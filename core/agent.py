"""
AXL Silo — Agent

Wraps any LLM from any provider into an AXL-speaking agent.
Uses litellm for universal provider support.
The Rosetta is injected as the system prompt.
The agent reads the bus, calls its LLM, and returns ONE AXL packet.
"""

import re
import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a single agent."""
    name: str
    role: str
    model: str              # litellm model string: "openai/gpt-4o", "anthropic/claude-sonnet-4-20250514"
    provider: str           # "openai", "anthropic", "google", "local"
    api_key: str = ""       # Provider API key (empty for local)
    api_base: str = ""      # Custom API base URL (for litellm proxy or local Ollama)
    temperature: float = 0.7
    max_tokens: int = 200   # AXL packets are short


class Agent:
    """
    A single agent in the Silo ring.

    The agent:
    1. Receives the Rosetta as its system prompt
    2. Reads the bus (recent packets from other agents)
    3. Calls its LLM via litellm
    4. Returns ONE AXL packet (first line only, stripped of English)
    """

    def __init__(self, config: AgentConfig, system_prompt: str):
        self.config = config
        self.system_prompt = system_prompt
        self.packets_emitted = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.last_response_time = 0.0
        self.errors = 0

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def role(self) -> str:
        return self.config.role

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def provider(self) -> str:
        return self.config.provider

    def respond(self, bus_context: str) -> Optional[str]:
        """
        Call the LLM with the bus context and return one AXL packet.

        Returns the raw AXL packet string, or None on failure.
        """
        try:
            import litellm

            # Build the kwargs for litellm
            kwargs = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": bus_context + "\n\nYour response (ONE AXL packet, no English):"},
                ],
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }

            # Add API key if provided
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key

            # Add custom API base if provided (for litellm proxy, Ollama, etc.)
            if self.config.api_base:
                kwargs["api_base"] = self.config.api_base

            start = time.time()
            response = litellm.completion(**kwargs)
            self.last_response_time = time.time() - start

            # Extract usage
            if hasattr(response, "usage") and response.usage:
                self.total_input_tokens += getattr(response.usage, "prompt_tokens", 0)
                self.total_output_tokens += getattr(response.usage, "completion_tokens", 0)

            raw = response.choices[0].message.content.strip()

            # Extract the AXL packet: first line starting with π:
            packet = self._extract_packet(raw)

            if packet:
                self.packets_emitted += 1
                return packet
            else:
                logger.warning(f"Agent {self.name}: no valid AXL packet in response: {raw[:100]}")
                self.errors += 1
                return None

        except Exception as e:
            logger.error(f"Agent {self.name} error: {e}")
            self.errors += 1
            return None

    def _extract_packet(self, raw: str) -> Optional[str]:
        """
        Extract a single AXL packet from the LLM response.

        Strategy:
        1. Look for lines starting with π:
        2. Take the FIRST one
        3. Strip everything after the first newline
        4. Strip any trailing English explanation
        """
        lines = raw.strip().split("\n")

        for line in lines:
            line = line.strip()
            # Match π: at start (the canonical AXL packet prefix)
            if line.startswith("π:") or line.startswith("P:"):
                # Truncate at first English word boundary after the packet
                # AXL packets use |, +, :, ←, →, and tagged values
                # If we see a pattern like ". The" or ". This" it's English
                truncated = self._truncate_english(line)
                return truncated

        # Fallback: if no π: line, check if any line looks like AXL
        # (has pipe delimiters and operation codes)
        for line in lines:
            line = line.strip()
            if "|" in line and any(op in line for op in ["OBS", "INF", "CON", "MRG", "SEK", "YLD", "PRD"]):
                return self._truncate_english(line)

        return None

    def _truncate_english(self, packet: str) -> str:
        """
        Strip trailing English from a hybrid packet.
        
        Agents sometimes write: π:ID|INF.82|... This means I think...
        We cut at the first English sentence boundary after the AXL content.
        """
        # Split on common English sentence starters after AXL
        patterns = [
            r"\.\s+[A-Z][a-z]",      # Period + space + capitalized word
            r"\s+—\s+",              # Em dash with spaces
            r"\s+\(Note:",           # Parenthetical note
            r"\s+This\s",            # "This means..."
            r"\s+The\s",             # "The implication..."
            r"\s+I\s",              # "I believe..."
            r"\s+Based\s",           # "Based on..."
            r"\s+In\s",             # "In other words..."
        ]

        for pattern in patterns:
            match = re.search(pattern, packet)
            if match and match.start() > 20:  # Don't truncate too early
                return packet[:match.start()].rstrip(". ")

        return packet

    def status(self) -> dict:
        """Agent status for the UI."""
        return {
            "name": self.name,
            "role": self.role,
            "model": self.model,
            "provider": self.provider,
            "packets_emitted": self.packets_emitted,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "last_response_time": round(self.last_response_time, 2),
            "errors": self.errors,
        }
