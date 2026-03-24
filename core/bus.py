"""
AXL Silo — Message Bus

The ring. Every packet flows through here.
No English. No prose. Only AXL.

The bus is an ordered, append-only list of packets.
Agents read from it. Agents post to it.
The operator sees it through the WebSocket feed.
"""

import time
import threading
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Callable


@dataclass
class Packet:
    """A single AXL packet on the bus."""
    id: int
    agent: str
    agent_role: str
    side: str               # "axl" — always. The bus is AXL-only.
    content: str            # The raw AXL packet string
    operation: str          # Extracted: OBS, INF, CON, MRG, SEK, YLD, PRD
    confidence: float       # Extracted: 0.0—1.0
    round: int
    timestamp: float
    model: str              # Which LLM produced this
    provider: str           # Which provider (openai, anthropic, google, local)
    decoded: str = ""       # English decode (computed by codec, for UI only)
    token_count: int = 0    # Token count of the raw AXL content

    def to_dict(self):
        return asdict(self)


class Bus:
    """
    The message bus. Append-only. Thread-safe.
    
    Every message on the bus is an AXL packet.
    No English is stored on the bus — ever.
    The decoded field is computed post-hoc for the operator UI.
    """

    def __init__(self):
        self._packets: List[Packet] = []
        self._lock = threading.Lock()
        self._listeners: List[Callable] = []
        self._round = 0

    @property
    def round(self) -> int:
        return self._round

    @round.setter
    def round(self, value: int):
        self._round = value

    def post(self, agent: str, agent_role: str, content: str,
             operation: str, confidence: float, model: str,
             provider: str, decoded: str = "", token_count: int = 0) -> Packet:
        """Post a packet to the bus. Returns the created packet."""
        with self._lock:
            packet = Packet(
                id=len(self._packets),
                agent=agent,
                agent_role=agent_role,
                side="axl",
                content=content.strip(),
                operation=operation,
                confidence=confidence,
                round=self._round,
                timestamp=time.time(),
                model=model,
                provider=provider,
                decoded=decoded,
                token_count=token_count,
            )
            self._packets.append(packet)

        # Notify listeners (outside lock to prevent deadlock)
        for listener in self._listeners:
            try:
                listener(packet)
            except Exception:
                pass

        return packet

    def read(self, since_id: int = 0, limit: int = 0) -> List[Packet]:
        """Read packets from the bus since a given ID."""
        with self._lock:
            packets = self._packets[since_id:]
            if limit > 0:
                packets = packets[-limit:]
            return list(packets)

    def read_round(self, round_num: int) -> List[Packet]:
        """Read all packets from a specific round."""
        with self._lock:
            return [p for p in self._packets if p.round == round_num]

    def read_agent(self, agent: str) -> List[Packet]:
        """Read all packets from a specific agent."""
        with self._lock:
            return [p for p in self._packets if p.agent == agent]

    def last(self, n: int = 1) -> List[Packet]:
        """Read the last N packets."""
        with self._lock:
            return list(self._packets[-n:])

    def count(self) -> int:
        """Total packet count."""
        with self._lock:
            return len(self._packets)

    def subscribe(self, listener: Callable):
        """Subscribe to new packets. Listener receives Packet objects."""
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable):
        """Remove a listener."""
        self._listeners = [l for l in self._listeners if l != listener]

    def stats(self) -> dict:
        """Bus statistics."""
        with self._lock:
            if not self._packets:
                return {
                    "total_packets": 0,
                    "rounds": 0,
                    "agents": [],
                    "operations": {},
                    "total_chars": 0,
                    "avg_chars": 0,
                    "providers": [],
                }

            ops = {}
            agents = set()
            providers = set()
            total_chars = 0
            total_tokens = 0

            for p in self._packets:
                ops[p.operation] = ops.get(p.operation, 0) + 1
                agents.add(p.agent)
                providers.add(p.provider)
                total_chars += len(p.content)
                total_tokens += p.token_count

            return {
                "total_packets": len(self._packets),
                "rounds": self._round,
                "agents": sorted(agents),
                "operations": ops,
                "total_chars": total_chars,
                "total_tokens": total_tokens,
                "avg_chars": total_chars // max(len(self._packets), 1),
                "providers": sorted(providers),
            }

    def export(self) -> List[dict]:
        """Export the full bus as a list of dicts (for JSON serialization)."""
        with self._lock:
            return [p.to_dict() for p in self._packets]

    def clear(self):
        """Clear the bus. Use with caution."""
        with self._lock:
            self._packets.clear()
            self._round = 0
