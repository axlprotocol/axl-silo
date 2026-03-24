# Copyright 2026 AXLPROTOCOL INC.
# Licensed under the Apache License, Version 2.0
"""
AXL Silo — Rosetta Loader

Loads the Rosetta specification and builds system prompts
for agents. The Rosetta is the ONLY shared code between agents.
"""

import os
import urllib.request

# Default paths to look for the Rosetta
ROSETTA_PATHS = [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "rosetta-v2.1.md"),
    "/opt/axl-silo/rosetta-v2.1.md",
    "/opt/axl-swarm/rosetta-v2.1.md",
]

# Fallback URL for remote fetch
ROSETTA_URL = "https://axlprotocol.org/rosetta"

# Local cache file path for URL-fetched content
ROSETTA_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rosetta-cache.md")

_cached_rosetta = None


def load_rosetta(path: str = None) -> str:
    """Load the Rosetta specification from disk, with URL fetch fallback."""
    global _cached_rosetta

    if _cached_rosetta and not path:
        return _cached_rosetta

    # Try explicit path first
    if path and os.path.exists(path):
        with open(path, "r") as f:
            _cached_rosetta = f.read()
            return _cached_rosetta

    # Try default paths
    for p in ROSETTA_PATHS:
        if os.path.exists(p):
            with open(p, "r") as f:
                _cached_rosetta = f.read()
                return _cached_rosetta

    # Try fetching from ROSETTA_URL
    try:
        req = urllib.request.urlopen(ROSETTA_URL, timeout=5)
        content = req.read().decode("utf-8")
        if content:
            _cached_rosetta = content
            # Save fetched content to local cache file
            try:
                with open(ROSETTA_CACHE_PATH, "w") as f:
                    f.write(content)
            except OSError:
                pass  # Cache write failure is non-fatal
            return _cached_rosetta
    except Exception:
        print(f"[rosetta] Could not fetch from {ROSETTA_URL} — continuing without remote rosetta.")

    raise FileNotFoundError(
        f"Rosetta not found. Looked in: {ROSETTA_PATHS}. "
        f"Place rosetta-v2.1.md in the project root or provide a path."
    )


ROUND_STRATEGIES = {
    "free": {},  # No operation restrictions per round
    "phased": {
        # Rounds 1-3: observation + inference
        (1, 3): ["OBS", "INF"],
        # Rounds 4-8: debate
        (4, 8): ["CON", "MRG", "SEK", "INF"],
        # Rounds 9-11: convergence
        (9, 11): ["YLD", "MRG", "PRD", "INF"],
        # Round 12+: final prediction
        (12, 99): ["PRD"],
    },
}


def get_round_instruction(round_num: int, strategy: str = "free") -> str:
    """Get the round-specific instruction for an agent."""
    if strategy == "free":
        return ""
    phases = ROUND_STRATEGIES.get(strategy, {})
    for (start, end), ops in phases.items():
        if start <= round_num <= end:
            ops_str = ", ".join(ops)
            return f"\nROUND PHASE: This is round {round_num}. Use these operations: {ops_str}."
    return ""


def build_agent_prompt(rosetta: str, agent_name: str, agent_role: str,
                       seed_context: str = "", bus_rules: str = "",
                       round_strategy: str = "free") -> str:
    """
    Build the system prompt for an agent.

    The prompt structure:
    1. The Rosetta (teaches the language)
    2. Agent identity (who you are)
    3. Communication rules (AXL only, one packet per response)
    4. Seed context (the question being deliberated)
    """

    rules = bus_rules or DEFAULT_BUS_RULES

    prompt = f"""{rosetta}

═══ AGENT IDENTITY ═══

You are {agent_name}.
Role: {agent_role}.

═══ COMMUNICATION RULES ═══

{rules}

═══ SEED CONTEXT ═══

{seed_context}
"""
    return prompt.strip()


DEFAULT_BUS_RULES = """You are an agent in the AXL Silo — a contained workspace where multiple LLMs
communicate ONLY through AXL Protocol packets.

ABSOLUTE RULES:
1. You communicate ONLY in AXL packets. No English prose. No explanations.
2. ONE packet per response. One line. Starts with π:
3. Use the cognitive operations: OBS, INF, CON, MRG, SEK, YLD, PRD
4. Use subject tags: $ (financial), @ (entity), # (metric), ! (event), ~ (state), ^ (value)
5. Include your confidence as OP.XX (e.g., INF.82 means 82% confident)
6. If you disagree with another agent, use CON and reference them with RE:agent_name
7. If you change your mind, use YLD and state from:OLD→NEW
8. Your packet must be self-contained. No references to "my previous message."
9. NEVER write English. NEVER explain your packet. NEVER add commentary.
10. If your response contains ANY English words that are not AXL field values, you have failed.

YOUR RESPONSE FORMAT:
π:YOUR_ID|OP.XX|SUBJECT|RELATION|EVIDENCE|TEMPORAL

NOTHING ELSE. ONE LINE. NO ENGLISH."""


def build_bus_context(packets: list, max_packets: int = 20,
                      round_num: int = None, strategy: str = "free") -> str:
    """
    Build the bus context string that agents see.
    Shows the most recent packets from the bus.
    Optionally includes round number and phase instruction.
    """
    if not packets:
        return "Bus is empty. You are the first to speak. Emit an OBS packet about the seed data."

    recent = packets[-max_packets:]
    lines = []
    for p in recent:
        lines.append(f"[R{p.round}] {p.agent}: {p.content}")

    context = "═══ BUS STATE (most recent packets) ═══\n" + "\n".join(lines)

    if round_num is not None:
        phase_instruction = get_round_instruction(round_num, strategy)
        if phase_instruction:
            context += phase_instruction

    return context
