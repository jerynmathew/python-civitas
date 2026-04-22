"""Unit tests for EvalLoop — EvalAgent, CorrectionSignal, emit_eval, rate limiting."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from civitas import AgentProcess, CorrectionSignal, EvalAgent, EvalEvent, Runtime, Supervisor
from civitas.evalloop import EvalExporter
from civitas.messages import Message
from civitas.process import ProcessStatus
from tests.conftest import wait_for, wait_for_status

# ---------------------------------------------------------------------------
# Concrete implementations for testing
# ---------------------------------------------------------------------------


class PolicyEval(EvalAgent):
    """Halts agents that say 'UNSAFE', redirects 'WARN', nudges 'CAUTION'."""

    async def on_eval_event(self, event: EvalEvent) -> CorrectionSignal | None:
        content = event.payload.get("content", "")
        if "UNSAFE" in content:
            return CorrectionSignal(severity="halt", reason="Policy violation detected")
        if "WARN" in content:
            return CorrectionSignal(severity="redirect", reason="Concerning content")
        if "CAUTION" in content:
            return CorrectionSignal(severity="nudge", reason="Minor concern")
        return None


class RecordingAgent(AgentProcess):
    """Emits an eval event for each message received; records corrections."""

    async def on_start(self) -> None:
        self.state["corrections"] = []
        self.state["messages"] = []

    async def handle(self, message: Message) -> None:
        content = message.payload.get("content", "")
        self.state["messages"].append(message.payload)
        # Forward the content to the EvalAgent for scoring
        await self.emit_eval("llm_output", {"content": content})

    async def on_correction(self, message: Message) -> None:
        self.state["corrections"].append(
            {
                "severity": message.payload.get("severity"),
                "reason": message.payload.get("reason"),
            }
        )


# ---------------------------------------------------------------------------
# EvalEvent and CorrectionSignal
# ---------------------------------------------------------------------------


class TestEvalEvent:
    def test_fields_set_correctly(self):
        event = EvalEvent(
            agent_name="researcher",
            event_type="llm_output",
            payload={"content": "Hello"},
            trace_id="abc",
            message_id="msg-1",
        )
        assert event.agent_name == "researcher"
        assert event.event_type == "llm_output"
        assert event.payload["content"] == "Hello"
        assert event.trace_id == "abc"

    def test_timestamp_defaults_to_now(self):
        before = time.time()
        event = EvalEvent(agent_name="a", event_type="t", payload={})
        after = time.time()
        assert before <= event.timestamp <= after


class TestCorrectionSignal:
    def test_nudge(self):
        sig = CorrectionSignal(severity="nudge", reason="minor issue")
        assert sig.severity == "nudge"
        assert sig.payload == {}

    def test_halt_with_payload(self):
        sig = CorrectionSignal(severity="halt", reason="policy", payload={"rule": "R1"})
        assert sig.severity == "halt"
        assert sig.payload["rule"] == "R1"


# ---------------------------------------------------------------------------
# EvalExporter protocol
# ---------------------------------------------------------------------------


class TestEvalExporter:
    def test_concrete_class_satisfies_protocol(self):
        class MyExporter:
            async def export(self, event: EvalEvent) -> None:
                pass

        assert isinstance(MyExporter(), EvalExporter)

    def test_missing_export_does_not_satisfy_protocol(self):
        class BadExporter:
            pass

        assert not isinstance(BadExporter(), EvalExporter)


# ---------------------------------------------------------------------------
# EvalAgent — on_eval_event dispatch
# ---------------------------------------------------------------------------


class TestEvalAgentDispatch:
    @pytest.mark.asyncio
    async def test_none_result_sends_no_message(self):
        agent = EvalAgent("eval")
        bus = MagicMock()
        bus.route = AsyncMock()
        agent._bus = bus

        msg = Message(
            type="civitas.eval.event",
            sender="worker",
            recipient="eval",
            payload={"agent_name": "worker", "event_type": "llm_output", "content": "safe"},
        )
        await agent.handle(msg)
        bus.route.assert_not_called()

    @pytest.mark.asyncio
    async def test_nudge_sends_correction_not_halt(self):
        agent = PolicyEval("eval")
        bus = MagicMock()
        bus.route = AsyncMock()
        agent._bus = bus

        msg = Message(
            type="civitas.eval.event",
            sender="worker",
            recipient="eval",
            payload={"agent_name": "worker", "event_type": "llm_output", "content": "CAUTION"},
        )
        await agent.handle(msg)
        bus.route.assert_called_once()
        sent: Message = bus.route.call_args[0][0]
        assert sent.type == "civitas.eval.correction"
        assert sent.payload["severity"] == "nudge"
        assert sent.recipient == "worker"

    @pytest.mark.asyncio
    async def test_redirect_sends_correction(self):
        agent = PolicyEval("eval")
        bus = MagicMock()
        bus.route = AsyncMock()
        agent._bus = bus

        msg = Message(
            type="civitas.eval.event",
            sender="worker",
            recipient="eval",
            payload={"agent_name": "worker", "event_type": "llm_output", "content": "WARN here"},
        )
        await agent.handle(msg)
        sent: Message = bus.route.call_args[0][0]
        assert sent.type == "civitas.eval.correction"
        assert sent.payload["severity"] == "redirect"

    @pytest.mark.asyncio
    async def test_halt_sends_halt_message(self):
        agent = PolicyEval("eval")
        bus = MagicMock()
        bus.route = AsyncMock()
        agent._bus = bus

        msg = Message(
            type="civitas.eval.event",
            sender="worker",
            recipient="eval",
            payload={"agent_name": "worker", "event_type": "llm_output", "content": "UNSAFE"},
        )
        await agent.handle(msg)
        sent: Message = bus.route.call_args[0][0]
        assert sent.type == "civitas.eval.halt"
        assert sent.priority == 1
        assert sent.recipient == "worker"

    @pytest.mark.asyncio
    async def test_non_eval_event_messages_ignored(self):
        agent = EvalAgent("eval")
        bus = MagicMock()
        bus.route = AsyncMock()
        agent._bus = bus

        msg = Message(
            type="message",
            sender="other",
            recipient="eval",
            payload={"content": "UNSAFE"},
        )
        await agent.handle(msg)
        bus.route.assert_not_called()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_allows_up_to_max_corrections(self):
        agent = EvalAgent("eval", max_corrections_per_window=3, window_seconds=60.0)
        assert agent._check_rate_limit("target") is True
        assert agent._check_rate_limit("target") is True
        assert agent._check_rate_limit("target") is True
        assert agent._check_rate_limit("target") is False  # 4th is over limit

    def test_independent_windows_per_agent(self):
        agent = EvalAgent("eval", max_corrections_per_window=2, window_seconds=60.0)
        agent._check_rate_limit("agent_a")
        agent._check_rate_limit("agent_a")
        assert agent._check_rate_limit("agent_a") is False
        # Different agent — fresh window
        assert agent._check_rate_limit("agent_b") is True

    def test_resets_after_window(self):
        agent = EvalAgent("eval", max_corrections_per_window=2, window_seconds=0.05)
        agent._check_rate_limit("target")
        agent._check_rate_limit("target")
        assert agent._check_rate_limit("target") is False
        # Fake time passing by backdating the stored timestamps
        agent._correction_timestamps["target"] = [time.time() - 1.0]
        assert agent._check_rate_limit("target") is True

    @pytest.mark.asyncio
    async def test_excess_corrections_are_dropped_not_raised(self):
        agent = PolicyEval("eval", max_corrections_per_window=1, window_seconds=60.0)
        bus = MagicMock()
        bus.route = AsyncMock()
        agent._bus = bus

        msg = Message(
            type="civitas.eval.event",
            sender="worker",
            recipient="eval",
            payload={"agent_name": "worker", "event_type": "x", "content": "UNSAFE"},
        )
        await agent.handle(msg)  # first — sent
        await agent.handle(msg)  # second — rate limited, dropped silently
        assert bus.route.call_count == 1


# ---------------------------------------------------------------------------
# AgentProcess — emit_eval and on_correction
# ---------------------------------------------------------------------------


class TestEmitEval:
    @pytest.mark.asyncio
    async def test_emit_eval_noop_without_bus(self):
        agent = RecordingAgent("worker")
        # _bus is None — should not raise
        await agent.emit_eval("llm_output", {"content": "hello"})

    @pytest.mark.asyncio
    async def test_emit_eval_sends_to_named_eval_agent(self):
        agent = RecordingAgent("worker")
        bus = MagicMock()
        bus.route = AsyncMock()
        bus.lookup = MagicMock(return_value=MagicMock(is_local=True))
        agent._bus = bus

        await agent.emit_eval("llm_output", {"content": "test"}, eval_agent="my_eval")
        bus.route.assert_called_once()
        sent: Message = bus.route.call_args[0][0]
        assert sent.type == "civitas.eval.event"
        assert sent.recipient == "my_eval"
        assert sent.payload["agent_name"] == "worker"
        assert sent.payload["event_type"] == "llm_output"
        assert sent.payload["content"] == "test"


# ---------------------------------------------------------------------------
# Integration — full supervision tree
# ---------------------------------------------------------------------------


class TestEvalLoopIntegration:
    @pytest.mark.asyncio
    async def test_nudge_reaches_on_correction_hook(self):
        eval_agent = PolicyEval("eval_agent")
        worker = RecordingAgent("worker")
        supervisor = Supervisor(name="root", children=[eval_agent, worker])
        runtime = Runtime(supervisor=supervisor)

        await runtime.start()
        # Send a regular message — worker.handle() will call emit_eval(), which
        # sends to eval_agent, which sends a nudge correction back to worker.
        await runtime.send("worker", {"content": "CAUTION here"})
        # Wait for worker to emit eval, eval_agent to respond, worker to receive correction
        await wait_for(
            lambda: len(worker.state.get("corrections", [])) >= 1,
            timeout=2.0,
        )
        await runtime.stop()

        assert worker.state["corrections"][0]["severity"] == "nudge"

    @pytest.mark.asyncio
    async def test_halt_stops_target_agent(self):
        eval_agent = PolicyEval("eval_agent")
        worker = RecordingAgent("worker")
        supervisor = Supervisor(name="root", children=[eval_agent, worker])
        runtime = Runtime(supervisor=supervisor)

        await runtime.start()
        # Send halt-triggering event directly to eval_agent
        await runtime.send(
            "eval_agent",
            {"agent_name": "worker", "event_type": "llm_output", "content": "UNSAFE"},
            message_type="civitas.eval.event",
        )
        await wait_for_status(worker, ProcessStatus.STOPPED, timeout=3.0)
        await runtime.stop()

    @pytest.mark.asyncio
    async def test_type_eval_agent_yaml(self, tmp_path):
        topology = """\
supervision:
  name: root
  strategy: ONE_FOR_ONE
  children:
    - type: eval_agent
      name: my_eval
      max_corrections_per_window: 5
      window_seconds: 30.0
"""
        cfg = tmp_path / "topology.yaml"
        cfg.write_text(topology)

        runtime = Runtime.from_config(cfg)
        agents = runtime.all_agents()
        assert len(agents) == 1
        assert isinstance(agents[0], EvalAgent)
        assert agents[0].name == "my_eval"
        assert agents[0]._max_corrections == 5
        assert agents[0]._window_seconds == 30.0
