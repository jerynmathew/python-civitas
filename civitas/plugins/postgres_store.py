"""PostgresStateStore — persistent state store backed by PostgreSQL.

Agent state survives process crashes and restarts. Each agent's state is
stored as a JSONB blob keyed by agent name. Requires ``civitas[postgres]``.

Usage:
    store = PostgresStateStore("postgresql://user:pass@host/db")
    runtime = Runtime(supervisor=..., state_store=store)

Or via topology YAML:

    plugins:
      state:
        type: postgres
        config:
          url: !ENV DATABASE_URL
          min_size: 1
          max_size: 10
          timeout: 30.0

``close()`` releases the connection pool. Runtime.stop() calls it automatically.
"""

from __future__ import annotations

import json
from typing import Any


class PostgresStateStore:
    """asyncpg-backed StateStore implementing the StateStore protocol.

    State is scoped per-agent. Stateless agents (those that never call
    checkpoint()) incur zero overhead — no rows are written.

    The connection pool is created lazily on first use (or on ``connect()``),
    so constructing this object is always safe even before the event loop starts.
    """

    TABLE_DDL = """
        CREATE TABLE IF NOT EXISTS civitas_agent_state (
            agent_name  TEXT PRIMARY KEY,
            state       JSONB NOT NULL,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """

    def __init__(
        self,
        url: str,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._min_size = min_size
        self._max_size = max_size
        self._timeout = timeout
        self._pool: Any = None  # asyncpg.Pool, set on first _ensure_pool()

    # ------------------------------------------------------------------
    # Connection pool lifecycle
    # ------------------------------------------------------------------

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            try:
                import asyncpg
            except ImportError as exc:
                raise ImportError(
                    "PostgresStateStore requires asyncpg. "
                    "Install it with: pip install civitas[postgres]"
                ) from exc
            self._pool = await asyncpg.create_pool(
                self._url,
                min_size=self._min_size,
                max_size=self._max_size,
                timeout=self._timeout,
            )
            async with self._pool.acquire() as conn:
                await conn.execute(self.TABLE_DDL)
        return self._pool

    async def close(self) -> None:
        """Close the connection pool. Authoritative cleanup path."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # ------------------------------------------------------------------
    # StateStore protocol
    # ------------------------------------------------------------------

    async def get(self, agent_name: str) -> dict[str, Any] | None:
        """Load agent state from Postgres, or None if not found."""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM civitas_agent_state WHERE agent_name = $1",
                agent_name,
            )
        if row is None:
            return None
        return json.loads(row["state"])  # type: ignore[no-any-return]

    async def set(self, agent_name: str, state: dict[str, Any]) -> None:
        """Upsert agent state into Postgres."""
        pool = await self._ensure_pool()
        blob = json.dumps(state)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO civitas_agent_state (agent_name, state, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (agent_name)
                DO UPDATE SET state = EXCLUDED.state, updated_at = NOW()
                """,
                agent_name,
                blob,
            )

    async def delete(self, agent_name: str) -> None:
        """Remove agent state from Postgres."""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM civitas_agent_state WHERE agent_name = $1",
                agent_name,
            )

    async def list_agents(self) -> list[str]:
        """Return all agent names with persisted state, sorted."""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT agent_name FROM civitas_agent_state ORDER BY agent_name"
            )
        return [r["agent_name"] for r in rows]
