"""OTELAgent — background coroutine that drains SpanQueue and exports spans."""

from __future__ import annotations

import asyncio
import logging

from agency.observability.export_backend import ExportBackend
from agency.observability.span_queue import SpanData, SpanQueue

logger = logging.getLogger(__name__)


async def run_otel_agent(
    queue: SpanQueue,
    backend: ExportBackend,
    batch_size: int = 50,
    flush_interval: float = 1.0,
) -> None:
    """Drain SpanQueue and export spans via the configured ExportBackend.

    This is a plain coroutine, not an AgentProcess. It has no mailbox,
    no supervision, and no message loop. Start it with asyncio.create_task()
    from Runtime or Worker during startup.

    Batches up to `batch_size` spans per export call, or flushes after
    `flush_interval` seconds even if the batch isn't full.

    On cancellation (shutdown), drains remaining spans before returning.
    """
    pending: list[SpanData] = []

    async def _flush() -> None:
        if pending:
            batch = pending.copy()
            pending.clear()
            try:
                await backend.export(batch)
            except Exception:  # noqa: BLE001
                logger.exception("OTELAgent: export failed, %d spans dropped", len(batch))

    try:
        while True:
            try:
                span = await asyncio.wait_for(queue.get(), timeout=flush_interval)
                pending.append(span)
                if len(pending) >= batch_size:
                    await _flush()
            except TimeoutError:
                await _flush()
    except asyncio.CancelledError:
        # F08-6: drain remaining spans with a 2s deadline to avoid stalling shutdown
        deadline = asyncio.get_event_loop().time() + 2.0
        while not queue.empty():
            if asyncio.get_event_loop().time() > deadline:
                logger.warning("OTELAgent: drain timeout — %d spans dropped", queue.qsize())
                break
            try:
                pending.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        await _flush()
        await backend.shutdown()
