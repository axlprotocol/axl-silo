"""
AXL Silo — Signal Extractor

Reads the bus and computes:
- Per-agent belief state trajectory
- Network consensus (weighted)
- Operation distribution
- Influence chains (who changed whose mind)
- The final Sophon Signal (if applicable)
"""

from typing import List, Dict
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


def extract_influence_chains(packets: List[Packet]) -> List[dict]:
    """
    Trace influence chains from YLD packets.

    When an agent YLDs, the RE: field indicates who caused it.
    Returns a list of: {"yielder": "Dr.Patel", "caused_by": "Dr.Chen", "round": 7}
    """
    chains = []
    for p in packets:
        if p.operation == "YLD":
            parsed = parse_packet(p.content)
            relation = parsed.get("relation", "")
            # Extract RE:agent_name
            if "RE:" in relation:
                caused_by = relation.split("RE:")[1].split("|")[0].split("+")[0].strip()
                chains.append({
                    "yielder": p.agent,
                    "caused_by": caused_by,
                    "round": p.round,
                    "content": p.content,
                })
    return chains


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


def build_signal(packets: List[Packet], seed_name: str = "") -> dict:
    """
    Build the full intelligence signal from the bus.

    This is the equivalent of the Sophon Signal — the final output
    of a Silo deliberation.
    """
    consensus = extract_consensus(packets)
    beliefs = extract_belief_table(packets)
    ops = extract_operation_distribution(packets)
    chains = extract_influence_chains(packets)
    predictions = extract_predictions(packets)

    # Stats
    total_chars = sum(len(p.content) for p in packets)
    total_tokens = sum(p.token_count for p in packets)
    agents = list(beliefs.keys())
    providers = list(set(p.provider for p in packets))
    models = list(set(p.model for p in packets))

    return {
        "seed": seed_name,
        "consensus": consensus,
        "operations": ops,
        "influence_chains": chains,
        "predictions": predictions,
        "agents": agents,
        "providers": providers,
        "models": models,
        "total_packets": len(packets),
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "avg_chars_per_packet": total_chars // max(len(packets), 1),
        "rounds": max((p.round for p in packets), default=0),
    }
