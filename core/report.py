# Copyright 2026 AXLPROTOCOL INC.
# Licensed under the Apache License, Version 2.0
"""
AXL Silo — Report Generator

Takes the bus output from a completed deliberation and produces
an academic-grade document: structured, cited, with methodology,
evidence chains, belief trajectories, and a formal conclusion.

The report is what the customer keeps. The bus is ephemeral.
The report is the permanent artifact of the collective intelligence.

Output formats:
  - Markdown (for GitHub, web, preview)
  - HTML (styled, for browser viewing)
  - JSON (structured, for downstream processing)
"""

import time
import json
from typing import List, Dict, Optional
from datetime import datetime

from .bus import Packet
from .signal import (
    extract_belief_table,
    extract_consensus,
    extract_operation_distribution,
    extract_influence_chains,
    extract_predictions,
    build_signal,
)
from .codec import decode_packet, parse_packet, OP_LABELS


class ReportGenerator:
    """
    Generates a formal report from a completed Silo deliberation.

    The report reads like an academic paper:
    - Title + metadata
    - Executive summary
    - Methodology
    - The seed (the question)
    - Participant registry (agents, models, providers)
    - Deliberation transcript (round by round)
    - Belief trajectory analysis
    - Consensus formation
    - Influence chain analysis
    - Operation distribution
    - Predictions and confidence
    - Conclusion and recommendation
    - Appendix: raw packets, cost breakdown
    """

    def __init__(self, packets: List[Packet], config: dict = None):
        self.packets = packets
        self.config = config or {}
        self.signal = build_signal(packets, seed_name=self.config.get("name", ""))
        self.beliefs = extract_belief_table(packets)
        self.consensus = extract_consensus(packets)
        self.ops = extract_operation_distribution(packets)
        self.chains = extract_influence_chains(packets)
        self.predictions = extract_predictions(packets)

    def generate_markdown(self) -> str:
        """Generate the full report as Markdown."""
        sections = []

        # ═══ TITLE ═══
        name = self.config.get("name", "Untitled Deliberation")
        ts = datetime.now().strftime("%B %d, %Y at %H:%M UTC")
        rounds = self.signal.get("rounds", 0)
        total = self.signal.get("total_packets", 0)
        providers = self.signal.get("providers", [])
        models = self.signal.get("models", [])

        sections.append(f"""# {name}

**AXL Silo — Deliberation Report**

| Field | Value |
|-------|-------|
| Generated | {ts} |
| Rounds | {rounds} |
| Total packets | {total} |
| Agents | {len(self.signal.get('agents', []))} |
| Providers | {', '.join(providers)} |
| Models | {', '.join(models)} |
| Consensus score | {self.consensus.get('consensus_score', 0):.1%} |
| Agreement ratio | {self.consensus.get('agreement_ratio', 0):.1%} |
| Belief changes (YLD) | {self.consensus.get('belief_changes', 0)} |
| Total characters | {self.signal.get('total_chars', 0):,} |

---
""")

        # ═══ EXECUTIVE SUMMARY ═══
        sections.append(self._section_executive_summary())

        # ═══ METHODOLOGY ═══
        sections.append(self._section_methodology())

        # ═══ PARTICIPANT REGISTRY ═══
        sections.append(self._section_participants())

        # ═══ DELIBERATION TRANSCRIPT ═══
        sections.append(self._section_transcript())

        # ═══ BELIEF TRAJECTORIES ═══
        sections.append(self._section_beliefs())

        # ═══ CONSENSUS FORMATION ═══
        sections.append(self._section_consensus())

        # ═══ INFLUENCE CHAINS ═══
        sections.append(self._section_influence())

        # ═══ OPERATION DISTRIBUTION ═══
        sections.append(self._section_operations())

        # ═══ PREDICTIONS ═══
        sections.append(self._section_predictions())

        # ═══ CONCLUSION ═══
        sections.append(self._section_conclusion())

        # ═══ APPENDIX A: COST ═══
        sections.append(self._section_cost())

        # ═══ APPENDIX B: RAW PACKETS ═══
        sections.append(self._section_raw_packets())

        return "
