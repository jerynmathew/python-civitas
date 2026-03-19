"""M1.2 — Supervised Agent testable criteria.

Each test maps to one bullet in the M1.2 milestone.
"""

import asyncio
import time

import pytest

from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message
from agency.process import ProcessStatus


# ------------------------------------------------------------------
# Test agents
# ------------------------------------------------------------------


class AlwaysCrashAgent(AgentProcess):
    """Crashes on every message."""

    async def handle(self, message: Message) -> Message | None:
        raise ValueError("boom")


class CrashOnceAgent(AgentProcess):
    """Crashes on the first message, works after restart."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._crashed = False

    async def handle(self, message: Message) -> Message | None:
        if not self._crashed:
            self._crashed = True
            raise ValueError("first-time crash")
        return self.reply({"status": "ok", "msg": message.payload.get("text", "")})


class CountingAgent(AgentProcess):
    """Tracks how many messages it has handled across restarts."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.handled = 0

    async def handle(self, message: Message) -> Message | None:
        self.handled += 1
        return self.reply({"handled": self.handled})


class TrackingAgent(AgentProcess):
    """Records start count to detect restarts."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.start_count = 0

    async def on_start(self) -> None:
        self.start_count += 1

    async def handle(self, message: Message) -> Message | None:
        return self.reply({"starts": self.start_count})


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


async def test_supervisor_detects_agent_crash():
    """Supervisor detects agent crash (unhandled exception in handle())."""
    agent = CrashOnceAgent("crasher")
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[agent],
            max_restarts=3,
            backoff="CONSTANT",
            backoff_base=0.01,
        )
    )
    await runtime.start()
    try:
        # Send a message that triggers the crash
        await runtime.send("crasher", {"text": "trigger"})
        # Give supervisor time to detect and restart
        await asyncio.sleep(0.15)
        # Agent should have been restarted (back to RUNNING)
        assert agent.status == ProcessStatus.RUNNING
        assert agent._crashed is True  # confirms it did crash
    finally:
        await runtime.stop()


async def test_one_for_one_restarts_only_failed_agent():
    """ONE_FOR_ONE strategy restarts only the failed agent."""
    crasher = CrashOnceAgent("crasher")
    healthy = TrackingAgent("healthy")

    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="ONE_FOR_ONE",
            children=[crasher, healthy],
            max_restarts=3,
            backoff="CONSTANT",
            backoff_base=0.01,
        )
    )
    await runtime.start()
    try:
        # Healthy agent started once
        r = await runtime.ask("healthy", {})
        assert r.payload["starts"] == 1

        # Trigger crash in crasher
        await runtime.send("crasher", {"text": "trigger"})
        await asyncio.sleep(0.15)

        # Crasher restarted, healthy still only started once
        assert crasher.status == ProcessStatus.RUNNING
        r = await runtime.ask("healthy", {})
        assert r.payload["starts"] == 1
    finally:
        await runtime.stop()


async def test_one_for_all_restarts_all_siblings():
    """ONE_FOR_ALL strategy restarts all siblings."""
    crasher = CrashOnceAgent("crasher")
    sibling = TrackingAgent("sibling")

    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="ONE_FOR_ALL",
            children=[crasher, sibling],
            max_restarts=3,
            backoff="CONSTANT",
            backoff_base=0.01,
        )
    )
    await runtime.start()
    try:
        r = await runtime.ask("sibling", {})
        assert r.payload["starts"] == 1

        # Trigger crash — should restart ALL children
        await runtime.send("crasher", {"text": "trigger"})
        await asyncio.sleep(0.15)

        # Sibling should have been restarted (start_count == 2)
        r = await runtime.ask("sibling", {})
        assert r.payload["starts"] == 2
    finally:
        await runtime.stop()


async def test_rest_for_one_restarts_failed_and_downstream():
    """REST_FOR_ONE strategy restarts the failed agent and downstream siblings."""
    upstream = TrackingAgent("upstream")
    crasher = CrashOnceAgent("crasher")
    downstream = TrackingAgent("downstream")

    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            strategy="REST_FOR_ONE",
            children=[upstream, crasher, downstream],
            max_restarts=3,
            backoff="CONSTANT",
            backoff_base=0.01,
        )
    )
    await runtime.start()
    try:
        r_up = await runtime.ask("upstream", {})
        r_down = await runtime.ask("downstream", {})
        assert r_up.payload["starts"] == 1
        assert r_down.payload["starts"] == 1

        # Crash the middle agent — downstream should restart, upstream should not
        await runtime.send("crasher", {"text": "trigger"})
        await asyncio.sleep(0.15)

        r_up = await runtime.ask("upstream", {})
        r_down = await runtime.ask("downstream", {})
        assert r_up.payload["starts"] == 1   # upstream untouched
        assert r_down.payload["starts"] == 2  # downstream restarted
    finally:
        await runtime.stop()


async def test_restart_counter_increments():
    """Restart counter increments correctly."""
    agent = AlwaysCrashAgent("crasher")
    sup = Supervisor(
        "root",
        children=[agent],
        max_restarts=5,
        restart_window=60.0,
        backoff="CONSTANT",
        backoff_base=0.01,
    )
    runtime = Runtime(supervisor=sup)
    await runtime.start()
    try:
        # Trigger 3 crashes
        for _ in range(3):
            await runtime.send("crasher", {"text": "trigger"})
            await asyncio.sleep(0.1)

        assert sup._restart_counts.get("crasher", 0) >= 3
    finally:
        await runtime.stop()


async def test_max_restarts_triggers_escalation():
    """Max restarts limit triggers escalation."""
    agent = AlwaysCrashAgent("crasher")
    sup = Supervisor(
        "root",
        children=[agent],
        max_restarts=2,
        restart_window=60.0,
        backoff="CONSTANT",
        backoff_base=0.01,
    )
    runtime = Runtime(supervisor=sup)
    await runtime.start()
    try:
        # Trigger enough crashes to exceed max_restarts
        for _ in range(4):
            await runtime.send("crasher", {"text": "trigger"})
            await asyncio.sleep(0.1)

        # After exceeding max_restarts, agent should be stopped permanently
        assert agent.status == ProcessStatus.STOPPED
    finally:
        await runtime.stop()


async def test_backoff_delay_applied():
    """Backoff delay is applied between restarts."""
    agent = CrashOnceAgent("crasher")
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[agent],
            max_restarts=3,
            backoff="CONSTANT",
            backoff_base=0.2,  # 200ms delay
        )
    )
    await runtime.start()
    try:
        t0 = time.monotonic()
        await runtime.send("crasher", {"text": "trigger"})
        # Wait for restart to complete (backoff + processing)
        await asyncio.sleep(0.5)
        elapsed = time.monotonic() - t0

        # Restart should have taken at least the backoff delay
        assert elapsed >= 0.2
        assert agent.status == ProcessStatus.RUNNING
    finally:
        await runtime.stop()


async def test_restarted_agent_receives_subsequent_messages():
    """Restarted agent receives subsequent messages normally."""
    agent = CrashOnceAgent("crasher")
    runtime = Runtime(
        supervisor=Supervisor(
            "root",
            children=[agent],
            max_restarts=3,
            backoff="CONSTANT",
            backoff_base=0.01,
        )
    )
    await runtime.start()
    try:
        # Trigger crash
        await runtime.send("crasher", {"text": "trigger"})
        await asyncio.sleep(0.15)

        # Agent should be back and functional
        result = await runtime.ask("crasher", {"text": "hello after restart"})
        assert result.payload["status"] == "ok"
        assert result.payload["msg"] == "hello after restart"
    finally:
        await runtime.stop()
