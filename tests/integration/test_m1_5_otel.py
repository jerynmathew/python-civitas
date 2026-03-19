"""M1.5 — Automatic Observability testable criteria.

Uses InMemorySpanExporter to capture and validate OTEL spans.
Console fallback tests use capsys to verify print output.
"""

import time
from typing import Any

import pytest

from agency.messages import Message
from agency.observability.tracer import Tracer, _new_span_id

# Try to import OTEL test utilities
_HAS_OTEL = False
try:
    from agency.plugins.otel import create_test_tracer

    _HAS_OTEL = True
except ImportError:
    pass


# ------------------------------------------------------------------
# OTEL span tests (require opentelemetry-sdk)
# ------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_OTEL, reason="opentelemetry-sdk not installed")
async def test_send_receive_spans_have_enrichment():
    """Send/receive spans include agency.sender, agency.recipient attributes."""
    tracer, exporter = create_test_tracer()

    msg = Message(
        type="test_msg",
        sender="agent_a",
        recipient="agent_b",
        trace_id="abc123",
        span_id=_new_span_id(),
    )

    send_span = tracer.start_send_span(msg)
    send_span.end()

    recv_span = tracer.start_receive_span(msg)
    recv_span.end()

    spans = exporter.get_finished_spans()
    assert len(spans) == 2

    # Check send span attributes
    send_attrs = dict(spans[0].attributes)
    assert send_attrs["agency.sender"] == "agent_a"
    assert send_attrs["agency.recipient"] == "agent_b"
    assert send_attrs["agency.message_type"] == "test_msg"

    # Check receive span attributes
    recv_attrs = dict(spans[1].attributes)
    assert recv_attrs["agency.sender"] == "agent_a"
    assert recv_attrs["agency.recipient"] == "agent_b"


@pytest.mark.skipif(not _HAS_OTEL, reason="opentelemetry-sdk not installed")
async def test_llm_span_has_token_counts():
    """LLM call generates a span with token counts, latency, and cost."""
    tracer, exporter = create_test_tracer()

    span = tracer.start_llm_span("test-model", trace_id="trace1")
    time.sleep(0.01)  # ensure measurable latency
    tracer.end_llm_span(span, tokens_in=10, tokens_out=20, cost_usd=0.001)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1

    attrs = dict(spans[0].attributes)
    assert attrs["llm.model"] == "test-model"
    assert attrs["llm.tokens_in"] == 10
    assert attrs["llm.tokens_out"] == 20
    assert attrs["llm.cost_usd"] == 0.001
    assert "llm.latency_ms" in attrs
    assert attrs["llm.latency_ms"] >= 5  # at least ~10ms


@pytest.mark.skipif(not _HAS_OTEL, reason="opentelemetry-sdk not installed")
async def test_tool_span_has_result_status():
    """Tool invocation generates a span with tool.result_status."""
    tracer, exporter = create_test_tracer()

    span = tracer.start_tool_span("web_search", trace_id="trace2")
    tracer.end_tool_span(span, status="ok")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1

    attrs = dict(spans[0].attributes)
    assert attrs["tool.name"] == "web_search"
    assert attrs["tool.result_status"] == "ok"
    assert "tool.latency_ms" in attrs


@pytest.mark.skipif(not _HAS_OTEL, reason="opentelemetry-sdk not installed")
async def test_tool_span_error_status():
    """Tool span captures error status."""
    tracer, exporter = create_test_tracer()

    span = tracer.start_tool_span("failing_tool", trace_id="trace3")
    tracer.end_tool_span(span, status="error")

    spans = exporter.get_finished_spans()
    attrs = dict(spans[0].attributes)
    assert attrs["tool.result_status"] == "error"


# ------------------------------------------------------------------
# Console fallback tests (no OTEL required)
# ------------------------------------------------------------------


def _make_console_tracer() -> Tracer:
    """Create a Tracer with console fallback (no OTEL)."""
    tracer = Tracer.__new__(Tracer)
    tracer._use_otel = False
    tracer._otel_tracer = None
    tracer._console_fallback = True
    return tracer


async def test_console_fallback_send_format(capsys):
    """Console exporter prints 'sender -> recipient: type' for sends."""
    tracer = _make_console_tracer()

    msg = Message(
        type="test_msg",
        sender="agent_a",
        recipient="agent_b",
        trace_id="abc123",
        span_id=_new_span_id(),
    )
    span = tracer.start_send_span(msg)
    span.end()

    captured = capsys.readouterr()
    assert "agent_a -> agent_b: test_msg" in captured.out


async def test_console_fallback_llm_format(capsys):
    """Console exporter prints LLM summary line."""
    tracer = _make_console_tracer()

    span = tracer.start_llm_span("claude-test")
    tracer.end_llm_span(span, tokens_in=100, tokens_out=50, cost_usd=0.005)

    captured = capsys.readouterr()
    assert "[llm]" in captured.out
    assert "claude-test" in captured.out
    assert "100in/50out" in captured.out
    assert "$0.0050" in captured.out


async def test_console_fallback_tool_format(capsys):
    """Console exporter prints tool summary line."""
    tracer = _make_console_tracer()

    span = tracer.start_tool_span("web_search")
    tracer.end_tool_span(span, status="ok")

    captured = capsys.readouterr()
    assert "[tool]" in captured.out
    assert "web_search" in captured.out
    assert "ok" in captured.out
