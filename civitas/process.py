"""AgentProcess — the fundamental unit of computation in Civitas."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Any

from civitas.errors import ErrorAction
from civitas.messages import Message, _new_span_id, _uuid7
from civitas.observability.tracer import Span

if TYPE_CHECKING:
    from civitas.bus import MessageBus
    from civitas.observability.tracer import Tracer
    from civitas.plugins.model import ModelProvider
    from civitas.plugins.state import StateStore
    from civitas.plugins.tools import ToolRegistry


class ProcessStatus(Enum):
    """Lifecycle states for an AgentProcess."""

    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    CRASHED = "CRASHED"


class Mailbox:
    """Bounded async queue for incoming messages with priority support.

    High-priority system messages (priority > 0) are placed at the front.
    Normal messages follow FIFO order. Backpressure is applied when the
    mailbox is full — the sender awaits until space is available.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=maxsize)
        self._priority_queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=100)
        self._notify: asyncio.Event = asyncio.Event()

    async def put(self, message: Message) -> None:
        """Enqueue a message. Priority messages bypass the normal queue."""
        if message.priority > 0:
            await self._priority_queue.put(message)
            self._notify.set()
        else:
            await self._queue.put(message)
            self._notify.set()

    async def get(self) -> Message:
        """Dequeue the next message. Priority messages are served first."""
        while True:
            # Check priority queue first
            if not self._priority_queue.empty():
                return self._priority_queue.get_nowait()
            # Then normal queue
            if not self._queue.empty():
                return self._queue.get_nowait()
            # Wait for a notification
            self._notify.clear()
            # Double-check after clearing (avoid race)
            if not self._priority_queue.empty() or not self._queue.empty():
                continue
            await self._notify.wait()

    def empty(self) -> bool:
        """Return True if both priority and normal queues are empty."""
        return self._priority_queue.empty() and self._queue.empty()


