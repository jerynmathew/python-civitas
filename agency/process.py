"""AgentProcess — the fundamental unit of computation in Agency."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, Any

from agency.errors import ErrorAction
from agency.messages import Message, _uuid7
from agency.observability.tracer import Tracer, _new_span_id

if TYPE_CHECKING:
    from agency.bus import MessageBus
    from agency.plugins.state import StateStore
    from agency.plugins.tools import ToolRegistry


class ProcessStatus(Enum):
    """Lifecycle states for an AgentProcess."""

    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
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
        self._priority_queue: asyncio.Queue[Message] = asyncio.Queue()
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
        return self._priority_queue.empty() and self._queue.empty()


class AgentProcess:
    """Base class for all agent processes in Agency.

    Developers subclass this and override lifecycle hooks:
    - on_start(): called once before the first message
    - handle(message): called for every incoming message
    - on_error(error, message): called when handle() raises
    - on_stop(): called on graceful shutdown

    Messaging methods available inside hooks:
    - send(recipient, payload): fire-and-forget
    - ask(recipient, payload, timeout): request-reply
    - broadcast(pattern, payload): send to all matching agents
    - reply(payload): return from handle() for request-reply
    """

    def __init__(self, name: str, mailbox_size: int = 1000) -> None:
        self.name = name
        self.id: str = _uuid7()
        self.state: dict[str, Any] = {}
        self._status = ProcessStatus.INITIALIZING
        self._mailbox = Mailbox(maxsize=mailbox_size)
        self._task: asyncio.Task[None] | None = None

        # Injected by Runtime during setup
        self._bus: MessageBus | None = None
        self._tracer: Tracer | None = None
        self.llm: Any = None
        self.tools: Any = None
        self.store: Any = None

        # Current message context for reply/tracing
        self._current_message: Message | None = None

        # Signalled when the message loop enters RUNNING
        self._running_event: asyncio.Event | None = None

    @property
    def status(self) -> ProcessStatus:
        return self._status

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
        """Called on graceful shutdown."""

    # ------------------------------------------------------------------
    # Messaging methods — call from inside hooks
    # ------------------------------------------------------------------

    async def send(self, recipient: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget: send a message to another agent by name."""
        assert self._bus is not None, "AgentProcess not wired to a MessageBus"
        trace_id = ""
        parent_span_id: str | None = None
        if self._current_message is not None:
            trace_id = self._current_message.trace_id
            parent_span_id = self._current_message.span_id

        message = Message(
            type=payload.get("type", "message"),
            sender=self.name,
            recipient=recipient,
            payload=payload,
            trace_id=trace_id,
            span_id=_new_span_id(),
            parent_span_id=parent_span_id,
        )
        await self._bus.route(message)

    async def ask(
        self, recipient: str, payload: dict[str, Any], timeout: float = 30.0
    ) -> Message:
        """Request-reply: send a message and await a response."""
        assert self._bus is not None, "AgentProcess not wired to a MessageBus"
        trace_id = ""
        parent_span_id: str | None = None
        if self._current_message is not None:
            trace_id = self._current_message.trace_id
            parent_span_id = self._current_message.span_id

        correlation_id = _uuid7()
        message = Message(
            type=payload.get("type", "message"),
            sender=self.name,
            recipient=recipient,
            payload=payload,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=_new_span_id(),
            parent_span_id=parent_span_id,
        )
        return await self._bus.request(message, timeout=timeout)

    async def broadcast(self, pattern: str, payload: dict[str, Any]) -> None:
        """Send a message to all agents matching a glob pattern."""
        assert self._bus is not None, "AgentProcess not wired to a MessageBus"
        from agency.registry import Registry

        # Access registry through the bus
        registry: Registry = self._bus._registry
        targets = await registry.lookup_all(pattern)
        for target in targets:
            await self.send(target.name, payload)

    def reply(self, payload: dict[str, Any]) -> Message:
        """Create a reply message. Return this from handle() for request-reply."""
        assert self._current_message is not None, "reply() called outside of handle()"
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
    # Internal lifecycle — called by Supervisor / Runtime
    # ------------------------------------------------------------------

    async def _start(self) -> None:
        """Initialize the agent and start the message loop as a task."""
        self._status = ProcessStatus.INITIALIZING
        self._running_event = asyncio.Event()
        await self.on_start()
        self._task = asyncio.create_task(self._message_loop(), name=self.name)
        # Wait until the message loop has entered RUNNING
        await self._running_event.wait()

    async def _message_loop(self) -> None:
        """Main loop: dequeue messages and dispatch to handle()."""
        self._status = ProcessStatus.RUNNING
        if self._running_event is not None:
            self._running_event.set()
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
            try:
                result = await self.handle(message)
                if result is not None and message.correlation_id:
                    assert self._bus is not None
                    await self._bus.route(result)
            except Exception as exc:
                action = await self.on_error(exc, message)
                await self._apply_error_action(action, exc, message)
            finally:
                self._current_message = None
        self._status = ProcessStatus.STOPPING
        await self.on_stop()
        self._status = ProcessStatus.STOPPED

    async def _apply_error_action(
        self, action: ErrorAction, exc: Exception, message: Message
    ) -> None:
        """Apply the error action returned by on_error()."""
        if action == ErrorAction.RETRY:
            message.attempt += 1
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
                async with asyncio.timeout(30):
                    await self._task
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
