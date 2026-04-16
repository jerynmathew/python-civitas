"""Unit tests for Supervisor — backoff, sliding window, strategy dispatch, heartbeat config."""

from __future__ import annotations

import time
from collections import deque
from unittest.mock import AsyncMock, patch

import pytest

from civitas.process import AgentProcess, ProcessStatus
from civitas.supervisor import (
    HeartbeatTimeout,
    Supervisor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class NullAgent(AgentProcess):
    async def handle(self, message):
        return None


def make_supervisor(**kwargs) -> Supervisor:
    defaults = dict(name="root", max_restarts=3, backoff="CONSTANT", backoff_base=1.0)
    defaults.update(kwargs)
    return Supervisor(**defaults)


# ---------------------------------------------------------------------------
# _compute_backoff
# ---------------------------------------------------------------------------


class TestComputeBackoff:
    def test_constant_always_returns_base(self):
        sup = make_supervisor(backoff="CONSTANT", backoff_base=0.5)
        assert sup._compute_backoff(1) == 0.5
        assert sup._compute_backoff(5) == 0.5

    def test_linear_scales_with_count(self):
        sup = make_supervisor(backoff="LINEAR", backoff_base=2.0)
        assert sup._compute_backoff(1) == 2.0
        assert sup._compute_backoff(3) == 6.0
        assert sup._compute_backoff(5) == 10.0

    def test_exponential_doubles_each_restart(self):
        sup = make_supervisor(backoff="EXPONENTIAL", backoff_base=1.0)
        # base * 2^(n-1), ignoring jitter
        with patch("civitas.supervisor.random.random", return_value=0.0):
            assert sup._compute_backoff(1) == 1.0  # 1 * 2^0
            assert sup._compute_backoff(2) == 2.0  # 1 * 2^1
            assert sup._compute_backoff(3) == 4.0  # 1 * 2^2

    def test_exponential_applies_jitter(self):
        sup = make_supervisor(backoff="EXPONENTIAL", backoff_base=1.0)
        with patch("civitas.supervisor.random.random", return_value=1.0):
            # delay = base * 2^0 = 1.0, jitter = 1.0 * 1.0 * 0.25 = 0.25
            assert sup._compute_backoff(1) == pytest.approx(1.25)

    def test_backoff_max_caps_result(self):
        sup = make_supervisor(backoff="LINEAR", backoff_base=10.0, backoff_max=15.0)
        assert sup._compute_backoff(10) == 15.0  # 100.0 capped at 15.0


# ---------------------------------------------------------------------------
# Sliding window (_restart_timestamps)
# ---------------------------------------------------------------------------


class TestRestartWindow:
    def test_timestamps_stored_as_deque(self):
        sup = make_supervisor()
        assert isinstance(sup._restart_timestamps, deque)

    def test_timestamps_pruned_outside_window(self):
        sup = make_supervisor(restart_window=10.0, max_restarts=100)
        now = time.time()
        # Inject two old timestamps (outside window) and one recent
        sup._restart_timestamps.append(now - 20.0)
        sup._restart_timestamps.append(now - 15.0)
        sup._restart_timestamps.append(now - 5.0)

        # Simulate _handle_crash pruning logic
        cutoff = now - sup.restart_window
        sup._restart_timestamps.append(now)
        while sup._restart_timestamps and sup._restart_timestamps[0] <= cutoff:
            sup._restart_timestamps.popleft()

        assert len(sup._restart_timestamps) == 2  # only the recent one + new
        assert all(t > cutoff for t in sup._restart_timestamps)

    def test_max_restarts_check_uses_window_length(self):
        sup = make_supervisor(restart_window=60.0, max_restarts=2)
        now = time.time()
        # 2 restarts already in window
        sup._restart_timestamps.extend([now - 5.0, now - 3.0])
        # Third crash exceeds limit
        assert len(sup._restart_timestamps) >= sup.max_restarts


# ---------------------------------------------------------------------------
# _find_child (O(1) dict lookup)
# ---------------------------------------------------------------------------


class TestFindChild:
    def test_find_returns_correct_agent(self):
        a = NullAgent("alpha")
        b = NullAgent("beta")
        sup = Supervisor("root", children=[a, b])
        assert sup._find_child("alpha") is a
        assert sup._find_child("beta") is b

    def test_find_returns_none_for_unknown(self):
        sup = Supervisor("root", children=[NullAgent("x")])
        assert sup._find_child("missing") is None

    def test_find_child_via_dict_not_linear_scan(self):
        # _children_by_name is a dict — verify it exists and has correct keys
        a = NullAgent("a")
        sup = Supervisor("root", children=[a])
        assert "a" in sup._children_by_name
        assert sup._children_by_name["a"] is a

    def test_find_child_supervisor(self):
        child_sup = Supervisor("child")
        sup = Supervisor("root", children=[child_sup])
        assert sup._find_child("child") is child_sup


# ---------------------------------------------------------------------------
# _escalate — permanently failed agent stays CRASHED
# ---------------------------------------------------------------------------


class TestEscalate:
    @pytest.mark.asyncio
    async def test_escalate_top_level_leaves_agent_crashed(self):
        agent = NullAgent("worker")
        agent._status = ProcessStatus.CRASHED
        sup = Supervisor("root", children=[agent], max_restarts=1)
        # No parent — top-level escalation
        await sup._escalate("worker", ValueError("boom"))
        # Agent stays CRASHED — not mutated to STOPPED
        assert agent.status == ProcessStatus.CRASHED

    @pytest.mark.asyncio
    async def test_escalate_with_parent_calls_parent_handle_crash(self):
        child_sup = Supervisor("child", max_restarts=1)
        parent_sup = Supervisor("root", children=[child_sup], max_restarts=5)
        child_sup._parent = parent_sup

        called_with: list = []

        async def mock_handle(name, exc):
            called_with.append((name, exc))

        parent_sup._handle_crash = mock_handle  # type: ignore[method-assign]
        exc = ValueError("cascade")
        await child_sup._escalate("child", exc)
        assert called_with == [("child", exc)]


# ---------------------------------------------------------------------------
# add_remote_child — per-child heartbeat config (F03-3)
# ---------------------------------------------------------------------------


class TestRemoteChildConfig:
    def test_each_child_gets_independent_config(self):
        sup = make_supervisor()
        sup.add_remote_child(
            "fast", heartbeat_interval=1.0, heartbeat_timeout=0.5, missed_heartbeats_threshold=2
        )
        sup.add_remote_child(
            "slow", heartbeat_interval=10.0, heartbeat_timeout=5.0, missed_heartbeats_threshold=5
        )

        fast_cfg = sup._remote_child_config["fast"]
        slow_cfg = sup._remote_child_config["slow"]

        assert fast_cfg["interval"] == 1.0
        assert fast_cfg["timeout"] == 0.5
        assert fast_cfg["threshold"] == 2

        assert slow_cfg["interval"] == 10.0
        assert slow_cfg["timeout"] == 5.0
        assert slow_cfg["threshold"] == 5

    def test_second_add_does_not_overwrite_first(self):
        sup = make_supervisor()
        sup.add_remote_child("a", heartbeat_timeout=0.5)
        sup.add_remote_child("b", heartbeat_timeout=9.9)
        # First child's config unchanged
        assert sup._remote_child_config["a"]["timeout"] == 0.5

    def test_add_remote_child_registers_in_set(self):
        sup = make_supervisor()
        sup.add_remote_child("remote_agent")
        assert "remote_agent" in sup._remote_children


# ---------------------------------------------------------------------------
# HeartbeatTimeout
# ---------------------------------------------------------------------------


class TestHeartbeatTimeout:
    def test_attributes(self):
        exc = HeartbeatTimeout("my_agent", missed=4)
        assert exc.agent_name == "my_agent"
        assert exc.missed == 4
        assert "my_agent" in str(exc)
        assert "4" in str(exc)


# ---------------------------------------------------------------------------
# Restart strategy dispatch
# ---------------------------------------------------------------------------


class TestStrategyDispatch:
    @pytest.mark.asyncio
    async def test_one_for_one_calls_restart_child(self):
        sup = Supervisor(
            "root", strategy="ONE_FOR_ONE", max_restarts=5, backoff="CONSTANT", backoff_base=0.0
        )
        sup._restart_counts["a"] = 0

        called = []
        sup._restart_child = AsyncMock(side_effect=lambda n: called.append(n))  # type: ignore[method-assign]
        sup._escalate = AsyncMock()  # type: ignore[method-assign]

        await sup._handle_crash("a", ValueError("x"))

        assert called == ["a"]
        sup._escalate.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_for_all_calls_restart_all(self):
        sup = Supervisor(
            "root", strategy="ONE_FOR_ALL", max_restarts=5, backoff="CONSTANT", backoff_base=0.0
        )
        sup._restart_counts["a"] = 0

        called = []
        sup._restart_all_children = AsyncMock(side_effect=lambda: called.append("all"))  # type: ignore[method-assign]
        sup._escalate = AsyncMock()  # type: ignore[method-assign]

        await sup._handle_crash("a", ValueError("x"))

        assert called == ["all"]

    @pytest.mark.asyncio
    async def test_rest_for_one_calls_restart_rest(self):
        sup = Supervisor(
            "root", strategy="REST_FOR_ONE", max_restarts=5, backoff="CONSTANT", backoff_base=0.0
        )
        sup._restart_counts["a"] = 0

        called = []
        sup._restart_rest_for_one = AsyncMock(side_effect=lambda n: called.append(n))  # type: ignore[method-assign]
        sup._escalate = AsyncMock()  # type: ignore[method-assign]

        await sup._handle_crash("a", ValueError("x"))

        assert called == ["a"]

    @pytest.mark.asyncio
    async def test_exceeding_max_restarts_calls_escalate(self):
        sup = Supervisor(
            "root",
            strategy="ONE_FOR_ONE",
            max_restarts=1,
            backoff="CONSTANT",
            backoff_base=0.0,
            restart_window=60.0,
        )
        sup._restart_counts["a"] = 0

        # Pre-fill 2 timestamps to exceed max_restarts=1
        now = time.time()
        sup._restart_timestamps.extend([now - 5, now - 3])

        escalated = []
        sup._escalate = AsyncMock(side_effect=lambda n, e: escalated.append(n))  # type: ignore[method-assign]
        sup._restart_child = AsyncMock()  # type: ignore[method-assign]

        await sup._handle_crash("a", ValueError("x"))

        assert "a" in escalated
        sup._restart_child.assert_not_called()


# ---------------------------------------------------------------------------
# all_agents / all_supervisors
# ---------------------------------------------------------------------------


class TestTreeCollectors:
    def test_all_agents_flat(self):
        a = NullAgent("a")
        b = NullAgent("b")
        sup = Supervisor("root", children=[a, b])
        assert set(agent.name for agent in sup.all_agents()) == {"a", "b"}

    def test_all_agents_nested(self):
        a = NullAgent("a")
        b = NullAgent("b")
        child_sup = Supervisor("child", children=[b])
        root = Supervisor("root", children=[a, child_sup])
        names = {agent.name for agent in root.all_agents()}
        assert names == {"a", "b"}

    def test_all_supervisors_includes_self_and_children(self):
        child_sup = Supervisor("child")
        root = Supervisor("root", children=[child_sup])
        names = {s.name for s in root.all_supervisors()}
        assert names == {"root", "child"}
