# Copyright 2026 AXL Protocol Inc.
# Licensed under the Apache License, Version 2.0
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
        "timestamp": "",
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
        "timestamp": "",
        "raw": packet.strip(),
    }

    clean = packet.strip()

    # Strip π: or P: or pi: prefix
    if clean.startswith("π:"):
        clean = clean[2:]
    elif clean.startswith("P:"):
        clean = clean[2:]
    elif clean.startswith("pi:"):
        clean = clean[3:]

    # Split on pipe
    fields = [f.strip() for f in clean.split("|")]

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
        rel_field = fields[3].strip()
        # Handle from:X→Y for YLD packets
        if rel_field.startswith("from:"):
            result["relation"] = rel_field
        # Handle RE: with multiple references (RE:agent1+agent2)
        elif rel_field.startswith("RE:"):
            result["relation"] = rel_field
        else:
            result["relation"] = rel_field

    if len(fields) >= 5:
        result["evidence"] = fields[4].strip()

    if len(fields) >= 6:
        temporal_field = fields[5].strip()
        # Check whether this field is a T: timestamp
        if temporal_field.startswith("T:"):
            result["timestamp"] = temporal_field[2:]
        else:
            result["temporal"] = temporal_field

    # Scan remaining fields for T: timestamp if not yet found
    if not result["timestamp"] and len(fields) >= 7:
        for extra in fields[6:]:
            extra = extra.strip()
            if extra.startswith("T:"):
                result["timestamp"] = extra[2:]

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
    relation = parsed["relation"]
    evidence = _decode_tags(parsed["evidence"])
    temporal = _decode_temporal(parsed["temporal"])

    parts = [f"{agent_id} {op_label} ({conf}%)"]

    if subject:
        parts.append(f": {subject}")

    if relation:
        # Handle RE: references — support multiple (RE:agent1+agent2)
        if relation.startswith("RE:"):
            refs_raw = relation[3:]
            refs = [r.strip() for r in refs_raw.split("+")]
            parts.append(f" — responding to {', '.join(refs)}")
        elif relation.startswith("←"):
            parts.append(f" — from {_decode_tags(relation[1:])}")
        # Handle from:X→Y in YLD packets
        elif relation.startswith("from:"):
            parts.append(f" — changed {relation[5:]}")
        else:
            parts.append(f" — {_decode_tags(relation)}")

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


# ═══ INPUT COMPRESSION PIPELINE ═══

def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list:
    """Split text into overlapping chunks for compression.

    Splits on paragraph boundaries first, then by size.
    Returns list of strings.
    """
    if not text:
        return []

    # Split into paragraphs (two or more newlines, or single newline)
    paragraphs = re.split(r"\n{2,}", text.strip())
    if len(paragraphs) == 1:
        # No paragraph breaks — fall back to single-newline split
        paragraphs = re.split(r"\n", text.strip())

    chunks = []
    current_chunk = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_len = len(para)

        # If a single paragraph is larger than chunk_size, hard-split it
        if para_len > chunk_size:
            # Flush current chunk first
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                # Keep overlap: last paragraph(s) that fit within `overlap` chars
                overlap_buf = []
                overlap_len = 0
                for p in reversed(current_chunk):
                    if overlap_len + len(p) <= overlap:
                        overlap_buf.insert(0, p)
                        overlap_len += len(p)
                    else:
                        break
                current_chunk = overlap_buf
                current_len = overlap_len

            # Hard-split large paragraph by character windows
            start = 0
            while start < para_len:
                end = min(start + chunk_size, para_len)
                chunks.append(para[start:end])
                start = end - overlap if end < para_len else end
            continue

        if current_len + para_len > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # Carry forward overlap
            overlap_buf = []
            overlap_len = 0
            for p in reversed(current_chunk):
                if overlap_len + len(p) <= overlap:
                    overlap_buf.insert(0, p)
                    overlap_len += len(p)
                else:
                    break
            current_chunk = overlap_buf
            current_len = overlap_len

        current_chunk.append(para)
        current_len += para_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks if chunks else [text]


