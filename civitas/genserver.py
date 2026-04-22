"""GenServer — OTP-style generic server process.

Dispatch model:
- Messages with reply_to set     → handle_call  (synchronous, reply required)
- Messages with __cast__ marker  → handle_cast  (async fire-and-forget)
- All other messages             → handle_info  (timers, internal signals)

No LLM or tool provider is injected. self.llm and self.tools remain None.
"""

from __future__ import annotations

import asyncio
from typing import Any

from civitas.messages import Message, _new_span_id
from civitas.observability.tracer import Span
from civitas.process import AgentProcess


class GenServer(AgentProcess):
    """OTP-style generic server for stateful service processes.

    Override handle_call, handle_cast, handle_info — not handle().
    Do not override on_start(); use init() instead.
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._send_after_tasks: list[asyncio.Task[None]] = []

    # ------------------------------------------------------------------
    # Lifecycle — override init(), not on_start()
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        await self.init()

    async def on_stop(self) -> None:
        """Cancel all pending send_after tasks on shutdown."""
        for task in self._send_after_tasks:
            if not task.done():
                task.cancel()
        if self._send_after_tasks:
            await asyncio.gather(*self._send_after_tasks, return_exceptions=True)
        self._send_after_tasks.clear()

    async def init(self) -> None:
        """Called once when the process starts. Initialize self.state here."""

    # ------------------------------------------------------------------
    # Dispatch handlers — override in subclasses
    # ------------------------------------------------------------------

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        """Synchronous request. Must return a dict reply."""
        raise NotImplementedError(
            f"{type(self).__name__} received a call but handle_call() is not implemented"
        )

    async def handle_cast(self, payload: dict[str, Any]) -> None:
        """Async fire-and-forget. No reply."""

    async def handle_info(self, payload: dict[str, Any]) -> None:
        """Internal messages — timers, ticks, out-of-band signals."""

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    def send_after(self, delay_ms: int, payload: dict[str, Any]) -> None:
        """Schedule a handle_info message to self after delay_ms milliseconds."""

        async def _fire() -> None:
            await asyncio.sleep(delay_ms / 1000)
            if self._bus is not None:
                msg = Message(
                    type="genserver.info",
                    sender=self.name,
                    recipient=self.name,
                    payload=payload,
                    span_id=_new_span_id(),
                )
                try:
                    await self._bus.route(msg)
                except Exception:
                    pass  # process may have stopped; routing errors are expected

        # Prune completed tasks before appending to prevent unbounded growth
        self._send_after_tasks = [t for t in self._send_after_tasks if not t.done()]
        self._send_after_tasks.append(asyncio.create_task(_fire()))

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def handle(self, message: Message) -> Message | None:
        """Route message to handle_call, handle_cast, or handle_info."""
        if message.reply_to is not None:
            return await self._do_call(message)
        elif message.payload.get("__cast__"):
            await self._do_cast(message)
            return None
        else:
            await self._do_info(message)
            return None

    async def _do_call(self, message: Message) -> Message:
        span = self._gs_span("civitas.genserver.call", message)
        try:
            result = await self.handle_call(message.payload, message.sender)
            if not isinstance(result, dict):
                raise TypeError(f"handle_call() must return a dict, got {type(result).__name__}")
            if span is not None:
                span.set_attribute("civitas.handle.result", "success")
            return self.reply(result)
        except Exception as exc:
            if span is not None:
                span.set_error(exc)
            raise
        finally:
            if span is not None:
                span.end()

    async def _do_cast(self, message: Message) -> None:
        payload = {k: v for k, v in message.payload.items() if k != "__cast__"}
        span = self._gs_span("civitas.genserver.cast", message)
        try:
            await self.handle_cast(payload)
        except Exception as exc:
            if span is not None:
                span.set_error(exc)
            raise
        finally:
            if span is not None:
                span.end()

    async def _do_info(self, message: Message) -> None:
        span = self._gs_span("civitas.genserver.info", message)
        try:
            await self.handle_info(message.payload)
        except Exception as exc:
            if span is not None:
                span.set_error(exc)
            raise
        finally:
            if span is not None:
                span.end()

    def _gs_span(self, name: str, message: Message) -> Span | None:
        if self._tracer is None:
            return None
        parent_span_id = (
            self._current_handle_span.span_id
            if self._current_handle_span is not None
            else message.span_id or None
        )
        return self._tracer.start_span(
            name,
            trace_id=message.trace_id,
            parent_span_id=parent_span_id,
            attributes={"civitas.agent.name": self.name},
        )