class AgentProcess:
    """Base class for all agent processes in Civitas.

    Developers subclass this and override lifecycle hooks:
    - on_start(): called once before the first message
    - handle(message): called for every incoming message
    - on_error(error, message): called when handle() raises
    - on_stop(): called on graceful shutdown (always — even on crash)

    Messaging methods available inside hooks:
    - send(recipient, payload, message_type): fire-and-forget
    - ask(recipient, payload, message_type, timeout): request-reply
    - broadcast(pattern, payload): send to all matching agents
    - reply(payload): return from handle() for request-reply

    Observability helpers (call from inside handle()):
    - llm_span(model, **attrs): context manager for LLM call spans
    - tool_span(tool_name, **attrs): context manager for tool call spans
    """

    def __init__(
        self,
        name: str,
        mailbox_size: int = 1000,
        max_retries: int = 3,
        shutdown_timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.id: str = _uuid7()
        self.state: dict[str, Any] = {}
        self._status = ProcessStatus.INITIALIZING
        self._mailbox = Mailbox(maxsize=mailbox_size)
        self._task: asyncio.Task[None] | None = None
        self._max_retries = max_retries
        self._shutdown_timeout = shutdown_timeout

        # Injected by Runtime/Worker during setup
        self._bus: MessageBus | None = None
        self._tracer: Tracer | None = None
        self.llm: ModelProvider | None = None
        self.tools: ToolRegistry | None = None
        self.store: StateStore | None = None

        # MCP clients opened via connect_mcp() — keyed by server name
        self._mcp_clients: dict[str, Any] = {}

        # Current message context for reply/tracing
        self._current_message: Message | None = None
        self._current_handle_span: Span | None = None

        # Signalled when the message loop enters RUNNING
        self._running_event: asyncio.Event | None = None

    @property
    def status(self) -> ProcessStatus:
        return self._status

    async def receive(self, message: Message) -> None:
        """Deliver an inbound message to this agent's mailbox."""
        await self._mailbox.put(message)

    # ------------------------------------------------------------------
    # Lifecycle hooks — override in subclasses
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        """Called once before the first message. Initialize self.state here."""

    async def handle(self, message: Message) -> Message | None:
        """Called for every incoming message.

        Return self.reply(...) for request-reply. Return None for fire-and-forget.
        """
        return None

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        """Called when handle() raises an exception.

        Return an ErrorAction. Default: ESCALATE (crash, let supervisor decide).
        """
        return ErrorAction.ESCALATE

    async def on_stop(self) -> None:
        """Called on graceful shutdown. Always called — even on crash."""

    # ------------------------------------------------------------------
    # State persistence — checkpoint and restore
    # ------------------------------------------------------------------

    async def checkpoint(self) -> None:
        """Save self.state to the configured StateStore.

        Call this from handle() after completing a meaningful unit of work.
        On restart, self.state is automatically restored from the last checkpoint.
        Agents that never call checkpoint() incur zero overhead.
        """
        if self.store is not None:
            await self.store.set(self.name, self.state)

    async def _restore_state(self) -> None:
        """Restore self.state from the StateStore if a checkpoint exists."""
        if self.store is not None:
            saved = await self.store.get(self.name)
            if saved is not None:
                self.state = saved

    # ------------------------------------------------------------------
    # Messaging methods — call from inside hooks
    # ------------------------------------------------------------------

    async def send(
        self,
        recipient: str,
        payload: dict[str, Any],
        message_type: str = "message",
    ) -> None:
        """Fire-and-forget: send a message to another agent by name."""
        if self._bus is None:
            raise RuntimeError("AgentProcess not wired to a MessageBus")
        trace_id = ""
        parent_span_id: str | None = None
        if self._current_message is not None:
            trace_id = self._current_message.trace_id
            parent_span_id = self._current_message.span_id

        message = Message(
            type=message_type,
            sender=self.name,
            recipient=recipient,
            payload=payload,
            trace_id=trace_id,
            span_id=_new_span_id(),
            parent_span_id=parent_span_id,
        )
        await self._bus.route(message)

    async def ask(
        self,
        recipient: str,
        payload: dict[str, Any],
        message_type: str = "message",
        timeout: float = 30.0,
    ) -> Message:
        """Request-reply: send a message and await a response."""
        if self._bus is None:
            raise RuntimeError("AgentProcess not wired to a MessageBus")
        trace_id = ""
        parent_span_id: str | None = None
        if self._current_message is not None:
            trace_id = self._current_message.trace_id
            parent_span_id = self._current_message.span_id

        correlation_id = _uuid7()
        message = Message(
            type=message_type,
            sender=self.name,
            recipient=recipient,
            payload=payload,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=_new_span_id(),
            parent_span_id=parent_span_id,
        )
        return await self._bus.request(message, timeout=timeout)

    async def call(
        self,
        name: str,
        payload: dict[str, Any],
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """Synchronous call to a GenServer. Blocks until reply or timeout."""
        reply = await self.ask(name, payload, timeout=timeout)
        return reply.payload

    async def cast(self, name: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget cast to a GenServer. Returns immediately."""
        await self.send(name, {**payload, "__cast__": True})

    async def connect_mcp(self, config: Any) -> None:
        """Connect to an MCP server and register its tools into self.tools.

        Idempotent: disconnects any existing client for config.name before reconnecting.
        Tools are addressable as mcp://server_name/tool_name after this call.
        """
        from civitas.mcp.client import MCPClient
        from civitas.mcp.tool import MCPTool

        existing = self._mcp_clients.get(config.name)
        if existing is not None:
            if self.tools is not None:
                self.tools.deregister_prefix(f"mcp://{config.name}/")
            try:
                await existing.disconnect()
            except Exception:
                pass

        client = MCPClient(config)
        await client.connect()
        schemas = await client.list_tools()

        if self.tools is not None:
            for schema in schemas:
                mcp_tool = MCPTool(client, schema, tracer=self._tracer)
                self.tools.register(mcp_tool)

        self._mcp_clients[config.name] = client

    async def broadcast(self, pattern: str, payload: dict[str, Any]) -> None:
        """Send a message to all agents matching a glob pattern."""
        if self._bus is None:
            raise RuntimeError("AgentProcess not wired to a MessageBus")
        targets = self._bus.lookup_all(pattern)
        for target in targets:
            await self.send(target.name, payload)

    def reply(self, payload: dict[str, Any]) -> Message:
        """Create a reply message. Return this from handle() for request-reply."""
        if self._current_message is None:
            raise RuntimeError("reply() called outside of handle()")
        msg = self._current_message
        return Message(
            type=payload.get("type", "reply"),
            sender=self.name,
            recipient=msg.reply_to or msg.sender,
            payload=payload,
            correlation_id=msg.correlation_id,
            trace_id=msg.trace_id,
            span_id=_new_span_id(),
            parent_span_id=msg.span_id,
        )

    # ------------------------------------------------------------------
    # Observability helpers — call from inside handle()
    # ------------------------------------------------------------------

    @contextmanager
    def llm_span(self, model: str, **attributes: Any) -> Iterator[Span]:
        """Context manager that creates an LLM call span parented to handle().

        Usage:
            with self.llm_span("claude-sonnet", tokens_in=1200) as span:
                response = await self.llm.chat(...)
                span.set_attribute("civitas.llm.tokens_out", ...)
        """
        if self._tracer is None:
            yield Span(name="llm", trace_id="", span_id="")
            return

        parent_span_id = (
            self._current_handle_span.span_id
            if self._current_handle_span is not None
            else (self._current_message.span_id if self._current_message else None)
        )
        trace_id = self._current_message.trace_id if self._current_message else ""
        span = self._tracer.start_span(
            "civitas.llm.chat",
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes={"civitas.llm.model": model, **attributes},
        )
        try:
            yield span
        except Exception as exc:
            span.set_error(exc)
            raise
        finally:
            span.end()

    @contextmanager
    def tool_span(self, tool_name: str, **attributes: Any) -> Iterator[Span]:
        """Context manager that creates a tool invocation span parented to handle().

        Usage:
            with self.tool_span("web_search") as span:
                result = await self.tools.invoke("web_search", ...)
                span.set_attribute("civitas.tool.result_size_bytes", len(result))
        """
        if self._tracer is None:
            yield Span(name="tool", trace_id="", span_id="")
            return

        parent_span_id = (
            self._current_handle_span.span_id
            if self._current_handle_span is not None
            else (self._current_message.span_id if self._current_message else None)
        )
        trace_id = self._current_message.trace_id if self._current_message else ""
        span = self._tracer.start_span(
            "civitas.tool.invoke",
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes={"civitas.tool.name": tool_name, **attributes},
        )
        try:
            yield span
        except Exception as exc:
            span.set_error(exc)
            raise
        finally:
            span.end()

    # ------------------------------------------------------------------
    # Internal lifecycle — called by Supervisor / Runtime
    # ------------------------------------------------------------------

    async def _start(self) -> None:
        """Initialize the agent and start the message loop as a task."""
        self._status = ProcessStatus.INITIALIZING
        self._running_event = asyncio.Event()
        await self._restore_state()

        # Emit agent.start span
        if self._tracer is not None:
            start_span = self._tracer.start_span(
                "civitas.agent.start",
                attributes={"civitas.agent.name": self.name, "civitas.agent.id": self.id},
            )

        await self.on_start()

        if self._tracer is not None:
            start_span.end()

        self._task = asyncio.create_task(self._message_loop(), name=self.name)
        # Wait until the message loop has entered RUNNING
        await self._running_event.wait()

    async def _message_loop(self) -> None:
        """Main loop: dequeue messages and dispatch to handle()."""
        self._status = ProcessStatus.RUNNING
        if self._running_event is not None:
            self._running_event.set()

        try:
            while self._status == ProcessStatus.RUNNING:
                message = await self._mailbox.get()
                if message.type == "_agency.shutdown":
                    break
                if message.type == "_agency.heartbeat":
                    # Auto-respond to heartbeat pings from supervisor
                    if self._bus is not None:
                        ack = Message(
                            type="_agency.heartbeat_ack",
                            sender=self.name,
                            recipient=message.reply_to or message.sender,
                            correlation_id=message.correlation_id,
                            trace_id=message.trace_id,
                        )
                        await self._bus.route(ack)
                    continue
                self._current_message = message
                await self._dispatch(message)
                self._current_message = None
        finally:
            self._current_message = None
            self._current_handle_span = None
            # Preserve CRASHED — only move to STOPPING for normal/requested exits
            crashed = self._status == ProcessStatus.CRASHED
            if not crashed:
                self._status = ProcessStatus.STOPPING

            # Emit agent.stop span — always, including on crash
            if self._tracer is not None:
                stop_span = self._tracer.start_span(
                    "civitas.agent.stop",
                    attributes={
                        "civitas.agent.name": self.name,
                        "civitas.agent.id": self.id,
                        "civitas.agent.final_status": self._status.value,
                    },
                )

            await self.on_stop()

            for _client in list(self._mcp_clients.values()):
                try:
                    await _client.disconnect()
                except Exception:
                    pass
            self._mcp_clients.clear()

            if self._tracer is not None:
                stop_span.end()

            if not crashed:
                self._status = ProcessStatus.STOPPED

    async def _dispatch(self, message: Message) -> None:
        """Wrap a single handle() call in a span, apply error action."""
        # Start handle span
        handle_span: Span | None = None
        if self._tracer is not None:
            handle_span = self._tracer.start_span(
                "civitas.agent.handle",
                trace_id=message.trace_id,
                parent_span_id=message.span_id,
                attributes={
                    "civitas.agent.name": self.name,
                    "civitas.message.type": message.type,
                    "civitas.handle.attempt": message.attempt,
                },
            )
        self._current_handle_span = handle_span

        try:
            result = await self.handle(message)
            if handle_span is not None:
                handle_span.set_attribute("civitas.handle.result", "success")
            if result is not None and message.correlation_id and self._bus is not None:
                await self._bus.route(result)
        except Exception as exc:
            if handle_span is not None:
                handle_span.set_error(exc)
                handle_span.set_attribute("civitas.handle.result", "error")
            action = await self.on_error(exc, message)
            if handle_span is not None:
                handle_span.set_attribute("civitas.handle.result", f"error.{action.value.lower()}")
            await self._apply_error_action(action, exc, message)
        finally:
            if handle_span is not None:
                handle_span.end()
            self._current_handle_span = None

    async def _apply_error_action(
        self, action: ErrorAction, exc: Exception, message: Message
    ) -> None:
        """Apply the error action returned by on_error()."""
        if action == ErrorAction.RETRY:
            message.attempt += 1
            if message.attempt > self._max_retries:
                # Max retries exceeded — escalate instead of looping forever
                self._status = ProcessStatus.CRASHED
                raise exc
            # Emit retry span
            if self._tracer is not None:
                retry_span = self._tracer.start_span(
                    "civitas.agent.retry",
                    trace_id=message.trace_id,
                    attributes={
                        "civitas.agent.name": self.name,
                        "civitas.message.type": message.type,
                        "civitas.handle.attempt": message.attempt,
                        "civitas.max_retries": self._max_retries,
                        "error.type": type(exc).__name__,
                    },
                )
                retry_span.end()
            await self._mailbox.put(message)
        elif action == ErrorAction.SKIP:
            pass  # discard message, continue
        elif action == ErrorAction.STOP:
            self._status = ProcessStatus.STOPPING
        elif action == ErrorAction.ESCALATE:
            self._status = ProcessStatus.CRASHED
            raise exc  # propagate to supervisor via task exception

    async def _stop(self) -> None:
        """Request graceful shutdown by sending a shutdown system message."""
        if self._status not in (ProcessStatus.RUNNING, ProcessStatus.INITIALIZING):
            return
        shutdown_msg = Message(
            type="_agency.shutdown",
            sender="_agency",
            recipient=self.name,
            priority=1,
        )
        await self._mailbox.put(shutdown_msg)
        if self._task is not None and not self._task.done():
            try:
                async with asyncio.timeout(self._shutdown_timeout):
                    await self._task
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
