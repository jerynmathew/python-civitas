"""Unit tests for M2.6 — Remote Eval Exporters.

All tests mock the underlying platform SDKs so no real API keys or
network connections are required.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from civitas.evalloop import CorrectionSignal, EvalAgent, EvalEvent, EvalExporter
from civitas.messages import Message

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_event(
    agent_name: str = "agent-a",
    event_type: str = "output",
    payload: dict[str, Any] | None = None,
) -> EvalEvent:
    return EvalEvent(
        agent_name=agent_name,
        event_type=event_type,
        payload=payload or {"content": "hello"},
        trace_id="trace-1",
        message_id="msg-1",
    )


def _eval_message(event_type: str = "output", payload: dict[str, Any] | None = None) -> Message:
    return Message(
        type="civitas.eval.event",
        sender="agent-a",
        recipient="eval",
        payload={
            "agent_name": "agent-a",
            "event_type": event_type,
            **(payload or {"content": "hello"}),
        },
    )


# ---------------------------------------------------------------------------
# EvalExporter protocol conformance
# ---------------------------------------------------------------------------


class TestEvalExporterProtocol:
    def test_protocol_is_runtime_checkable(self):
        class GoodExporter:
            async def export(self, event: EvalEvent) -> None:
                pass

        assert isinstance(GoodExporter(), EvalExporter)

    def test_object_without_export_method_is_not_exporter(self):
        class BadExporter:
            def process(self, event: EvalEvent) -> None:
                pass

        assert not isinstance(BadExporter(), EvalExporter)


# ---------------------------------------------------------------------------
# EvalAgent exporter registration and dispatch
# ---------------------------------------------------------------------------


class TestEvalAgentExporters:
    @pytest.mark.asyncio
    async def test_single_exporter_called_on_event(self):
        exporter = MagicMock()
        exporter.export = AsyncMock()
        agent = EvalAgent("eval", exporters=[exporter])
        agent._bus = MagicMock()
        agent._bus.route = AsyncMock()

        await agent.handle(_eval_message())

        exporter.export.assert_called_once()
        event_arg: EvalEvent = exporter.export.call_args[0][0]
        assert event_arg.agent_name == "agent-a"
        assert event_arg.event_type == "output"

    @pytest.mark.asyncio
    async def test_multiple_exporters_all_called(self):
        exp1 = MagicMock()
        exp1.export = AsyncMock()
        exp2 = MagicMock()
        exp2.export = AsyncMock()
        agent = EvalAgent("eval", exporters=[exp1, exp2])

        await agent.handle(_eval_message())

        exp1.export.assert_called_once()
        exp2.export.assert_called_once()

    @pytest.mark.asyncio
    async def test_exporter_error_does_not_crash_eval_loop(self):
        failing = MagicMock()
        failing.export = AsyncMock(side_effect=RuntimeError("network down"))
        agent = EvalAgent("eval", exporters=[failing])

        await agent.handle(_eval_message())  # must not raise

    @pytest.mark.asyncio
    async def test_exporters_called_even_when_no_correction(self):
        exporter = MagicMock()
        exporter.export = AsyncMock()
        agent = EvalAgent("eval", exporters=[exporter])
        # Default on_eval_event returns None (no correction)

        await agent.handle(_eval_message())

        exporter.export.assert_called_once()

    @pytest.mark.asyncio
    async def test_exporters_called_when_correction_is_issued(self):
        exporter = MagicMock()
        exporter.export = AsyncMock()

        class HaltEval(EvalAgent):
            async def on_eval_event(self, event: EvalEvent) -> CorrectionSignal | None:
                return CorrectionSignal(severity="nudge", reason="test")

        agent = HaltEval("eval", exporters=[exporter])
        agent._bus = MagicMock()
        agent._bus.route = AsyncMock()

        await agent.handle(_eval_message())

        exporter.export.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_eval_message_skips_exporters(self):
        exporter = MagicMock()
        exporter.export = AsyncMock()
        agent = EvalAgent("eval", exporters=[exporter])

        msg = Message(type="message", sender="x", recipient="eval", payload={})
        await agent.handle(msg)

        exporter.export.assert_not_called()

    @pytest.mark.asyncio
    async def test_exporter_receives_correct_event_fields(self):
        captured: list[EvalEvent] = []

        class CapturingExporter:
            async def export(self, event: EvalEvent) -> None:
                captured.append(event)

        agent = EvalAgent("eval", exporters=[CapturingExporter()])
        msg = _eval_message(event_type="decision", payload={"score": 0.9})
        await agent.handle(msg)

        assert len(captured) == 1
        ev = captured[0]
        assert ev.agent_name == "agent-a"
        assert ev.event_type == "decision"
        assert ev.payload["score"] == 0.9

    def test_no_exporters_by_default(self):
        agent = EvalAgent("eval")
        assert agent._exporters == []


# ---------------------------------------------------------------------------
# ArizeExporter
# ---------------------------------------------------------------------------


class TestArizeExporter:
    def _make_arize(self) -> Any:
        from civitas.eval.exporters import ArizeExporter

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        exporter = ArizeExporter.__new__(ArizeExporter)
        exporter._tracer = mock_tracer
        return exporter, mock_tracer, mock_span

    @pytest.mark.asyncio
    async def test_export_opens_span_with_event_type(self):
        exporter, tracer, _ = self._make_arize()
        await exporter.export(_make_event(event_type="output"))
        tracer.start_as_current_span.assert_called_once_with("civitas.eval.output")

    @pytest.mark.asyncio
    async def test_export_sets_agent_name_attribute(self):
        exporter, _, span = self._make_arize()
        await exporter.export(_make_event(agent_name="my-agent"))
        calls = {c.args[0]: c.args[1] for c in span.set_attribute.call_args_list}
        assert calls.get("gen_ai.agent.name") == "my-agent"

    @pytest.mark.asyncio
    async def test_export_sets_trace_id_attribute(self):
        exporter, _, span = self._make_arize()
        event = _make_event()
        event.trace_id = "trace-xyz"
        await exporter.export(event)
        calls = {c.args[0]: c.args[1] for c in span.set_attribute.call_args_list}
        assert calls.get("civitas.eval.trace_id") == "trace-xyz"

    @pytest.mark.asyncio
    async def test_export_propagates_scalar_payload_fields(self):
        exporter, _, span = self._make_arize()
        await exporter.export(_make_event(payload={"score": 0.9, "label": "ok"}))
        attr_keys = {c.args[0] for c in span.set_attribute.call_args_list}
        assert "civitas.eval.payload.score" in attr_keys
        assert "civitas.eval.payload.label" in attr_keys

    @pytest.mark.asyncio
    async def test_export_skips_non_scalar_payload_fields(self):
        exporter, _, span = self._make_arize()
        await exporter.export(_make_event(payload={"nested": {"a": 1}}))
        attr_keys = {c.args[0] for c in span.set_attribute.call_args_list}
        assert "civitas.eval.payload.nested" not in attr_keys

    def test_raises_import_error_when_otel_missing(self):
        with patch.dict("sys.modules", {"opentelemetry": None}):
            from civitas.eval import exporters as mod

            with pytest.raises(ImportError, match="civitas\\[arize\\]"):
                mod.ArizeExporter()


# ---------------------------------------------------------------------------
# LangfuseExporter
# ---------------------------------------------------------------------------


class TestLangfuseExporter:
    def _make_langfuse(self) -> Any:
        from civitas.eval.exporters import LangfuseExporter

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace

        exporter = LangfuseExporter.__new__(LangfuseExporter)
        exporter._client = mock_client
        return exporter, mock_client, mock_trace

    @pytest.mark.asyncio
    async def test_export_creates_trace(self):
        exporter, client, _ = self._make_langfuse()
        await exporter.export(_make_event())
        client.trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_trace_name_includes_event_type(self):
        exporter, client, _ = self._make_langfuse()
        await exporter.export(_make_event(event_type="decision"))
        kwargs = client.trace.call_args.kwargs
        assert kwargs["name"] == "civitas.decision"

    @pytest.mark.asyncio
    async def test_export_trace_id_passed(self):
        exporter, client, _ = self._make_langfuse()
        event = _make_event()
        event.trace_id = "tid-99"
        await exporter.export(event)
        kwargs = client.trace.call_args.kwargs
        assert kwargs["id"] == "tid-99"

    @pytest.mark.asyncio
    async def test_export_creates_generation_on_trace(self):
        exporter, _, trace = self._make_langfuse()
        await exporter.export(_make_event())
        trace.generation.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_generation_includes_payload(self):
        exporter, _, trace = self._make_langfuse()
        await exporter.export(_make_event(payload={"content": "hello world"}))
        kwargs = trace.generation.call_args.kwargs
        assert kwargs["input"]["content"] == "hello world"

    def test_raises_import_error_when_langfuse_missing(self):
        with patch.dict("sys.modules", {"langfuse": None}):
            from civitas.eval import exporters as mod

            with pytest.raises(ImportError, match="civitas\\[langfuse\\]"):
                mod.LangfuseExporter(public_key="pk", secret_key="sk")


# ---------------------------------------------------------------------------
# BraintrustExporter
# ---------------------------------------------------------------------------


class TestBraintrustExporter:
    def _make_braintrust(self) -> Any:
        from civitas.eval.exporters import BraintrustExporter

        mock_logger = MagicMock()
        exporter = BraintrustExporter.__new__(BraintrustExporter)
        exporter._logger = mock_logger
        return exporter, mock_logger

    @pytest.mark.asyncio
    async def test_export_calls_log(self):
        exporter, logger = self._make_braintrust()
        await exporter.export(_make_event())
        logger.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_passes_payload_as_input(self):
        exporter, logger = self._make_braintrust()
        await exporter.export(_make_event(payload={"result": "pass"}))
        kwargs = logger.log.call_args.kwargs
        assert kwargs["input"]["result"] == "pass"

    @pytest.mark.asyncio
    async def test_export_metadata_includes_agent_name(self):
        exporter, logger = self._make_braintrust()
        await exporter.export(_make_event(agent_name="scorer"))
        kwargs = logger.log.call_args.kwargs
        assert kwargs["metadata"]["agent_name"] == "scorer"

    @pytest.mark.asyncio
    async def test_export_metadata_includes_event_type(self):
        exporter, logger = self._make_braintrust()
        await exporter.export(_make_event(event_type="score"))
        kwargs = logger.log.call_args.kwargs
        assert kwargs["metadata"]["event_type"] == "score"

    @pytest.mark.asyncio
    async def test_export_metadata_includes_trace_id(self):
        exporter, logger = self._make_braintrust()
        event = _make_event()
        event.trace_id = "t-42"
        await exporter.export(event)
        kwargs = logger.log.call_args.kwargs
        assert kwargs["metadata"]["trace_id"] == "t-42"

    def test_raises_import_error_when_braintrust_missing(self):
        with patch.dict("sys.modules", {"braintrust": None}):
            from civitas.eval import exporters as mod

            with pytest.raises(ImportError, match="civitas\\[braintrust\\]"):
                mod.BraintrustExporter(api_key="key")


# ---------------------------------------------------------------------------
# LangSmithExporter
# ---------------------------------------------------------------------------


class TestLangSmithExporter:
    def _make_langsmith(self, project: str = "civitas") -> Any:
        from civitas.eval.exporters import LangSmithExporter

        mock_client = MagicMock()
        exporter = LangSmithExporter.__new__(LangSmithExporter)
        exporter._client = mock_client
        exporter._project = project
        return exporter, mock_client

    @pytest.mark.asyncio
    async def test_export_calls_create_run(self):
        exporter, client = self._make_langsmith()
        await exporter.export(_make_event())
        client.create_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_run_name_is_event_type(self):
        exporter, client = self._make_langsmith()
        await exporter.export(_make_event(event_type="policy_check"))
        kwargs = client.create_run.call_args.kwargs
        assert kwargs["name"] == "policy_check"

    @pytest.mark.asyncio
    async def test_export_project_name_passed(self):
        exporter, client = self._make_langsmith(project="my-project")
        await exporter.export(_make_event())
        kwargs = client.create_run.call_args.kwargs
        assert kwargs["project_name"] == "my-project"

    @pytest.mark.asyncio
    async def test_export_inputs_is_payload(self):
        exporter, client = self._make_langsmith()
        await exporter.export(_make_event(payload={"answer": "42"}))
        kwargs = client.create_run.call_args.kwargs
        assert kwargs["inputs"]["answer"] == "42"

    @pytest.mark.asyncio
    async def test_export_extra_includes_agent_name(self):
        exporter, client = self._make_langsmith()
        await exporter.export(_make_event(agent_name="policy-bot"))
        kwargs = client.create_run.call_args.kwargs
        assert kwargs["extra"]["agent_name"] == "policy-bot"

    def test_raises_import_error_when_langsmith_missing(self):
        with patch.dict("sys.modules", {"langsmith": None}):
            from civitas.eval import exporters as mod

            with pytest.raises(ImportError, match="civitas\\[langsmith\\]"):
                mod.LangSmithExporter(api_key="key")


# ---------------------------------------------------------------------------
# FiddlerExporter
# ---------------------------------------------------------------------------


class TestFiddlerExporter:
    def _make_fiddler(self) -> Any:
        from civitas.eval.exporters import FiddlerExporter

        mock_client = MagicMock()
        exporter = FiddlerExporter.__new__(FiddlerExporter)
        exporter._client = mock_client
        exporter._project_id = "proj-1"
        exporter._model_id = "model-1"
        return exporter, mock_client

    @pytest.mark.asyncio
    async def test_export_calls_publish_event(self):
        exporter, client = self._make_fiddler()
        await exporter.export(_make_event())
        client.publish_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_passes_project_and_model_ids(self):
        exporter, client = self._make_fiddler()
        await exporter.export(_make_event())
        kwargs = client.publish_event.call_args.kwargs
        assert kwargs["project_id"] == "proj-1"
        assert kwargs["model_id"] == "model-1"

    @pytest.mark.asyncio
    async def test_export_event_row_includes_agent_name(self):
        exporter, client = self._make_fiddler()
        await exporter.export(_make_event(agent_name="guard"))
        kwargs = client.publish_event.call_args.kwargs
        assert kwargs["event"]["agent_name"] == "guard"

    @pytest.mark.asyncio
    async def test_export_event_row_includes_event_type(self):
        exporter, client = self._make_fiddler()
        await exporter.export(_make_event(event_type="anomaly"))
        kwargs = client.publish_event.call_args.kwargs
        assert kwargs["event"]["event_type"] == "anomaly"

    @pytest.mark.asyncio
    async def test_export_event_row_includes_payload_fields(self):
        exporter, client = self._make_fiddler()
        await exporter.export(_make_event(payload={"risk": 0.7}))
        kwargs = client.publish_event.call_args.kwargs
        assert kwargs["event"]["risk"] == 0.7

    def test_raises_import_error_when_fiddler_missing(self):
        with patch.dict("sys.modules", {"fiddler": None}):
            from civitas.eval import exporters as mod

            with pytest.raises(ImportError, match="civitas\\[fiddler\\]"):
                mod.FiddlerExporter(
                    url="http://x", token="t", org_id="o", project_id="p", model_id="m"
                )


# ---------------------------------------------------------------------------
# Topology YAML — exporter instantiation via Runtime.from_config
# ---------------------------------------------------------------------------


class TestRuntimeExporterYaml:
    def test_arize_exporter_built_from_yaml(self, tmp_path: Path):
        topology = textwrap.dedent("""\
            supervision:
              name: root
              strategy: ONE_FOR_ONE
              children:
                - type: eval_agent
                  name: eval
                  exporters:
                    - type: arize
                      endpoint: "http://localhost:6006/v1/traces"
                      service_name: "test-svc"
        """)
        cfg = tmp_path / "t.yaml"
        cfg.write_text(topology)

        with (
            patch("civitas.eval.exporters.ArizeExporter.__init__", return_value=None) as mock_init,
        ):
            from civitas import Runtime

            Runtime.from_config(cfg)
            mock_init.assert_called_once_with(
                endpoint="http://localhost:6006/v1/traces",
                service_name="test-svc",
            )

    def test_langfuse_exporter_built_from_yaml(self, tmp_path: Path):
        topology = textwrap.dedent("""\
            supervision:
              name: root
              strategy: ONE_FOR_ONE
              children:
                - type: eval_agent
                  name: eval
                  exporters:
                    - type: langfuse
                      public_key: "pk-abc"
                      secret_key: "sk-abc"
                      host: "https://eu.cloud.langfuse.com"
        """)
        cfg = tmp_path / "t.yaml"
        cfg.write_text(topology)

        with (
            patch(
                "civitas.eval.exporters.LangfuseExporter.__init__", return_value=None
            ) as mock_init,
        ):
            from civitas import Runtime

            Runtime.from_config(cfg)
            mock_init.assert_called_once_with(
                public_key="pk-abc",
                secret_key="sk-abc",
                host="https://eu.cloud.langfuse.com",
            )

    def test_unknown_exporter_type_is_skipped(self, tmp_path: Path):
        topology = textwrap.dedent("""\
            supervision:
              name: root
              strategy: ONE_FOR_ONE
              children:
                - type: eval_agent
                  name: eval
                  exporters:
                    - type: unknown_platform
        """)
        cfg = tmp_path / "t.yaml"
        cfg.write_text(topology)

        from civitas import Runtime

        runtime = Runtime.from_config(cfg)
        eval_agent = runtime.all_agents()[0]
        assert isinstance(eval_agent, EvalAgent)
        assert eval_agent._exporters == []

    def test_no_exporters_key_yields_empty_list(self, tmp_path: Path):
        topology = textwrap.dedent("""\
            supervision:
              name: root
              strategy: ONE_FOR_ONE
              children:
                - type: eval_agent
                  name: eval
        """)
        cfg = tmp_path / "t.yaml"
        cfg.write_text(topology)

        from civitas import Runtime

        runtime = Runtime.from_config(cfg)
        eval_agent = runtime.all_agents()[0]
        assert eval_agent._exporters == []

    def test_multiple_exporters_built_from_yaml(self, tmp_path: Path):
        topology = textwrap.dedent("""\
            supervision:
              name: root
              strategy: ONE_FOR_ONE
              children:
                - type: eval_agent
                  name: eval
                  exporters:
                    - type: braintrust
                      api_key: "bt-key"
                    - type: langsmith
                      api_key: "ls-key"
                      project: "my-proj"
        """)
        cfg = tmp_path / "t.yaml"
        cfg.write_text(topology)

        with (
            patch("civitas.eval.exporters.BraintrustExporter.__init__", return_value=None),
            patch("civitas.eval.exporters.LangSmithExporter.__init__", return_value=None),
        ):
            from civitas import Runtime

            runtime = Runtime.from_config(cfg)
            eval_agent = runtime.all_agents()[0]
            assert len(eval_agent._exporters) == 2