def normalize_packet(raw: str) -> str:
    """Normalize AXL packet from different LLM providers.

    - pi: → π:
    - P: → π:
    - Strip spaces around |
    - Validate operation code
    - Clamp confidence to 0-99
    """
    s = raw.strip()

    # Normalize prefix variants
    if s.startswith("pi:"):
        s = "π:" + s[3:]
    elif s.startswith("P:"):
        s = "π:" + s[2:]

    # Strip spaces around pipe characters
    s = re.sub(r"\s*\|\s*", "|", s)

    # Validate / clamp operation code and confidence
    prefix = ""
    body = s
    if s.startswith("π:"):
        prefix = "π:"
        body = s[2:]

    fields = body.split("|")
    if len(fields) >= 2:
        op_field = fields[1]
        op_match = re.match(r"([A-Za-z]{2,3})\.?(\d+)?", op_field)
        if op_match:
            op_code = op_match.group(1).upper()
            conf_str = op_match.group(2)

            # Clamp confidence
            if conf_str is not None:
                conf_val = max(0, min(99, int(conf_str)))
                fields[1] = f"{op_code}.{conf_val:02d}"
            else:
                fields[1] = op_code

        body = "|".join(fields)

    return prefix + body


def strip_english(response: str) -> Optional[str]:
    """Extract the AXL packet from a potentially English-laden LLM response.

    Strategy:
    1. Find first line containing π: or a recognized OP code with |
    2. Take only that line
    3. Truncate at first English sentence boundary after the packet
    4. Return None if no valid packet found
    """
    if not response:
        return None

    lines = response.splitlines()

    # Pattern: line starts with π: / P: / pi: or contains OP.NN|
    packet_line_re = re.compile(
        r"^\s*(π:|pi:|P:)[^\|]*\|"  # canonical prefix
        r"|^\s*[A-Z]{3}\.\d{1,2}\|"  # bare OP.NN| (no prefix)
    )
    # Also accept lines that have a recognized OP code with pipe separators
    op_pipe_re = re.compile(
        r"(?:π:|pi:|P:)\S+\|(?:" + "|".join(OPERATIONS) + r")\.\d"
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        is_packet = bool(packet_line_re.match(stripped))
        if not is_packet:
            # Secondary check: contains π: followed by pipes
            is_packet = bool(re.search(r"π:[^\s|]+\|[A-Z]{3}", stripped))

        if is_packet:
            # Truncate at first English sentence boundary after the packet
            # A sentence boundary is ". " or ".\n" followed by a capital letter
            # or a newline with normal English text
            truncated = re.split(r"\.\s+[A-Z]", stripped)
            candidate = truncated[0].strip()
            # Restore the period that was consumed by the split lookahead
            if len(truncated) > 1 and not candidate.endswith("."):
                candidate = candidate  # period already not there — fine
            return candidate

    return None


def compress_text(
    text: str,
    model: str = "anthropic/claude-sonnet-4-20250514",
    api_key: str = None,
    max_packets: int = 30,
) -> list:
    """Compress any text to AXL packets.

    Pipeline:
    1. If text < 500 words: compress directly in 1 LLM call
    2. If text >= 500 words: chunk → compress per chunk → deduplicate
    3. Returns list of raw AXL packet strings

    Uses litellm for the LLM call.
    Uses build_compress_prompt for the prompt.
    Parses response, strips English, normalizes packets.
    """
    try:
        import litellm
    except ImportError as exc:
        raise ImportError(
            "litellm is required for compress_text. "
            "Install it with: pip install litellm"
        ) from exc

    word_count = len(text.split())

    def _call_llm(chunk: str) -> str:
        system_prompt, user_prompt = build_compress_prompt(chunk)
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if api_key:
            kwargs["api_key"] = api_key
        response = litellm.completion(**kwargs)
        return response.choices[0].message.content or ""

    def _parse_response(raw_response: str) -> list:
        packets = []
        for line in raw_response.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip the Rosetta URL line
            if line.startswith("@axlprotocol.org"):
                continue
            # Attempt to extract a packet from potentially English-laden lines
            candidate = strip_english(line) if not (
                line.startswith("π:") or line.startswith("pi:") or line.startswith("P:")
            ) else line
            if candidate:
                normalized = normalize_packet(candidate)
                packets.append(normalized)
        return packets

    if word_count < 500:
        raw = _call_llm(text)
        packets = _parse_response(raw)
    else:
        chunks = chunk_text(text)
        all_packets = []
        for chunk in chunks:
            raw = _call_llm(chunk)
            all_packets.extend(_parse_response(raw))

        # Deduplicate while preserving order (by raw string equality)
        seen = set()
        packets = []
        for pkt in all_packets:
            if pkt not in seen:
                seen.add(pkt)
                packets.append(pkt)

    # Cap at max_packets
    return packets[:max_packets]
