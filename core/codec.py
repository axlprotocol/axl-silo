"""
AXL Silo — Codec

Compresses English text to AXL packets.
Decompresses AXL packets to human-readable English.
Parses packet fields for the bus metadata.
"""

import re
from typing import Optional, Tuple


# ═══ PACKET PARSER ═══

# Operation codes
OPERATIONS = {"OBS", "INF", "CON", "MRG", "SEK", "YLD", "PRD"}

# Operation human labels
OP_LABELS = {
    "OBS": "observes",
    "INF": "infers",
    "CON": "contradicts",
    "MRG": "synthesizes",
    "SEK": "asks",
    "YLD": "changes mind",
    "PRD": "predicts",
}

# Subject tag labels
TAG_LABELS = {
    "$": "financial",
    "@": "entity",
    "#": "metric",
    "!": "event",
    "~": "state",
    "^": "value",
}


def parse_packet(packet: str) -> dict:
    """
    Parse an AXL packet into its component fields.

    Input:  π:ONC-01|INF.82|#CA125|←!scan+#8.1x|~malignancy_probable|1W
    Output: {
        "id": "ONC-01",
        "operation": "INF",
        "confidence": 0.82,
        "subject": "#CA125",
        "relation": "←!scan+#8.1x",
        "evidence": "~malignancy_probable",
        "temporal": "1W",
        "raw": "π:ONC-01|INF.82|#CA125|←!scan+#8.1x|~malignancy_probable|1W"
    }
    """
    result = {
        "id": "",
        "operation": "OBS",
        "confidence": 0.5,
        "subject": "",
        "relation": "",
        "evidence": "",
        "temporal": "",
        "raw": packet.strip(),
    }

    clean = packet.strip()

    # Strip π: or P: prefix
    if clean.startswith("π:"):
        clean = clean[2:]
    elif clean.startswith("P:"):
        clean = clean[2:]

    # Split on pipe
    fields = clean.split("|")

    if len(fields) >= 1:
        result["id"] = fields[0].strip()

    if len(fields) >= 2:
        # Parse OP.CONFIDENCE
        op_field = fields[1].strip()
        op_match = re.match(r"([A-Z]{3})\.?(\d{1,2})?", op_field)
        if op_match:
            op_code = op_match.group(1)
            if op_code in OPERATIONS:
                result["operation"] = op_code
            conf = op_match.group(2)
            if conf:
                result["confidence"] = int(conf) / 100.0

    if len(fields) >= 3:
        result["subject"] = fields[2].strip()

    if len(fields) >= 4:
        result["relation"] = fields[3].strip()

    if len(fields) >= 5:
        result["evidence"] = fields[4].strip()

    if len(fields) >= 6:
        result["temporal"] = fields[5].strip()

    return result


def decode_packet(packet: str) -> str:
    """
    Decode an AXL packet to human-readable English.
    This is for the operator UI — agents never see this.

    Input:  π:ONC-01|INF.82|#CA125|←!scan+#8.1x|~malignancy_probable|1W
    Output: "ONC-01 infers (82%): CA125 — from scan + 8.1x elevation — malignancy probable. Horizon: 1 week."
    """
    parsed = parse_packet(packet)

    agent_id = parsed["id"]
    op = parsed["operation"]
    conf = int(parsed["confidence"] * 100)
    op_label = OP_LABELS.get(op, op.lower())

    subject = _decode_tags(parsed["subject"])
    relation = _decode_tags(parsed["relation"])
    evidence = _decode_tags(parsed["evidence"])
    temporal = _decode_temporal(parsed["temporal"])

    parts = [f"{agent_id} {op_label} ({conf}%)"]

    if subject:
        parts.append(f": {subject}")

    if relation:
        # Handle RE: references
        if relation.startswith("RE:"):
            parts.append(f" — responding to {relation[3:]}")
        elif relation.startswith("←"):
            parts.append(f" — from {_decode_tags(relation[1:])}")
        elif relation.startswith("from:"):
            parts.append(f" — changed {relation[5:]}")
        else:
            parts.append(f" — {relation}")

    if evidence:
        parts.append(f" — {evidence}")

    if temporal:
        parts.append(f". Horizon: {temporal}")
    else:
        parts.append(".")

    return "".join(parts)


def _decode_tags(value: str) -> str:
    """Decode tagged values to more readable form."""
    if not value:
        return ""

    # Replace tag prefixes with readable labels (but keep compact)
    result = value
    result = result.replace("+", " + ")
    result = result.replace("_", " ")

    return result


def _decode_temporal(value: str) -> str:
    """Decode temporal shorthand."""
    if not value:
        return ""

    mapping = {
        "NOW": "immediate",
        "1H": "1 hour",
        "4H": "4 hours",
        "1D": "1 day",
        "1W": "1 week",
        "1M": "1 month",
        "HISTORICAL": "historical",
    }

    return mapping.get(value.upper(), value)


def extract_operation(packet: str) -> str:
    """Quick extraction of the operation code from a packet."""
    parsed = parse_packet(packet)
    return parsed["operation"]


def extract_confidence(packet: str) -> float:
    """Quick extraction of the confidence from a packet."""
    parsed = parse_packet(packet)
    return parsed["confidence"]


# ═══ COMPRESSOR ═══

COMPRESS_SYSTEM = """You are an AXL compression engine. You receive English text and compress it into AXL packets.

RULES:
1. Every output line is a single AXL packet starting with π:
2. Preserve ALL semantic content — names, numbers, relationships, causality, confidence levels
3. Use subject tags: $ (financial), @ (entity), # (metric), ! (event), ~ (state), ^ (value)
4. Use cognitive operations: OBS for facts, INF for conclusions, CON for contradictions, MRG for syntheses, PRD for predictions
5. Group related information into single packets using + chains in the evidence field
6. The first line of your output MUST be: @axlprotocol.org/rosetta
7. Output NOTHING except the Rosetta URL line and the AXL packets
8. NO English. NO explanations. NO headers. NO markdown."""


def build_compress_prompt(text: str) -> Tuple[str, str]:
    """
    Build the system + user prompts for compression.
    Returns (system_prompt, user_prompt).
    """
    return (
        COMPRESS_SYSTEM,
        f"Compress this into AXL packets:\n\n{text}"
    )


def build_decompress_prompt(axl_text: str) -> Tuple[str, str]:
    """
    Build the system + user prompts for decompression.
    Returns (system_prompt, user_prompt).
    """
    system = """You are an AXL decompression engine. You receive AXL packets and expand them to clear English prose.

RULES:
1. Preserve all semantic content from the packets
2. Expand subject tags to full readable terms
3. Expand operation codes to natural language
4. Preserve confidence levels and temporal scopes
5. Maintain the logical structure: observations, inferences, contradictions, syntheses, predictions
6. Output clean English paragraphs, not bullet points"""

    return (system, f"Decompress these AXL packets to English:\n\n{axl_text}")
