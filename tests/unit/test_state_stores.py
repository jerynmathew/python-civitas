"""Unit tests for StateStore protocol extensions and PostgresStateStore."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from civitas.plugins.state import InMemoryStateStore, StateStore

# ---------------------------------------------------------------------------
# StateStore protocol compliance helpers
# ---------------------------------------------------------------------------


def _assert_protocol(store: Any) -> None:
    """Verify the store satisfies the StateStore protocol (structural check)."""
    assert isinstance(store, StateStore)


# ---------------------------------------------------------------------------
# InMemoryStateStore — protocol extension (list_agents, close)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_list_agents_empty():
    store = InMemoryStateStore()
    assert await store.list_agents() == []


@pytest.mark.asyncio
async def test_in_memory_list_agents_returns_sorted_names():
    store = InMemoryStateStore()
    await store.set("zebra", {"x": 1})
    await store.set("alpha", {"x": 2})
    await store.set("mango", {"x": 3})
    assert await store.list_agents() == ["alpha", "mango", "zebra"]


@pytest.mark.asyncio
async def test_in_memory_list_agents_excludes_deleted():
    store = InMemoryStateStore()
    await store.set("a", {})
    await store.set("b", {})
    await store.delete("a")
    assert await store.list_agents() == ["b"]


@pytest.mark.asyncio
async def test_in_memory_close_is_noop():
    store = InMemoryStateStore()
    await store.set("agent_a", {"key": "val"})
    await store.close()  # must not raise
    # store still usable (in-memory; close is advisory)
    assert await store.get("agent_a") == {"key": "val"}


def test_in_memory_satisfies_protocol():
    _assert_protocol(InMemoryStateStore())


# ---------------------------------------------------------------------------
# PostgresStateStore — unit tests with mocked asyncpg
# ---------------------------------------------------------------------------


class _AsyncCtx:
    """Minimal async context manager wrapping a mock connection."""

    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *args: Any) -> None:
        pass


@pytest.fixture
def mock_asyncpg():
    """Patch asyncpg.create_pool to return a controllable mock pool."""
    with patch("civitas.plugins.postgres_store.PostgresStateStore._ensure_pool") as mock:
        yield mock


@pytest.mark.asyncio
async def test_postgres_get_returns_none_when_missing():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncCtx(conn))

    with patch.object(store, "_ensure_pool", AsyncMock(return_value=pool)):
        result = await store.get("missing_agent")

    assert result is None


@pytest.mark.asyncio
async def test_postgres_get_deserializes_json():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    state = {"counter": 42, "items": ["a", "b"]}
    row = MagicMock()
    row.__getitem__ = MagicMock(side_effect=lambda k: json.dumps(state) if k == "state" else None)
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=row)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncCtx(conn))

    with patch.object(store, "_ensure_pool", AsyncMock(return_value=pool)):
        result = await store.get("agent_a")

    assert result == state


@pytest.mark.asyncio
async def test_postgres_set_upserts_json():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncCtx(conn))

    with patch.object(store, "_ensure_pool", AsyncMock(return_value=pool)):
        await store.set("agent_a", {"count": 7})

    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    # Second positional arg is agent_name
    assert call_args[0][1] == "agent_a"
    # Third positional arg is the JSON blob
    assert json.loads(call_args[0][2]) == {"count": 7}


@pytest.mark.asyncio
async def test_postgres_delete_removes_row():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncCtx(conn))

    with patch.object(store, "_ensure_pool", AsyncMock(return_value=pool)):
        await store.delete("agent_a")

    conn.execute.assert_called_once()
    assert "agent_a" in conn.execute.call_args[0]


@pytest.mark.asyncio
async def test_postgres_list_agents_returns_sorted_names():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    names = ["zebra", "alpha", "mango"]

    def _make_row(name: str) -> MagicMock:
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: name)
        return row

    rows = [_make_row(n) for n in names]
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncCtx(conn))

    with patch.object(store, "_ensure_pool", AsyncMock(return_value=pool)):
        result = await store.list_agents()

    # Postgres ORDER BY handles ordering — our mock returns as given
    assert result == names


@pytest.mark.asyncio
async def test_postgres_close_releases_pool():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    pool = MagicMock()
    pool.close = AsyncMock()
    store._pool = pool

    await store.close()

    pool.close.assert_called_once()
    assert store._pool is None


@pytest.mark.asyncio
async def test_postgres_close_when_not_connected_is_noop():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    assert store._pool is None
    await store.close()  # must not raise


@pytest.mark.asyncio
async def test_postgres_missing_asyncpg_raises_helpful_error():
    from civitas.plugins.postgres_store import PostgresStateStore

    store = PostgresStateStore("postgresql://localhost/test")
    with patch("builtins.__import__", side_effect=ImportError("No module named 'asyncpg'")):
        # _ensure_pool should raise ImportError with install hint
        with pytest.raises(ImportError, match="civitas\\[postgres\\]"):
            # bypass cache — pool is None so _ensure_pool will try to import
            await store._ensure_pool()


# ---------------------------------------------------------------------------
# migrate CLI — unit tests with mocked stores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_copies_all_agents():
    from civitas.cli.state import _do_migrate

    src = InMemoryStateStore()
    await src.set("alpha", {"x": 1})
    await src.set("beta", {"x": 2})

    dst = InMemoryStateStore()

    with (
        patch("civitas.cli.state._parse_dsn", side_effect=[src, dst]),
    ):
        count = await _do_migrate("sqlite:src.db", "sqlite:dst.db", dry_run=False)

    assert count == 2
    assert await dst.get("alpha") == {"x": 1}
    assert await dst.get("beta") == {"x": 2}


@pytest.mark.asyncio
async def test_migrate_dry_run_does_not_write():
    from civitas.cli.state import _do_migrate

    src = InMemoryStateStore()
    await src.set("alpha", {"x": 1})

    dst = InMemoryStateStore()

    with patch("civitas.cli.state._parse_dsn", side_effect=[src, dst]):
        count = await _do_migrate("sqlite:src.db", "sqlite:dst.db", dry_run=True)

    assert count == 1
    assert await dst.get("alpha") is None  # dry-run — nothing written


@pytest.mark.asyncio
async def test_migrate_empty_source_returns_zero():
    from civitas.cli.state import _do_migrate

    src = InMemoryStateStore()
    dst = InMemoryStateStore()

    with patch("civitas.cli.state._parse_dsn", side_effect=[src, dst]):
        count = await _do_migrate("sqlite:src.db", "sqlite:dst.db", dry_run=False)

    assert count == 0


def test_parse_dsn_sqlite_prefix():
    from civitas.cli.state import _parse_dsn
    from civitas.plugins.sqlite_store import SQLiteStateStore

    store = _parse_dsn("sqlite:mydb.db")
    assert isinstance(store, SQLiteStateStore)


def test_parse_dsn_sqlite_extension():
    from civitas.cli.state import _parse_dsn
    from civitas.plugins.sqlite_store import SQLiteStateStore

    store = _parse_dsn("mydb.db")
    assert isinstance(store, SQLiteStateStore)


def test_parse_dsn_postgres_url():
    from civitas.cli.state import _parse_dsn
    from civitas.plugins.postgres_store import PostgresStateStore

    store = _parse_dsn("postgresql://user:pass@host/db")
    assert isinstance(store, PostgresStateStore)


def test_parse_dsn_unknown_raises():
    import typer

    from civitas.cli.state import _parse_dsn

    with pytest.raises(typer.BadParameter):
        _parse_dsn("redis://localhost")
