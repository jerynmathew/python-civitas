"""Observability — tracing, metrics, and span management."""

from __future__ import annotations

from civitas.observability.export_backend import ConsoleBackend, ExportBackend, FanOutBackend
from civitas.observability.otel_agent import run_otel_agent
from civitas.observability.span_queue import SpanData, SpanQueue
from civitas.observability.tracer import Span, Tracer

__all__ = [
    "ConsoleBackend",
    "ExportBackend",
    "FanOutBackend",
    "run_otel_agent",
    "Span",
    "SpanData",
    "SpanQueue",
    "Tracer",
]