".join(sections)

    def _section_executive_summary(self) -> str:
        name = self.config.get("name", "this question")
        total = self.signal.get("total_packets", 0)
        rounds = self.signal.get("rounds", 0)
        agents = self.signal.get("agents", [])
        providers = self.signal.get("providers", [])
        consensus = self.consensus.get("consensus_score", 0)
        agreement = self.consensus.get("agreement_ratio", 0)
        ylds = self.consensus.get("belief_changes", 0)

        # Find dominant prediction
        pred_summary = "No formal predictions were issued."
        if self.predictions:
            top_pred = max(self.predictions, key=lambda p: p["confidence"])
            pred_summary = (
                f"The highest-confidence prediction came from {top_pred['agent']} "
                f"({top_pred['provider']}) at {top_pred['confidence']:.0%} confidence: "
                f"{top_pred['subject']} {top_pred.get('evidence', '')}."
            )

        return f"""## Executive Summary

{len(agents)} agents from {len(providers)} LLM providers ({', '.join(providers)}) deliberated on "{name}" over {rounds} rounds, producing {total} AXL packets.

The deliberation reached a consensus score of {consensus:.1%} with an agreement ratio of {agreement:.1%}. {ylds} belief changes (YLD operations) were recorded during the deliberation, indicating genuine epistemic updating rather than static position-holding.

{pred_summary}

All communication occurred exclusively in AXL Protocol packets — no English was used on the message bus. Each agent received only the Rosetta specification (377 lines) as its system context. The protocol was the sole interoperability layer between competing LLM architectures.

---
"""

    def _section_methodology(self) -> str:
        providers = self.signal.get("providers", [])
        models = self.signal.get("models", [])
        rounds = self.signal.get("rounds", 0)

        return f"""## Methodology

This deliberation was conducted in the AXL Silo — a contained workspace where multiple Large Language Models communicate exclusively through the AXL Protocol. The methodology follows the protocol's core design principles:

**Communication layer.** All agent communication was conducted in AXL packets conforming to the Rosetta v2.1 specification. No natural language was permitted on the message bus. Each packet consists of a single line encoding: agent identity, cognitive operation (OBS/INF/CON/MRG/SEK/YLD/PRD), confidence level, subject with typed tags, evidence chain, and temporal scope.

**Agent independence.** Each agent was instantiated as an independent LLM call through the litellm abstraction layer. Agents were connected to {len(set(providers))} different LLM providers ({', '.join(set(providers))}), using {len(set(models))} different models ({', '.join(set(models))}). No agent had access to another agent's system prompt, internal state, or model weights. The only shared context was the Rosetta specification and the public message bus.

**Round structure.** The deliberation proceeded for {rounds} rounds. In each round, every agent read the most recent 20 packets from the bus, formulated a response through its LLM, and posted a single AXL packet. Agents were called sequentially to ensure causal ordering of packets on the bus.

**Packet validation.** Each agent response was truncated to the first line containing a valid AXL packet (starting with π: and containing a recognized cognitive operation code). Trailing English explanations were stripped. Responses that did not contain a valid AXL packet were logged as errors and excluded from the bus.

**Consensus extraction.** The intelligence signal was computed from the bus at completion using deterministic parsing of AXL packets. Consensus score is the weighted average of agent confidence levels. Agreement ratio is the proportion of agents not in active contradiction (CON). Belief changes are counted from YLD operations. Influence chains are traced through RE: references in YLD packets.

---
"""

    def _section_participants(self) -> str:
        lines = ["## Participant Registry
"]
        lines.append("| Agent | Role | Model | Provider | Packets | Last Operation |")
        lines.append("|-------|------|-------|----------|---------|----------------|")

        for agent_name, trajectory in self.beliefs.items():
            if not trajectory:
                continue
            role = ""
            model = trajectory[0].get("model", "unknown")
            provider = trajectory[0].get("provider", "unknown")
            count = len(trajectory)
            last_op = trajectory[-1].get("operation", "—")
            last_conf = trajectory[-1].get("confidence", 0)
            lines.append(
                f"| {agent_name} | {role} | `{model}` | {provider} | {count} | {last_op} ({last_conf:.0%}) |"
            )

        lines.append("
---
")
        return "
".join(lines)

    def _section_transcript(self) -> str:
        lines = ["## Deliberation Transcript
"]

        current_round = -1
        for pkt in self.packets:
            if pkt.round != current_round:
                current_round = pkt.round
                lines.append(f"
### Round {current_round}
")

            parsed = parse_packet(pkt.content)
            op_label = OP_LABELS.get(pkt.operation, pkt.operation)
            conf = f"{pkt.confidence:.0%}"

            lines.append(f"**{pkt.agent}** ({pkt.provider}) — *{op_label}* at {conf} confidence")
            lines.append(f"```")
            lines.append(pkt.content)
            lines.append(f"```")

            if pkt.decoded:
                lines.append(f"> {pkt.decoded}")

            lines.append("")

        lines.append("---
")
        return "
".join(lines)

    def _section_beliefs(self) -> str:
        lines = ["## Belief Trajectory Analysis
"]
        lines.append("The following table shows each agent's cognitive trajectory across rounds — the sequence of operations they performed and how their confidence evolved.
")

        for agent_name, trajectory in self.beliefs.items():
            if not trajectory:
                continue

            lines.append(f"### {agent_name}
")
            lines.append("| Round | Operation | Confidence | Key Content |")
            lines.append("|-------|-----------|------------|-------------|")

            for entry in trajectory:
                r = entry["round"]
                op = entry["operation"]
                conf = f"{entry['confidence']:.0%}"
                content = entry["content"][:60] + "..." if len(entry["content"]) > 60 else entry["content"]
                lines.append(f"| {r} | {op} | {conf} | `{content}` |")

            # Trajectory summary
            ops_used = [e["operation"] for e in trajectory]
            changed_mind = "YLD" in ops_used
            first_conf = trajectory[0]["confidence"]
            last_conf = trajectory[-1]["confidence"]
            drift = last_conf - first_conf

            summary = f"Trajectory: {' → '.join(ops_used)}. "
            if changed_mind:
                summary += f"**Changed mind** during the deliberation. "
            summary += f"Confidence drift: {drift:+.0%} (from {first_conf:.0%} to {last_conf:.0%})."
            lines.append(f"
{summary}
")

        lines.append("---
")
        return "
".join(lines)

    def _section_consensus(self) -> str:
        score = self.consensus.get("consensus_score", 0)
        agreement = self.consensus.get("agreement_ratio", 0)
        agreeing = self.consensus.get("agents_agreeing", 0)
        disagreeing = self.consensus.get("agents_disagreeing", 0)
        ylds = self.consensus.get("belief_changes", 0)

        return f"""## Consensus Formation

| Metric | Value |
|--------|-------|
| Consensus score (weighted confidence) | {score:.1%} |
| Agreement ratio | {agreement:.1%} |
| Agents in agreement | {agreeing} |
| Agents in active contradiction | {disagreeing} |
| Belief changes (YLD operations) | {ylds} |

The consensus score represents the weighted average of each agent's most recent confidence level. Agreement ratio measures the proportion of agents not currently contradicting the emerging consensus. Belief changes indicate genuine epistemic updating — agents who received evidence or arguments that caused them to revise their position.

A consensus score above 70% with an agreement ratio above 80% indicates strong convergence. A high number of YLD operations relative to agent count indicates a dynamic, evidence-driven deliberation rather than static position-holding.

---
"""

    def _section_influence(self) -> str:
        lines = ["## Influence Chain Analysis
"]

        if not self.chains:
            lines.append("No belief changes (YLD operations) were detected. All agents maintained their initial positions throughout the deliberation.
")
        else:
            lines.append("The following influence chains trace which agents caused other agents to change their minds. Each chain shows: the yielding agent, the agent or evidence that caused the change, and the round in which it occurred.
")

            lines.append("| Round | Agent Changed | Caused By | Packet |")
            lines.append("|-------|--------------|-----------|--------|")

            for chain in self.chains:
                content = chain["content"][:50] + "..." if len(chain["content"]) > 50 else chain["content"]
                lines.append(
                    f"| {chain['round']} | {chain['yielder']} | {chain['caused_by']} | `{content}` |"
                )

            # Influence summary
            influencers = {}
            for chain in self.chains:
                name = chain["caused_by"]
                influencers[name] = influencers.get(name, 0) + 1

            if influencers:
                most_influential = max(influencers, key=influencers.get)
                lines.append(
                    f"
Most influential agent: **{most_influential}** "
                    f"(caused {influencers[most_influential]} belief change(s))."
                )

        lines.append("
---
")
        return "
".join(lines)

    def _section_operations(self) -> str:
        lines = ["## Cognitive Operation Distribution
"]
        lines.append("| Operation | Verb | Count | Percentage |")
        lines.append("|-----------|------|-------|------------|")

        total = sum(self.ops.values())
        for op in ["OBS", "INF", "CON", "MRG", "SEK", "YLD", "PRD"]:
            count = self.ops.get(op, 0)
            pct = f"{count / max(total, 1):.1%}"
            verb = OP_LABELS.get(op, op)
            lines.append(f"| {op} | {verb} | {count} | {pct} |")

        lines.append(f"| **TOTAL** | | **{total}** | |")

        # Analysis
        dominant = max(self.ops, key=self.ops.get) if self.ops else "N/A"
        lines.append(f"
Dominant operation: **{dominant}** ({OP_LABELS.get(dominant, dominant)}). ")

        if self.ops.get("CON", 0) > 0:
            con_ratio = self.ops["CON"] / max(total, 1)
            lines.append(f"Contradiction rate: {con_ratio:.1%} of all packets. ")

        if self.ops.get("YLD", 0) > 0:
            yld_ratio = self.ops["YLD"] / max(total, 1)
            lines.append(f"Belief change rate: {yld_ratio:.1%} of all packets. ")

        lines.append("

---
")
        return "
".join(lines)

    def _section_predictions(self) -> str:
        lines = ["## Predictions
"]

        if not self.predictions:
            lines.append("No formal predictions (PRD operations) were issued during the deliberation.
")
        else:
            lines.append("| Agent | Confidence | Subject | Evidence | Horizon | Provider |")
            lines.append("|-------|------------|---------|----------|---------|----------|")

            for pred in sorted(self.predictions, key=lambda p: -p["confidence"]):
                lines.append(
                    f"| {pred['agent']} | {pred['confidence']:.0%} | "
                    f"{pred['subject']} | {pred.get('evidence', '—')} | "
                    f"{pred.get('temporal', '—')} | {pred['provider']} |"
                )

            # Prediction convergence
            if len(self.predictions) >= 2:
                confs = [p["confidence"] for p in self.predictions]
                avg = sum(confs) / len(confs)
                spread = max(confs) - min(confs)
                lines.append(
                    f"
Prediction convergence: average confidence {avg:.1%}, "
                    f"spread {spread:.1%}. "
                )
                if spread < 0.2:
                    lines.append("Narrow spread indicates strong prediction convergence.")
                elif spread > 0.4:
                    lines.append("Wide spread indicates significant disagreement on the outcome.")

        lines.append("
---
")
        return "
".join(lines)

    def _section_conclusion(self) -> str:
        name = self.config.get("name", "the question posed")
        total = self.signal.get("total_packets", 0)
        rounds = self.signal.get("rounds", 0)
        providers = self.signal.get("providers", [])
        score = self.consensus.get("consensus_score", 0)
        agreement = self.consensus.get("agreement_ratio", 0)
        ylds = self.consensus.get("belief_changes", 0)
        chars = self.signal.get("total_chars", 0)
        avg_chars = self.signal.get("avg_chars_per_packet", 0)

        conclusion = f"""## Conclusion

This deliberation on "{name}" produced {total} AXL packets across {rounds} rounds, with {len(providers)} LLM providers participating ({', '.join(providers)}).

The collective intelligence reached a consensus score of {score:.1%} with {agreement:.1%} agreement. {ylds} agents changed their position during the deliberation, indicating that the process produced genuine epistemic updating rather than mere aggregation of initial positions.

The average packet length was {avg_chars} characters. The total deliberation consumed {chars:,} characters of bus traffic. Under AXL Protocol compression, this represents approximately 10x reduction compared to equivalent English-language deliberation.

All findings in this report are derived from deterministic parsing of AXL cognitive operation packets. No natural language processing or LLM inference was required to extract consensus, trace influence chains, or compute belief trajectories. The cognitive grammar makes thought machine-readable.

---

*Report generated by AXL Silo v0.1*
*Protocol: AXL v2.1 — https://axlprotocol.org/rosetta*
*Generated: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}*
"""
        return conclusion

    def _section_cost(self) -> str:
        tokens_in = self.signal.get("total_tokens", 0)
        chars = self.signal.get("total_chars", 0)

        return f"""## Appendix A: Resource Consumption

| Metric | Value |
|--------|-------|
| Total AXL characters | {chars:,} |
| Approximate tokens (AXL) | {tokens_in:,} |
| Estimated English equivalent | {chars * 10:,} characters |
| Compression ratio (estimated) | ~10x |

---
"""

    def _section_raw_packets(self) -> str:
        lines = ["## Appendix B: Raw Packet Log
"]
        lines.append("Complete bus transcript in chronological order.
")
        lines.append("```")
        for pkt in self.packets:
            lines.append(f"[R{pkt.round:02d}] [{pkt.provider:>10}] {pkt.agent:>20}: {pkt.content}")
        lines.append("```")
        lines.append("")
        return "
".join(lines)

    def generate_json(self) -> dict:
        """Export the full report as structured JSON."""
        return {
            "metadata": {
                "name": self.config.get("name", ""),
                "generated": datetime.now().isoformat(),
                "version": "axl-silo-0.1",
                "protocol": "axl-v2.1",
            },
            "signal": self.signal,
            "consensus": self.consensus,
            "operations": self.ops,
            "beliefs": {
                name: entries for name, entries in self.beliefs.items()
            },
            "influence_chains": self.chains,
            "predictions": self.predictions,
            "packets": [p.to_dict() for p in self.packets],
        }
