# Copyright 2026 AXLPROTOCOL INC.
# Licensed under the Apache License, Version 2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
AXL Silo — Signal Extractor

Reads the bus and computes:
- Per-agent belief state trajectory
- Network consensus (weighted)
- Operation distribution
- Influence chains (who changed whose mind, full multi-hop chains)
- Per-round summaries
- Concise LLM-readable report context
- The final Sophon Signal (if applicable)
"""

from typing import List, Dict, Optional
from .bus import Packet
from .codec import parse_packet, OPERATIONS


def extract_belief_table(packets: List[Packet]) -> Dict[str, list]:
    """
    Build a per-agent belief state trajectory.

    Returns: {
        "Dr.Chen": [
            {"round": 1, "operation": "OBS", "confidence": 0.92, "content": "..."},
            {"round": 3, "operation": "INF", "confidence": 0.85, "content": "..."},
            {"round": 7, "operation": "YLD", "confidence": 0.60, "content": "..."},
        ],
        ...
    }
    """
    beliefs = {}
    for p in packets:
        if p.agent not in beliefs:
            beliefs[p.agent] = []
        beliefs[p.agent].append({
            "round": p.round,
            "operation": p.operation,
            "confidence": p.confidence,
            "content": p.content,
            "model": p.model,
            "provider": p.provider,
        })
    return beliefs


def extract_consensus(packets: List[Packet]) -> dict:
    """
    Compute weighted consensus from the most recent PRD or INF packet per agent.

    Returns: {
        "consensus_score": 0.74,  # weighted average confidence
        "agreement_ratio": 0.83,  # proportion of agents on majority side
        "dominant_operation": "INF",
        "agents_agreeing": 10,
        "agents_disagreeing": 2,
        "belief_changes": 3,  # YLD count
    }
    """
    # Get the most recent packet per agent
    latest = {}
    for p in packets:
        latest[p.agent] = p

    if not latest:
        return {
            "consensus_score": 0.0,
            "agreement_ratio": 0.0,
            "dominant_operation": "N/A",
            "agents_agreeing": 0,
            "agents_disagreeing": 0,
            "belief_changes": 0,
        }

    # Count operations across all packets
    yld_count = sum(1 for p in packets if p.operation == "YLD")
    con_count = sum(1 for p in packets if p.operation == "CON")

    # Weighted confidence from latest packets
    confidences = [p.confidence for p in latest.values() if p.confidence > 0]
    avg_confidence = sum(confidences) / max(len(confidences), 1)

    # Count operations in latest round
    latest_ops = [p.operation for p in latest.values()]
    op_counts = {}
    for op in latest_ops:
        op_counts[op] = op_counts.get(op, 0) + 1
    dominant = max(op_counts, key=op_counts.get) if op_counts else "N/A"

    # Agreement: agents NOT contradicting (i.e., not CON in latest)
    con_agents = sum(1 for p in latest.values() if p.operation == "CON")
    agreeing = len(latest) - con_agents

    return {
        "consensus_score": round(avg_confidence, 3),
        "agreement_ratio": round(agreeing / max(len(latest), 1), 3),
        "dominant_operation": dominant,
        "agents_agreeing": agreeing,
        "agents_disagreeing": con_agents,
        "belief_changes": yld_count,
    }


def extract_operation_distribution(packets: List[Packet]) -> dict:
    """Count of each operation across all packets."""
    dist = {op: 0 for op in OPERATIONS}
    for p in packets:
        if p.operation in dist:
            dist[p.operation] += 1
    return dist


def _extract_re_agents(parsed: dict) -> List[str]:
    """
    Extract the list of agent names from a RE: reference in any parsed field.

    Handles RE:agent1+agent2 in any of: relation, evidence, subject, or raw content.
    Returns a list of agent name strings (may be empty).
    """
    # Search all string fields for a RE: token
    search_order = ["relation", "evidence", "subject", "raw"]
    for field in search_order:
        value = parsed.get(field, "")
        if "RE:" in value:
            re_part = value.split("RE:")[1].split("|")[0].strip()
            agents = [a.strip() for a in re_part.split("+") if a.strip()]
            if agents:
                return agents
    return []


def extract_influence_chains(packets: List[Packet]) -> List[dict]:
    """
    Trace influence chains from YLD packets, including multi-agent RE: references
    and full multi-hop chains (A caused B to YLD, B later caused C to YLD → A→B→C).

    Also computes most_influential_agent: the agent whose arguments caused the most YLDs
    (directly or transitively).

    Returns a list of:
        {
            "yielder": "Dr.Patel",
            "caused_by": ["Dr.Chen"],       # list — handles RE:agent1+agent2
            "round": 7,
            "content": "...",
            "chain": ["Dr.Chen", "Dr.Patel"],   # full causal chain leading to this yield
        }
    Plus a trailing sentinel entry:
        {"most_influential_agent": "Dr.Chen", "ylds_caused": 2}
    """
    chains = []

    # First pass: build raw yield events with all causing agents
    for p in packets:
        if p.operation == "YLD":
            parsed = parse_packet(p.content)
            caused_by = _extract_re_agents(parsed)
            chains.append({
                "yielder": p.agent,
                "caused_by": caused_by,
                "round": p.round,
                "content": p.content,
                "chain": [],  # filled in below
            })

    # Second pass: resolve full chains using sorted order (earlier rounds first)
    chains.sort(key=lambda x: x["round"])

    # Map: agent → the chain that ends with that agent yielding
    # We track the "best" (longest) chain that leads to each yielder
    yielder_chain: Dict[str, list] = {}

    for entry in chains:
        yielder = entry["yielder"]
        caused_by = entry["caused_by"]

        if not caused_by:
            entry["chain"] = [yielder]
        else:
            # Try to extend from any known chain of a causing agent
            best_prefix: list = []
            for cause in caused_by:
                candidate = yielder_chain.get(cause, [cause])
                if len(candidate) > len(best_prefix):
                    best_prefix = candidate
            entry["chain"] = best_prefix + [yielder]

        # Record the chain for this yielder (keep longest if multiple yields)
        existing = yielder_chain.get(yielder, [])
        if len(entry["chain"]) > len(existing):
            yielder_chain[yielder] = entry["chain"]

    # Compute most influential agent: count how many YLD chains each agent appears in
    # as a non-yielder (i.e., as a cause)
    influence_counts: Dict[str, int] = {}
    for entry in chains:
        for cause in entry["caused_by"]:
            influence_counts[cause] = influence_counts.get(cause, 0) + 1

    most_influential: Optional[str] = None
    max_ylds = 0
    if influence_counts:
        most_influential = max(influence_counts, key=influence_counts.get)
        max_ylds = influence_counts[most_influential]

    result = list(chains)
    result.append({
        "most_influential_agent": most_influential,
        "ylds_caused": max_ylds,
    })
    return result


def extract_predictions(packets: List[Packet]) -> List[dict]:
    """Extract all PRD packets with their predictions."""
    predictions = []
    for p in packets:
        if p.operation == "PRD":
            parsed = parse_packet(p.content)
            predictions.append({
                "agent": p.agent,
                "confidence": p.confidence,
                "subject": parsed.get("subject", ""),
                "evidence": parsed.get("evidence", ""),
                "temporal": parsed.get("temporal", ""),
                "round": p.round,
                "model": p.model,
                "provider": p.provider,
            })
    return predictions


def extract_round_summary(packets: List[Packet], round_num: int) -> dict:
    """
    Summarise activity for a specific round number.

    Returns: {
        "round": 1,
        "active_agents": ["Dr.Chen", "Dr.Patel"],
        "operations": {"INF": 1, "CON": 1, ...},
        "yld_count": 0,
        "dominant_op": "INF",
        "key_events": ["Dr.Chen posted INF@0.85", ...]
    }
    """
    round_packets = [p for p in packets if p.round == round_num]

    active_agents = list(dict.fromkeys(p.agent for p in round_packets))  # preserve order, unique

    ops: Dict[str, int] = {}
    for p in round_packets:
        ops[p.operation] = ops.get(p.operation, 0) + 1

    yld_count = ops.get("YLD", 0)
    dominant_op = max(ops, key=ops.get) if ops else "N/A"

    key_events = []
    for p in round_packets:
        parsed = parse_packet(p.content)
        subject = parsed.get("subject", "")
        event = f"{p.agent} posted {p.operation}@{p.confidence:.2f}"
        if subject:
            event += f" re:{subject}"
        key_events.append(event)

    return {
        "round": round_num,
        "active_agents": active_agents,
        "operations": ops,
        "yld_count": yld_count,
        "dominant_op": dominant_op,
        "key_events": key_events,
    }


def build_report_context(packets: List[Packet], seed_name: str = "") -> str:
    """
    Build a concise (~2000 char max) structured text summary for the report LLM.

    This is NOT the full bus — it is distilled intelligence the LLM reads when
    generating the executive summary and conclusion.

    Format: structured plain text, easy to parse.
    """
    consensus = extract_consensus(packets)
    ops = extract_operation_distribution(packets)
    chains = extract_influence_chains(packets)
    predictions = extract_predictions(packets)

    # Pull most_influential from the sentinel appended by extract_influence_chains
    most_influential = None
    real_chains = []
    for entry in chains:
        if "most_influential_agent" in entry:
            most_influential = entry.get("most_influential_agent")
        else:
            real_chains.append(entry)

    total_packets = len(packets)
    num_rounds = max((p.round for p in packets), default=0)
    agents = list(dict.fromkeys(p.agent for p in packets))

    lines = []
    lines.append(f"SEED: {seed_name or 'unnamed'}")
    lines.append(f"ROUNDS: {num_rounds}  PACKETS: {total_packets}  AGENTS: {len(agents)} ({', '.join(agents)})")
    lines.append("")

    # Consensus block
    lines.append("=== CONSENSUS ===")
    lines.append(f"Score: {consensus['consensus_score']:.0%}  "
                 f"Agreement: {consensus['agreement_ratio']:.0%}  "
                 f"Dominant-op: {consensus['dominant_operation']}")
    lines.append(f"Agreeing agents: {consensus['agents_agreeing']}  "
                 f"Contradicting: {consensus['agents_disagreeing']}  "
                 f"Belief-changes (YLD): {consensus['belief_changes']}")
    lines.append("")

    # Operation breakdown
    active_ops = {k: v for k, v in ops.items() if v > 0}
    lines.append("=== OPERATIONS ===")
    op_parts = [f"{k}:{v}" for k, v in sorted(active_ops.items(), key=lambda x: -x[1])]
    lines.append("  ".join(op_parts) if op_parts else "none")
    lines.append("")

    # Influence chains
    lines.append("=== INFLUENCE ===")
    if most_influential:
        lines.append(f"Most influential agent: {most_influential}")
    if real_chains:
        for c in real_chains[:5]:  # cap at 5 to stay within char budget
            caused_str = "+".join(c["caused_by"]) if c["caused_by"] else "?"
            chain_str = "→".join(c["chain"]) if c["chain"] else c["yielder"]
            lines.append(f"  R{c['round']}: {caused_str} → {c['yielder']} (YLD)  chain: {chain_str}")
    else:
        lines.append("  No influence events (no YLDs with RE: references)")
    lines.append("")

    # Top predictions
    if predictions:
        lines.append("=== TOP PREDICTIONS ===")
        top_preds = sorted(predictions, key=lambda x: -x["confidence"])[:5]
        for pred in top_preds:
            subj = pred["subject"] or pred.get("evidence", "")[:40]
            lines.append(f"  [{pred['agent']} R{pred['round']} @{pred['confidence']:.2f}] {subj}")
        lines.append("")

    # Per-round snapshot
    if num_rounds > 0:
        lines.append("=== ROUND SNAPSHOTS ===")
        for r in range(1, num_rounds + 1):
            rs = extract_round_summary(packets, r)
            agents_str = ", ".join(rs["active_agents"])
            ops_str = "  ".join(f"{k}:{v}" for k, v in rs["operations"].items() if v > 0)
            lines.append(f"  R{r}: [{agents_str}]  ops={ops_str}  ylds={rs['yld_count']}")
        lines.append("")

    text = "\n".join(lines)

    # Hard cap at ~2000 chars — truncate with notice if over
    if len(text) > 2000:
        text = text[:1960] + "\n...[truncated for LLM budget]"

    return text


def extract_agent_summary(packets: List[Packet], agent_name: str) -> dict:
    """
    Build a full profile for a specific agent across the entire bus.

    Returns: {
        "name": "Dr.Chen",
        "total_packets": 4,
        "operations": {"INF": 2, "YLD": 1, ...},
        "trajectory": [{"round": 1, "op": "INF", "conf": 0.85}, ...],
        "influenced_by": ["Dr.Patel"],   # agents who caused this agent to YLD
        "influenced": ["Dr.Patel"],      # agents this agent caused to YLD
    }
    """
    agent_packets = [p for p in packets if p.agent == agent_name]

    ops: Dict[str, int] = {}
    trajectory = []
    for p in sorted(agent_packets, key=lambda x: x.round):
        ops[p.operation] = ops.get(p.operation, 0) + 1
        trajectory.append({
            "round": p.round,
            "op": p.operation,
            "conf": p.confidence,
        })

    # Who caused this agent to YLD?
    influenced_by = []
    for p in agent_packets:
        if p.operation == "YLD":
            parsed = parse_packet(p.content)
            for cause in _extract_re_agents(parsed):
                if cause not in influenced_by:
                    influenced_by.append(cause)

    # Who did this agent cause to YLD?
    influenced = []
    for p in packets:
        if p.agent != agent_name and p.operation == "YLD":
            parsed = parse_packet(p.content)
            causers = _extract_re_agents(parsed)
            if agent_name in causers and p.agent not in influenced:
                influenced.append(p.agent)

    return {
        "name": agent_name,
        "total_packets": len(agent_packets),
        "operations": ops,
        "trajectory": trajectory,
        "influenced_by": influenced_by,
        "influenced": influenced,
    }


def build_signal(packets: List[Packet], seed_name: str = "") -> dict:
    """
    Build the full intelligence signal from the bus.

    This is the equivalent of the Sophon Signal — the final output
    of a Silo deliberation.

    Includes:
    - round_summaries: per-round activity digest
    - most_influential_agent: agent who caused the most YLDs
    - report_context: concise LLM-readable summary string
    - compression_estimate: AXL chars vs estimated English equivalent
    """
    consensus = extract_consensus(packets)
    beliefs = extract_belief_table(packets)
    ops = extract_operation_distribution(packets)
    chains = extract_influence_chains(packets)
    predictions = extract_predictions(packets)

    # Extract most_influential from the sentinel entry in chains
    most_influential = None
    real_chains = []
    for entry in chains:
        if "most_influential_agent" in entry:
            most_influential = entry.get("most_influential_agent")
        else:
            real_chains.append(entry)

    # Stats
    total_chars = sum(len(p.content) for p in packets)
    total_tokens = sum(p.token_count for p in packets)
    agents = list(beliefs.keys())
    providers = list(set(p.provider for p in packets))
    models = list(set(p.model for p in packets))
    num_rounds = max((p.round for p in packets), default=0)

    # Per-round summaries
    round_summaries = [extract_round_summary(packets, r) for r in range(1, num_rounds + 1)]

    # Report context for LLM
    report_context = build_report_context(packets, seed_name)

    # Compression estimate: AXL is terse; natural English equivalent is ~8-10x longer
    estimated_english_chars = total_chars * 9  # midpoint of 8–10x

    return {
        "seed": seed_name,
        "consensus": consensus,
        "operations": ops,
        "influence_chains": real_chains,
        "predictions": predictions,
        "agents": agents,
        "providers": providers,
        "models": models,
        "total_packets": len(packets),
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "avg_chars_per_packet": total_chars // max(len(packets), 1),
        "rounds": num_rounds,
        # New fields
        "round_summaries": round_summaries,
        "most_influential_agent": most_influential,
        "report_context": report_context,
        "compression_estimate": {
            "total_axl_chars": total_chars,
            "estimated_english_chars": estimated_english_chars,
            "compression_ratio": f"1:{total_chars // max(estimated_english_chars // 9, 1) * 9 // max(total_chars, 1)}x"
            if total_chars > 0 else "N/A",
        },
    }
