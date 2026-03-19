"""Tracer — automatic span creation for message send/receive, LLM calls, and tool invocations.

Uses OpenTelemetry SDK when installed; falls back to a built-in print-based
ConsoleExporter when OTEL is not available. The rest of the runtime does not
know which backend is active.
"""

from __future__ import annotations

import os
import time
from typing import Any

from agency.messages import Message, _uuid7

# ---------------------------------------------------------------------------
# Span abstraction — thin wrapper so callers don't depend on OTEL types
# ---------------------------------------------------------------------------


class Span:
    """Lightweight span that works with or without OTEL."""

    def __init__(
        self,
        name: str,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.attributes: dict[str, Any] = attributes or {}
        self.start_time = time.time()
        self.end_time: float | None = None
        self._otel_span: Any = None  # holds real OTEL span if available

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value
        if self._otel_span is not None:
            self._otel_span.set_attribute(key, value)

    def end(self) -> None:
        self.end_time = time.time()
        if self._otel_span is not None:
            self._otel_span.end()


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

# Try to import OTEL; set a flag for runtime use
_HAS_OTEL = False
try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter as OTELConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    _HAS_OTEL = True
except ImportError:
    pass


def _new_span_id() -> str:
    """Generate a 16-hex-char span ID."""
    return os.urandom(8).hex()


class Tracer:
    """Creates and enriches spans for Agency operations.

    Behaviour depends on the environment:
    - opentelemetry-sdk installed + OTEL_EXPORTER_OTLP_ENDPOINT set -> OTLP exporter
    - opentelemetry-sdk installed, no endpoint -> OTEL ConsoleSpanExporter
    - opentelemetry-sdk not installed -> built-in print-based console output
    """

    def __init__(self) -> None:
        self._use_otel = False
        self._otel_tracer: Any = None
        self._console_fallback = True

        if _HAS_OTEL:
            provider = TracerProvider()
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

            if endpoint:
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )

                    exporter = OTLPSpanExporter(endpoint=endpoint)
                    provider.add_span_processor(SimpleSpanProcessor(exporter))
                except ImportError:
                    # OTLP exporter not installed — fall back to OTEL console
                    provider.add_span_processor(
                        SimpleSpanProcessor(OTELConsoleSpanExporter())
                    )
            else:
                provider.add_span_processor(
                    SimpleSpanProcessor(OTELConsoleSpanExporter())
                )

            otel_trace.set_tracer_provider(provider)
            self._otel_tracer = otel_trace.get_tracer("agency", "0.1.0")
            self._use_otel = True
            self._console_fallback = False

    # ------------------------------------------------------------------
    # Span creation
    # ------------------------------------------------------------------

    def start_send_span(self, message: Message) -> Span:
        """Create a span for an outbound message send."""
        span = Span(
            name=f"send {message.type}",
            trace_id=message.trace_id,
            span_id=message.span_id,
            parent_span_id=message.parent_span_id,
            attributes={
                "agency.sender": message.sender,
                "agency.recipient": message.recipient,
                "agency.message_type": message.type,
                "agency.message_id": message.id,
            },
        )
        if self._use_otel and self._otel_tracer is not None:
            otel_span = self._otel_tracer.start_span(span.name, attributes=span.attributes)
            span._otel_span = otel_span
        elif self._console_fallback:
            ts = time.strftime("%H:%M:%S", time.localtime(span.start_time))
            ms = f"{span.start_time % 1:.3f}"[1:]
            print(f"[{ts}{ms}] {message.sender} -> {message.recipient}: {message.type}")
        return span

    def start_receive_span(self, message: Message) -> Span:
        """Create a span for an inbound message receive."""
        span = Span(
            name=f"recv {message.type}",
            trace_id=message.trace_id,
            span_id=_new_span_id(),
            parent_span_id=message.span_id,
            attributes={
                "agency.sender": message.sender,
                "agency.recipient": message.recipient,
                "agency.message_type": message.type,
                "agency.message_id": message.id,
            },
        )
        if self._use_otel and self._otel_tracer is not None:
            otel_span = self._otel_tracer.start_span(span.name, attributes=span.attributes)
            span._otel_span = otel_span
        return span

    def start_span(
        self,
        name: str,
        trace_id: str = "",
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Create a general-purpose span (for LLM calls, tool invocations, etc)."""
        span = Span(
            name=name,
            trace_id=trace_id or os.urandom(16).hex(),
            span_id=_new_span_id(),
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        if self._use_otel and self._otel_tracer is not None:
            otel_span = self._otel_tracer.start_span(name, attributes=span.attributes)
            span._otel_span = otel_span
        return span

    def start_llm_span(
        self,
        model: str,
        trace_id: str = "",
        parent_span_id: str | None = None,
    ) -> Span:
        """Create a span for an LLM call. Call end_llm_span() after the call completes."""
        span = self.start_span(
            name=f"llm.chat {model}",
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes={"llm.model": model},
        )
        return span

    def end_llm_span(
        self,
        span: Span,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Enrich and close an LLM span with response metrics."""
        span.set_attribute("llm.tokens_in", tokens_in)
        span.set_attribute("llm.tokens_out", tokens_out)
        span.set_attribute("llm.cost_usd", cost_usd)
        latency_ms = (time.time() - span.start_time) * 1000
        span.set_attribute("llm.latency_ms", round(latency_ms, 2))
        span.end()
        if self._console_fallback:
            model = span.attributes.get("llm.model", "?")
            print(
                f"  [llm] {model}: {tokens_in}in/{tokens_out}out "
                f"${cost_usd:.4f} {latency_ms:.0f}ms"
            )

    def start_tool_span(
        self,
        tool_name: str,
        trace_id: str = "",
        parent_span_id: str | None = None,
    ) -> Span:
        """Create a span for a tool invocation."""
        span = self.start_span(
            name=f"tool.execute {tool_name}",
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes={"tool.name": tool_name},
        )
        return span

    def end_tool_span(
        self,
        span: Span,
        *,
        status: str = "ok",
    ) -> None:
        """Enrich and close a tool span with result status."""
        span.set_attribute("tool.result_status", status)
        latency_ms = (time.time() - span.start_time) * 1000
        span.set_attribute("tool.latency_ms", round(latency_ms, 2))
        span.end()
        if self._console_fallback:
            tool_name = span.attributes.get("tool.name", "?")
            print(f"  [tool] {tool_name}: {status} {latency_ms:.0f}ms")

    def new_trace_id(self) -> str:
        """Generate a new trace ID (32-hex-char)."""
        return os.urandom(16).hex()

    def new_span_id(self) -> str:
        """Generate a new span ID (16-hex-char)."""
        return _new_span_id()

    def flush(self) -> None:
        """Force-export any pending spans."""
        if self._use_otel:
            provider = otel_trace.get_tracer_provider()
            if hasattr(provider, "force_flush"):
                provider.force_flush()  # type: ignore[union-attr]
