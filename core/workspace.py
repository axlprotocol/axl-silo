# Copyright 2026 AXLPROTOCOL INC.
# Licensed under the Apache License, Version 2.0
"""
AXL Silo — Workspace

The workspace manages a single deliberation session.
It owns the bus, the agents, the round loop, and the signal extraction.

This is the ring. The contained environment where LLMs collide.
"""

import time
import logging
import threading
import yaml
from typing import List, Optional, Callable
from dataclasses import dataclass

from .bus import Bus
from .agent import Agent, AgentConfig
from .rosetta import load_rosetta, build_agent_prompt, build_bus_context
from .codec import parse_packet, decode_packet, extract_operation, extract_confidence
from .signal import build_signal

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceConfig:
    """Configuration for a workspace session."""
    name: str
    seed_path: str
    rounds: int = 12
    agents: list = None             # List of AgentConfig dicts
    rosetta_path: str = ""
    max_bus_context: int = 20       # How many recent packets agents see
    delay_between_agents: float = 0.5  # Seconds between agent calls
    delay_between_rounds: float = 1.0

    @classmethod
    def from_yaml(cls, path: str) -> "WorkspaceConfig":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        ws = data.get("workspace", data)
        return cls(
            name=ws.get("name", "Untitled"),
            seed_path=ws.get("seed", ""),
            rounds=ws.get("rounds", 12),
            agents=ws.get("agents", []),
            rosetta_path=ws.get("rosetta_path", ""),
            max_bus_context=ws.get("max_bus_context", 20),
            delay_between_agents=ws.get("delay_between_agents", 0.5),
            delay_between_rounds=ws.get("delay_between_rounds", 1.0),
        )


