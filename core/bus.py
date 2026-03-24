# Copyright 2026 AXLPROTOCOL INC.
# Licensed under the Apache License, Version 2.0
"""
AXL Silo — Message Bus

The ring. Every packet flows through here.
No English. No prose. Only AXL.

The bus is an ordered, append-only list of packets.
Agents read from it. Agents post to it.
The operator sees it through the WebSocket feed.

SQLite write-through persistence is optional. When a db_path is supplied the
bus keeps its in-memory list for WebSocket speed and simultaneously writes
every packet to SQLite so nothing is lost across restarts.
"""

import os
import shutil
import sqlite3
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


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    side TEXT DEFAULT 'axl',
    content TEXT NOT NULL,
    operation TEXT,
    confidence REAL DEFAULT 0.5,
    round INTEGER DEFAULT 0,
    timestamp REAL,
    model TEXT,
    provider TEXT,
    decoded TEXT DEFAULT '',
    token_count INTEGER DEFAULT 0
);
"""

_INSERT_PACKET = """
INSERT INTO packets
    (agent, agent_role, side, content, operation, confidence, round,
     timestamp, model, provider, decoded, token_count)
VALUES
    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_SELECT_ALL = """
SELECT id, agent, agent_role, side, content, operation, confidence, round,
       timestamp, model, provider, decoded, token_count
FROM packets
ORDER BY id ASC;
"""


def _row_to_packet(row) -> Packet:
    """Convert a SQLite row (tuple) to a Packet, remapping id to 0-based index."""
    (db_id, agent, agent_role, side, content, operation, confidence, rnd,
     timestamp, model, provider, decoded, token_count) = row
    return Packet(
        id=db_id - 1,          # 0-based in-memory index; SQLite uses 1-based AUTOINCREMENT
        agent=agent,
        agent_role=agent_role,
        side=side or "axl",
        content=content,
        operation=operation or "",
        confidence=float(confidence) if confidence is not None else 0.5,
        round=int(rnd) if rnd is not None else 0,
        timestamp=float(timestamp) if timestamp is not None else 0.0,
        model=model or "",
        provider=provider or "",
        decoded=decoded or "",
        token_count=int(token_count) if token_count is not None else 0,
    )


class Bus:
    """
    The message bus. Append-only. Thread-safe.

    Every message on the bus is an AXL packet.
    No English is stored on the bus — ever.
    The decoded field is computed post-hoc for the operator UI.

    When db_path is provided the bus opens (or creates) a SQLite database and
    performs write-through persistence: every post() writes to both the
    in-memory list and SQLite. All read operations use the in-memory list for
    maximum speed. Existing packets are loaded from SQLite on init so the bus
    survives process restarts.

    When db_path is None the bus is pure in-memory (backward compatible).
    """

    def __init__(self, db_path: str = None):
        self._packets: List[Packet] = []
        self._lock = threading.Lock()
        self._listeners: List[Callable] = []
        self._round = 0
        self._db_path: Optional[str] = db_path
        self._db: Optional[sqlite3.Connection] = None

        if db_path is not None:
            self._db = sqlite3.connect(db_path, check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL;")
            self._db.execute(_CREATE_TABLE)
            self._db.commit()
            self._load_from_db()

    # ------------------------------------------------------------------
    # Internal SQLite helpers
    # ------------------------------------------------------------------

    def _load_from_db(self):
        """Load all existing rows from SQLite into the in-memory list."""
        if self._db is None:
            return
        cursor = self._db.execute(_SELECT_ALL)
        rows = cursor.fetchall()
        for row in rows:
            packet = _row_to_packet(row)
            self._packets.append(packet)
        # Restore round counter from the highest round seen
        if self._packets:
            self._round = max(p.round for p in self._packets)

    def _write_to_db(self, packet: Packet):
        """Insert a single packet into SQLite. Must be called while holding self._lock."""
        if self._db is None:
            return
        self._db.execute(
            _INSERT_PACKET,
            (
                packet.agent,
                packet.agent_role,
                packet.side,
                packet.content,
                packet.operation,
                packet.confidence,
                packet.round,
                packet.timestamp,
                packet.model,
                packet.provider,
                packet.decoded,
                packet.token_count,
            ),
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Round management
    # ------------------------------------------------------------------

    @property
    def round(self) -> int:
        return self._round

    @round.setter
    def round(self, value: int):
        self._round = value

    # ------------------------------------------------------------------
    # Core bus operations
    # ------------------------------------------------------------------

    def post(self, agent: str, agent_role: str, content: str,
             operation: str, confidence: float, model: str,
             provider: str, decoded: str = "", token_count: int = 0) -> Packet:
        """Post a packet to the bus. Returns the created packet.

        Writes to self._packets (in-memory) and, if a db_path was configured,
        also writes to SQLite synchronously before returning.
        """
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
            self._write_to_db(packet)

        # Notify listeners outside the lock to prevent deadlock
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

    # ------------------------------------------------------------------
    # Session persistence helpers
    # ------------------------------------------------------------------

    def save_session(self, directory: str):
        """Export the bus database and a signal file to a session directory.

        Creates `directory` if it does not already exist. Copies bus.db (when
        SQLite is active) and writes a plain-text session.signal file that
        records the packet count and current round so callers can quickly
        inspect a session without opening the database.
        """
        os.makedirs(directory, exist_ok=True)

        # Write session signal (always, even for in-memory-only buses)
        signal_path = os.path.join(directory, "session.signal")
        with open(signal_path, "w") as fh:
            fh.write(f"packets={self.count()}\n")
            fh.write(f"round={self._round}\n")
            if self._db_path:
                fh.write(f"db={os.path.basename(self._db_path)}\n")

        if self._db is not None and self._db_path:
            # Flush WAL to main database file before copying
            self._db.execute("PRAGMA wal_checkpoint(FULL);")
            dest = os.path.join(directory, "bus.db")
            shutil.copy2(self._db_path, dest)

    @classmethod
    def load_session(cls, db_path: str) -> "Bus":
        """Create a Bus instance from an existing SQLite database file.

        This is a convenience classmethod equivalent to Bus(db_path) but
        makes the intent explicit at the call site.
        """
        return cls(db_path=db_path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Close the SQLite connection. Safe to call even without a database."""
        if self._db is not None:
            try:
                self._db.execute("PRAGMA wal_checkpoint(FULL);")
                self._db.close()
            except Exception:
                pass
            finally:
                self._db = None
