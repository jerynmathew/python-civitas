"""Unit tests for AgentProcess, Mailbox, and message loop behaviour."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from civitas.errors import ErrorAction
from civitas.messages import Message
from civitas.observability.tracer import Span
from civitas.process import AgentProcess, Mailbox, ProcessStatus
from tests.conftest import wait_for

# ---------------------------------------------------------------------------
# Mailbox tests
# ---------------------------------------------------------------------------


async def test_mailbox_put_get_fifo():
    """Normal messages are delivered in FIFO order."""
    mb = Mailbox()
    m1 = Message(type="a")
    m2 = Message(type="b")
    await mb.put(m1)
    await mb.put(m2)
    assert (await mb.get()).type == "a"
    assert (await mb.get()).type == "b"


async def test_mailbox_priority_served_first():
    """Priority messages are served before normal messages."""
    mb = Mailbox()
    normal = Message(type="normal", priority=0)
    high = Message(type="high", priority=1)
    await mb.put(normal)
    await mb.put(high)
    assert (await mb.get()).type == "high"
    assert (await mb.get()).type == "normal"


async def test_mailbox_empty_check():
    """empty() reflects both queues."""
    mb = Mailbox()
    assert mb.empty()
    await mb.put(Message(type="x"))
    assert not mb.empty()
    await mb.get()
    assert mb.empty()


async def test_mailbox_priority_queue_bounded():
    """Priority queue has a finite bound (F02-2)."""
    mb = Mailbox(maxsize=10)
    # Priority queue maxsize is 100 — verify it has a bound by checking it exists
    assert mb._priority_queue.maxsize == 100


# ---------------------------------------------------------------------------
# ProcessStatus — SUSPENDED removed (F02-6)
# ---------------------------------------------------------------------------


def test_suspended_removed_from_enum():
    """SUSPENDED is not in ProcessStatus (F02-6)."""
    names = [s.name for s in ProcessStatus]
    assert "SUSPENDED" not in names


def test_expected_states_present():
    """All expected states are present."""
    names = {s.name for s in ProcessStatus}
    assert names == {"INITIALIZING", "RUNNING", "STOPPING", "STOPPED", "CRASHED"}


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


class TrackingAgent(AgentProcess):
    """Agent that records lifecycle events and received messages."""

    def __init__(self, name: str = "tracker") -> None:
        super().__init__(name)
        self.events: list[str] = []
        self.received: list[Message] = []

    async def on_start(self) -> None:
        self.events.append("start")

    async def handle(self, message: Message) -> Message | None:
        self.events.append(f"handle:{message.type}")
        self.received.append(message)
        return None

    async def on_stop(self) -> None:
        self.events.append("stop")


async def _start_and_stop(agent: AgentProcess) -> None:
    await agent._start()
    await agent._stop()


async def test_on_start_called_before_first_message():
    """on_start() is called once before handle()."""
    agent = TrackingAgent()
    await _start_and_stop(agent)
    assert "start" in agent.events
    assert agent.events.index("start") == 0


async def test_on_stop_called_on_graceful_shutdown():
    """on_stop() is called after graceful shutdown (F02-1)."""
    agent = TrackingAgent()
    await _start_and_stop(agent)
    assert "stop" in agent.events
    assert agent.status == ProcessStatus.STOPPED


async def test_on_stop_called_on_crash():
    """on_stop() is always called — even when the agent crashes (F02-1)."""

    class CrashingAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("crasher")
            self.stop_called = False

        async def on_start(self) -> None:
            raise RuntimeError("on_start crash")

        async def on_stop(self) -> None:
            self.stop_called = True

    agent = CrashingAgent()
    # on_start crash propagates — _start() should raise
    with pytest.raises(RuntimeError, match="on_start crash"):
        await agent._start()
    # on_stop is not called for on_start failures (message loop never ran)
    # But crashes during handle() should call on_stop via the finally block.

    # Second scenario: crash during handle()
    class HandleCrashAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("handle_crasher")
            self.stop_called = False

        async def handle(self, message: Message) -> None:
            raise RuntimeError("handle crash")

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            return ErrorAction.ESCALATE

        async def on_stop(self) -> None:
            self.stop_called = True

    agent2 = HandleCrashAgent()
    await agent2._start()
    await agent2._mailbox.put(Message(type="trigger"))
    # Wait for the loop to crash
    if agent2._task is not None:
        try:
            await asyncio.wait_for(agent2._task, timeout=2.0)
        except (TimeoutError, RuntimeError):
            pass
    assert agent2.stop_called, "on_stop must be called even when agent crashes"
    assert agent2.status == ProcessStatus.CRASHED


async def test_status_transitions():
    """Status follows INITIALIZING → RUNNING → STOPPING → STOPPED."""
    agent = TrackingAgent()
    assert agent.status == ProcessStatus.INITIALIZING
    await agent._start()
    assert agent.status == ProcessStatus.RUNNING
    await agent._stop()
    assert agent.status == ProcessStatus.STOPPED


# ---------------------------------------------------------------------------
# ErrorAction
# ---------------------------------------------------------------------------


async def test_retry_redelivers_message():
    """RETRY puts the message back in the mailbox (F02-3)."""

    class RetryAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("retrier", max_retries=2)
            self.attempts: list[int] = []

        async def handle(self, message: Message) -> None:
            self.attempts.append(message.attempt)
            raise ValueError("transient")

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            if message.attempt < 2:
                return ErrorAction.RETRY
            return ErrorAction.SKIP

    agent = RetryAgent()
    await agent._start()
    await agent._mailbox.put(Message(type="work"))
    await wait_for(lambda: len(agent.attempts) >= 2)
    assert agent.status == ProcessStatus.RUNNING  # SKIP kept it running
    await agent._stop()


async def test_retry_increments_attempt():
    """RETRY increments message.attempt on each re-delivery."""

    class AttemptLogger(AgentProcess):
        def __init__(self) -> None:
            super().__init__("attempt_logger", max_retries=3)
            self.seen_attempts: list[int] = []

        async def handle(self, message: Message) -> None:
            self.seen_attempts.append(message.attempt)
            if message.attempt < 2:
                raise ValueError("retry me")

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            return ErrorAction.RETRY

    agent = AttemptLogger()
    await agent._start()
    await agent._mailbox.put(Message(type="work"))
    await wait_for(lambda: 1 in agent.seen_attempts)
    assert 0 in agent.seen_attempts
    await agent._stop()


async def test_retry_limit_escalates_after_max():
    """Exceeding max_retries escalates instead of looping forever (F02-3)."""

    class AlwaysFailAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("always_fail", max_retries=2)

        async def handle(self, message: Message) -> None:
            raise ValueError("always fails")

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            return ErrorAction.RETRY

    agent = AlwaysFailAgent()
    await agent._start()
    await agent._mailbox.put(Message(type="work"))
    if agent._task is not None:
        try:
            await asyncio.wait_for(agent._task, timeout=2.0)
        except (TimeoutError, ValueError):
            pass
    assert agent.status in (ProcessStatus.CRASHED, ProcessStatus.STOPPED)


async def test_skip_discards_message():
    """SKIP discards the failed message and continues processing."""

    class SkipAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("skipper")
            self.processed: list[str] = []

        async def handle(self, message: Message) -> None:
            if message.type == "bad":
                raise ValueError("skip me")
            self.processed.append(message.type)

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            return ErrorAction.SKIP

    agent = SkipAgent()
    await agent._start()
    await agent._mailbox.put(Message(type="bad"))
    await agent._mailbox.put(Message(type="good"))
    await wait_for(lambda: "good" in agent.processed)
    assert "good" in agent.processed
    assert agent.status == ProcessStatus.RUNNING
    await agent._stop()


async def test_stop_error_action_stops_gracefully():
    """STOP error action transitions to STOPPING."""

    class StopOnErrorAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("stopper")

        async def handle(self, message: Message) -> None:
            raise ValueError("stop please")

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            return ErrorAction.STOP

    agent = StopOnErrorAgent()
    await agent._start()
    await agent._mailbox.put(Message(type="trigger"))
    await wait_for(lambda: agent.status in (ProcessStatus.STOPPING, ProcessStatus.STOPPED))


async def test_escalate_crashes_process():
    """ESCALATE sets status to CRASHED and propagates the exception."""

    class EscalateAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("escalater")

        async def handle(self, message: Message) -> None:
            raise RuntimeError("escalate me")

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            return ErrorAction.ESCALATE

    agent = EscalateAgent()
    await agent._start()
    await agent._mailbox.put(Message(type="trigger"))
    if agent._task is not None:
        try:
            await asyncio.wait_for(agent._task, timeout=2.0)
        except (TimeoutError, RuntimeError):
            pass
    assert agent.status == ProcessStatus.CRASHED


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


def test_reply_outside_handle_raises():
    """reply() raises RuntimeError when called outside of handle()."""
    agent = TrackingAgent()
    with pytest.raises(RuntimeError, match="outside of handle"):
        agent.reply({"type": "reply"})


async def test_send_requires_bus():
    """send() raises RuntimeError when bus is not injected."""
    agent = TrackingAgent()
    with pytest.raises(RuntimeError, match="not wired"):
        await agent.send("someone", {})


# ---------------------------------------------------------------------------
# Configurable shutdown timeout (F02-10)
# ---------------------------------------------------------------------------


def test_configurable_shutdown_timeout():
    """shutdown_timeout param is stored on the agent."""
    agent = AgentProcess("myagent", shutdown_timeout=5.0)
    assert agent._shutdown_timeout == 5.0


def test_default_shutdown_timeout():
    """Default shutdown timeout is 30 seconds."""
    agent = AgentProcess("myagent")
    assert agent._shutdown_timeout == 30.0


# ---------------------------------------------------------------------------
# Observability span context managers (F05-x)
# ---------------------------------------------------------------------------


def _make_agent_with_tracer() -> tuple[TrackingAgent, Any]:
    """Return a TrackingAgent wired with an in-memory test tracer."""
    pytest.importorskip("opentelemetry", reason="opentelemetry-sdk not installed")
    from civitas.plugins.otel import create_test_tracer  # optional dep — gated by importorskip

    agent = TrackingAgent("obs_agent")
    tracer, exporter = create_test_tracer()
    agent._tracer = tracer
    return agent, exporter


def test_llm_span_no_tracer_yields_dummy():
    """llm_span() yields a dummy Span when no tracer is attached."""
    agent = TrackingAgent()
    with agent.llm_span("claude-sonnet") as span:
        assert isinstance(span, Span)


def test_tool_span_no_tracer_yields_dummy():
    """tool_span() yields a dummy Span when no tracer is attached."""
    agent = TrackingAgent()
    with agent.tool_span("web_search") as span:
        assert isinstance(span, Span)


def test_llm_span_with_tracer_creates_span():
    """llm_span() creates a real span when a tracer is attached."""
    agent, exporter = _make_agent_with_tracer()
    agent._current_message = Message(sender="x", recipient="obs_agent", trace_id="t1")
    with agent.llm_span("test-model", tokens_in=100) as span:
        span.set_attribute("civitas.llm.tokens_out", 50)
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "civitas.llm.chat"


def test_tool_span_with_tracer_creates_span():
    """tool_span() creates a real span when a tracer is attached."""
    agent, exporter = _make_agent_with_tracer()
    agent._current_message = Message(sender="x", recipient="obs_agent", trace_id="t1")
    with agent.tool_span("web_search") as span:
        span.set_attribute("result", "ok")
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "civitas.tool.invoke"


def test_llm_span_records_error_on_exception():
    """llm_span() sets error on the span when an exception is raised."""
    agent, exporter = _make_agent_with_tracer()

    with pytest.raises(ValueError, match="llm failed"):
        with agent.llm_span("test-model"):
            raise ValueError("llm failed")
    spans = exporter.get_finished_spans()
    assert len(spans) == 1


def test_tool_span_records_error_on_exception():
    """tool_span() sets error on the span when an exception is raised."""
    agent, exporter = _make_agent_with_tracer()

    with pytest.raises(RuntimeError, match="tool failed"):
        with agent.tool_span("search"):
            raise RuntimeError("tool failed")
    spans = exporter.get_finished_spans()
    assert len(spans) == 1


# ---------------------------------------------------------------------------
# handle() default implementation
# ---------------------------------------------------------------------------


async def test_handle_default_returns_none():
    """AgentProcess.handle() default implementation returns None (line 146)."""
    agent = AgentProcess("bare")
    result = await agent.handle(Message(type="ping"))
    assert result is None


# ---------------------------------------------------------------------------
# Checkpoint with store
# ---------------------------------------------------------------------------


async def test_checkpoint_with_store_persists_state():
    """checkpoint() calls store.set() when a store is configured (line 170)."""
    agent = TrackingAgent()
    mock_store = AsyncMock()
    agent.store = mock_store
    agent.state = {"key": "value"}

    await agent.checkpoint()

    mock_store.set.assert_awaited_once_with("tracker", {"key": "value"})


async def test_checkpoint_without_store_is_noop():
    """checkpoint() is a no-op when store is None (branch 169->exit)."""
    agent = TrackingAgent()
    # store is None by default
    await agent.checkpoint()  # must not raise


# ---------------------------------------------------------------------------
# send() and ask() with current_message context
# ---------------------------------------------------------------------------


async def test_send_propagates_trace_from_current_message():
    """send() uses trace_id/span_id from _current_message (lines 194-196)."""
    agent = TrackingAgent()
    mock_bus = MagicMock()
    mock_bus.route = AsyncMock()
    agent._bus = mock_bus

    # Set a current message to exercise the trace propagation branch
    agent._current_message = Message(
        type="incoming", sender="other", trace_id="trace-abc", span_id="span-xyz"
    )
    await agent.send("somewhere", {"data": 1})

    call_args = mock_bus.route.call_args[0][0]
    assert call_args.trace_id == "trace-abc"
    assert call_args.parent_span_id == "span-xyz"


async def test_send_without_current_message_uses_empty_trace():
    """send() with no _current_message uses empty trace (branch 194->198)."""
    agent = TrackingAgent()
    mock_bus = MagicMock()
    mock_bus.route = AsyncMock()
    agent._bus = mock_bus
    # _current_message is None by default

    await agent.send("somewhere", {"data": 1})

    call_args = mock_bus.route.call_args[0][0]
    assert call_args.trace_id == ""
    assert call_args.parent_span_id is None


async def test_ask_requires_bus():
    """ask() raises RuntimeError when bus is not injected (line 218)."""
    agent = TrackingAgent()
    with pytest.raises(RuntimeError, match="not wired"):
        await agent.ask("target", {})


async def test_ask_propagates_trace_from_current_message():
    """ask() uses trace_id/span_id from _current_message (lines 221-223)."""
    agent = TrackingAgent()
    mock_bus = MagicMock()
    reply_msg = Message(type="reply", sender="target", recipient="tracker")
    mock_bus.request = AsyncMock(return_value=reply_msg)
    agent._bus = mock_bus

    agent._current_message = Message(
        type="incoming", sender="other", trace_id="trace-ask", span_id="span-ask"
    )
    result = await agent.ask("target", {"q": 1})

    sent = mock_bus.request.call_args[0][0]
    assert sent.trace_id == "trace-ask"
    assert sent.parent_span_id == "span-ask"
    assert result is reply_msg


async def test_ask_without_current_message_uses_empty_trace():
    """ask() with no _current_message uses empty trace (branch 221->225)."""
    agent = TrackingAgent()
    mock_bus = MagicMock()
    reply_msg = Message(type="reply", sender="target", recipient="tracker")
    mock_bus.request = AsyncMock(return_value=reply_msg)
    agent._bus = mock_bus
    # _current_message is None by default

    await agent.ask("target", {"q": 1})

    sent = mock_bus.request.call_args[0][0]
    assert sent.trace_id == ""
    assert sent.parent_span_id is None


async def test_broadcast_requires_bus():
    """broadcast() raises RuntimeError when bus is not injected (line 241)."""
    agent = TrackingAgent()
    with pytest.raises(RuntimeError, match="not wired"):
        await agent.broadcast("*", {})


# ---------------------------------------------------------------------------
# Heartbeat auto-response
# ---------------------------------------------------------------------------


async def test_heartbeat_auto_response():
    """_agency.heartbeat messages receive an _agency.heartbeat_ack reply (lines 372-379)."""
    agent = TrackingAgent()
    mock_bus = MagicMock()
    mock_bus.route = AsyncMock()
    agent._bus = mock_bus

    await agent._start()
    hb = Message(
        type="_agency.heartbeat",
        sender="supervisor",
        recipient="tracker",
        reply_to="supervisor",
        correlation_id="hb-1",
    )
    await agent._mailbox.put(hb)
    await wait_for(lambda: mock_bus.route.called)

    routed = mock_bus.route.call_args[0][0]
    assert routed.type == "_agency.heartbeat_ack"
    assert routed.correlation_id == "hb-1"
    await agent._stop()


async def test_heartbeat_without_bus_continues_loop():
    """Heartbeat with no bus still continues (branch 371->380: bus is None)."""
    agent = TrackingAgent()
    # _bus intentionally left as None

    await agent._start()
    hb = Message(
        type="_agency.heartbeat",
        sender="supervisor",
        recipient="tracker",
        correlation_id="hb-2",
    )
    await agent._mailbox.put(hb)
    # Send a normal message after the heartbeat so we know the loop continued
    await agent._mailbox.put(Message(type="ping"))
    await wait_for(lambda: "handle:ping" in agent.events)
    await agent._stop()


async def test_stop_noop_when_never_started():
    """_stop() is a no-op when the agent was never started (branch 491->exit)."""
    agent = TrackingAgent()
    # _task is None, _status is INITIALIZING
    await agent._stop()
    # No exception — idempotent


# ---------------------------------------------------------------------------
# Retry span emitted with tracer
# ---------------------------------------------------------------------------


async def test_retry_emits_span_when_tracer_set():
    """RETRY action emits a civitas.agent.retry span when a tracer is attached (lines 459-470)."""
    pytest.importorskip("opentelemetry", reason="opentelemetry-sdk not installed")
    from civitas.plugins.otel import create_test_tracer

    class RetryOnceAgent(AgentProcess):
        def __init__(self) -> None:
            super().__init__("retrier", max_retries=3)
            self.count = 0

        async def handle(self, message: Message) -> None:
            self.count += 1
            if self.count == 1:
                raise ValueError("first attempt fails")

        async def on_error(self, error: Exception, message: Message) -> ErrorAction:
            return ErrorAction.RETRY

    agent = RetryOnceAgent()
    tracer, exporter = create_test_tracer()
    agent._tracer = tracer

    await agent._start()
    await agent._mailbox.put(Message(type="work"))
    await wait_for(lambda: agent.count >= 2)
    await agent._stop()

    span_names = [s.name for s in exporter.get_finished_spans()]
    assert any("retry" in n for n in span_names), f"Expected retry span, got: {span_names}"