class Workspace:
    """
    A single deliberation session in the Silo.

    Lifecycle:
    1. Create workspace with config
    2. Load Rosetta and seed
    3. Create agents
    4. Run the round loop
    5. Extract the signal
    """

    def __init__(self, config: WorkspaceConfig):
        self.config = config
        self.bus = Bus()
        self.agents: List[Agent] = []
        self.rosetta = ""
        self.seed_text = ""
        self.state = "INIT"        # INIT, LOADING, READY, RUNNING, PAUSED, COMPLETE, ERROR
        self.current_round = 0
        self.start_time = 0.0
        self.end_time = 0.0
        self._thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._pause_event.set()     # Not paused by default
        self._stop = False
        self._on_packet: Optional[Callable] = None
        self._on_round: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None

    def on_packet(self, callback: Callable):
        """Set callback for new packets. Receives the Packet object."""
        self._on_packet = callback

    def on_round(self, callback: Callable):
        """Set callback for round completion. Receives round number."""
        self._on_round = callback

    def on_complete(self, callback: Callable):
        """Set callback for workspace completion. Receives the signal dict."""
        self._on_complete = callback

    def load(self):
        """Load the Rosetta and seed, create agents."""
        self.state = "LOADING"

        # Load Rosetta
        self.rosetta = load_rosetta(self.config.rosetta_path or None)
        logger.info(f"Rosetta loaded: {len(self.rosetta)} chars")

        # Load seed
        if self.config.seed_path:
            with open(self.config.seed_path, "r") as f:
                self.seed_text = f.read()
            logger.info(f"Seed loaded: {self.config.seed_path}")

        # Create agents
        for agent_cfg in (self.config.agents or []):
            if isinstance(agent_cfg, dict):
                ac = AgentConfig(
                    name=agent_cfg.get("name", "Unknown"),
                    role=agent_cfg.get("role", "Agent"),
                    model=agent_cfg.get("model", "openai/gpt-4o"),
                    provider=agent_cfg.get("provider", "openai"),
                    api_key=agent_cfg.get("api_key", ""),
                    api_base=agent_cfg.get("api_base", ""),
                    temperature=agent_cfg.get("temperature", 0.7),
                    max_tokens=agent_cfg.get("max_tokens", 200),
                )
            else:
                ac = agent_cfg

            # Build the system prompt for this agent
            system_prompt = build_agent_prompt(
                rosetta=self.rosetta,
                agent_name=ac.name,
                agent_role=ac.role,
                seed_context=self.seed_text,
            )

            agent = Agent(config=ac, system_prompt=system_prompt)
            self.agents.append(agent)
            logger.info(f"Agent created: {ac.name} ({ac.model} via {ac.provider})")

        self.state = "READY"
        logger.info(f"Workspace ready: {self.config.name} — {len(self.agents)} agents, {self.config.rounds} rounds")

    def run(self, blocking: bool = False):
        """Start the round loop. Non-blocking by default (runs in thread)."""
        if self.state not in ("READY", "PAUSED"):
            raise RuntimeError(f"Cannot run workspace in state: {self.state}")

        self._stop = False

        if blocking:
            self._run_loop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def pause(self):
        """Pause the round loop."""
        self._pause_event.clear()
        self.state = "PAUSED"
        logger.info("Workspace paused")

    def resume(self):
        """Resume the round loop."""
        self._pause_event.set()
        self.state = "RUNNING"
        logger.info("Workspace resumed")

    def stop(self):
        """Stop the round loop."""
        self._stop = True
        self._pause_event.set()  # Unblock if paused
        if self._thread:
            self._thread.join(timeout=30)
        self.state = "COMPLETE"
        logger.info("Workspace stopped")

    def inject(self, content: str, agent_name: str = "OPERATOR") -> Optional[dict]:
        """
        Operator injects a packet into the bus manually.
        Content should be a raw AXL packet.
        """
        parsed = parse_packet(content)
        packet = self.bus.post(
            agent=agent_name,
            agent_role="Operator",
            content=content,
            operation=parsed["operation"],
            confidence=parsed["confidence"],
            model="human",
            provider="operator",
            decoded=decode_packet(content),
        )
        if self._on_packet:
            self._on_packet(packet)
        return packet.to_dict()

    def get_signal(self) -> dict:
        """Extract the current intelligence signal from the bus."""
        return build_signal(self.bus.read(), seed_name=self.config.name)

    def get_status(self) -> dict:
        """Workspace status for the UI."""
        elapsed = 0.0
        if self.start_time:
            end = self.end_time if self.end_time else time.time()
            elapsed = round(end - self.start_time, 1)

        return {
            "name": self.config.name,
            "state": self.state,
            "current_round": self.current_round,
            "total_rounds": self.config.rounds,
            "total_packets": self.bus.count(),
            "elapsed_seconds": elapsed,
            "agents": [a.status() for a in self.agents],
            "bus_stats": self.bus.stats(),
        }

    def _run_loop(self):
        """The main round loop. Runs in a thread."""
        self.state = "RUNNING"
        self.start_time = time.time()
        logger.info(f"Round loop started: {self.config.name}")

        try:
            for round_num in range(1, self.config.rounds + 1):
                # Check for stop
                if self._stop:
                    break

                # Check for pause
                self._pause_event.wait()
                if self._stop:
                    break

                self.current_round = round_num
                self.bus.round = round_num
                logger.info(f"═══ Round {round_num}/{self.config.rounds} ═══")

                for agent in self.agents:
                    if self._stop:
                        break

                    # Check for pause between agents
                    self._pause_event.wait()
                    if self._stop:
                        break

                    # Build bus context for this agent
                    recent_packets = self.bus.read(limit=self.config.max_bus_context)
                    bus_context = build_bus_context(recent_packets, self.config.max_bus_context)

                    # Call the agent
                    raw_packet = agent.respond(bus_context)

                    if raw_packet:
                        # Parse the packet
                        parsed = parse_packet(raw_packet)
                        decoded = decode_packet(raw_packet)

                        # Post to bus
                        packet = self.bus.post(
                            agent=agent.name,
                            agent_role=agent.role,
                            content=raw_packet,
                            operation=parsed["operation"],
                            confidence=parsed["confidence"],
                            model=agent.model,
                            provider=agent.provider,
                            decoded=decoded,
                            token_count=len(raw_packet.split()),  # Approximate
                        )

                        logger.info(f"  {agent.name} ({agent.provider}): {raw_packet[:80]}")

                        # Notify listeners
                        if self._on_packet:
                            self._on_packet(packet)
                    else:
                        logger.warning(f"  {agent.name}: no valid packet returned")

                    # Delay between agents
                    if self.config.delay_between_agents > 0:
                        time.sleep(self.config.delay_between_agents)

                # Round complete
                if self._on_round:
                    self._on_round(round_num)

                logger.info(f"  Round {round_num} complete: {self.bus.count()} total packets")

                # Delay between rounds
                if self.config.delay_between_rounds > 0 and round_num < self.config.rounds:
                    time.sleep(self.config.delay_between_rounds)

        except Exception as e:
            logger.error(f"Round loop error: {e}")
            self.state = "ERROR"
            return

        self.end_time = time.time()
        self.state = "COMPLETE"
        elapsed = round(self.end_time - self.start_time, 1)
        logger.info(f"Workspace complete: {self.bus.count()} packets in {elapsed}s")

        # Signal
        signal = self.get_signal()
        if self._on_complete:
            self._on_complete(signal)
