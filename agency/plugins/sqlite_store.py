"""SQLiteStateStore — persistent state store backed by SQLite.

Agent state survives process crashes and restarts. Each agent's state is
stored as a JSON blob keyed by agent name.

Usage:
    store = SQLiteStateStore("agency_state.db")
    runtime = Runtime(supervisor=..., state_store=store)
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class SQLiteStateStore:
    """SQLite-backed StateStore implementing the StateStore protocol.

    State is scoped per-agent. Stateless agents (those that never call
    checkpoint()) incur zero overhead — no rows are written.
    """

    def __init__(self, db_path: str = "agency_state.db") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_state "
            "(agent_name TEXT PRIMARY KEY, state TEXT NOT NULL)"
        )
        self._conn.commit()

    async def get(self, agent_name: str) -> dict[str, Any] | None:
        """Load agent state from SQLite."""
        row = self._conn.execute(
            "SELECT state FROM agent_state WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    async def set(self, agent_name: str, state: dict[str, Any]) -> None:
        """Save agent state to SQLite (upsert)."""
        self._conn.execute(
            "INSERT INTO agent_state (agent_name, state) VALUES (?, ?) "
            "ON CONFLICT(agent_name) DO UPDATE SET state = excluded.state",
            (agent_name, json.dumps(state)),
        )
        self._conn.commit()

    async def delete(self, agent_name: str) -> None:
        """Remove agent state from SQLite."""
        self._conn.execute(
            "DELETE FROM agent_state WHERE agent_name = ?",
            (agent_name,),
        )
        self._conn.commit()

    async def list_agents(self) -> list[str]:
        """Return all agent names with persisted state."""
        rows = self._conn.execute(
            "SELECT agent_name FROM agent_state ORDER BY agent_name"
        ).fetchall()
        return [r[0] for r in rows]

    async def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __del__(self) -> None:
        """Ensure connection is closed on garbage collection."""
        try:
            self._conn.close()
        except Exception:
            pass
