"""ExportBackend — protocol and built-in implementations for span export."""

from __future__ import annotations

import logging
from typing import Protocol

from agency.observability.span_queue import SpanData

logger = logging.getLogger(__name__)


class ExportBackend(Protocol):
    """Receives batches of completed spans and ships them to a backend."""

    async def export(self, spans: list[SpanData]) -> None:
        """Export a batch of completed spans."""
        ...

    async def shutdown(self) -> None:
        """Flush any pending data and close connections."""
        ...


class ConsoleBackend:
    """Prints a human-readable summary of each span to stdout via logging."""

    async def export(self, spans: list[SpanData]) -> None:
        for span in spans:
            duration_ms = (span.end_time - span.start_time) * 1000
            if span.status == "error":
                logger.info(
                    "[span] %s  %.1fms  ERROR: %s",
                    span.name, duration_ms, span.error_message or "",
                )
            else:
                logger.info("[span] %s  %.1fms", span.name, duration_ms)

    async def shutdown(self) -> None:
        pass


class FanOutBackend:
    """Exports spans to multiple backends in sequence.

    Errors from one backend are logged and do not prevent others from running.
    """

    def __init__(self, backends: list[ExportBackend]) -> None:
        self._backends = backends

    async def export(self, spans: list[SpanData]) -> None:
        for backend in self._backends:
            try:
                await backend.export(spans)
            except Exception:  # noqa: BLE001
                logger.exception("ExportBackend %r raised during export", backend)

    async def shutdown(self) -> None:
        for backend in self._backends:
            try:
                await backend.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception("ExportBackend %r raised during shutdown", backend)
