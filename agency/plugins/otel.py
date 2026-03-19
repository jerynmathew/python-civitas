"""OTELExporter — convenience helpers for OpenTelemetry integration.

The actual OTEL setup happens in ``agency.observability.tracer.Tracer.__init__()``
which auto-detects the opentelemetry-sdk at import time. This module provides
helpers for tests and custom configurations.

Requires ``pip install python-agency[otel]``.
"""

from __future__ import annotations

from typing import Any


def create_test_tracer() -> tuple[Any, Any]:
    """Create a Tracer backed by InMemorySpanExporter for testing.

    Returns (tracer, exporter) where exporter.get_finished_spans() gives
    all exported spans.

    Uses a standalone TracerProvider (not the global one) to avoid conflicts
    between tests.

    Raises ImportError if opentelemetry-sdk is not installed.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from agency.observability.tracer import Tracer

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = Tracer.__new__(Tracer)
    tracer._use_otel = True
    tracer._console_fallback = False
    tracer._otel_tracer = provider.get_tracer("agency.test", "0.1.0")

    return tracer, exporter
