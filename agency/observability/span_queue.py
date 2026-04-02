"""SpanQueue — non-blocking span emission decoupled from export."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any


@dataclasses.dataclass
class SpanData:
    """Completed span ready for export. All fields are plain Python types."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_time: float  # Unix timestamp
    end_time: float  # Unix timestamp
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    status: str = "ok"  # "ok" | "error"
    error_message: str | None = None


class SpanQueue:
    """Thin asyncio.Queue wrapper for completed SpanData.

    The Tracer puts spans here via put_nowait() (never blocks).
    OTELAgent drains this queue and calls the ExportBackend.
    """

    def __init__(self, maxsize: int = 10_000) -> None:
        self._queue: asyncio.Queue[SpanData] = asyncio.Queue(maxsize=maxsize)

    def put_nowait(self, span: SpanData) -> None:
        """Enqueue a completed span. Drops oldest if full (never blocks)."""
        try:
            self._queue.put_nowait(span)
        except asyncio.QueueFull:
            # Drop the oldest span to make room — losing a span is better
            # than blocking the message loop.
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(span)

    async def get(self) -> SpanData:
        """Dequeue a span. Awaits until one is available."""
        return await self._queue.get()

    def get_nowait(self) -> SpanData:
        return self._queue.get_nowait()

    def empty(self) -> bool:
        return self._queue.empty()

    def qsize(self) -> int:
        return self._queue.qsize()
