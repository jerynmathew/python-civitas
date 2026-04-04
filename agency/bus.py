"""MessageBus — routes messages between AgentProcesses via the transport layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agency.errors import MessageRoutingError, MessageValidationError
from agency.messages import SYSTEM_MESSAGE_TYPES, Message
from agency.observability.tracer import Tracer
from agency.registry import Registry, RoutingEntry
from agency.serializer import Serializer
from agency.transport import Transport

if TYPE_CHECKING:
    from agency.process import AgentProcess


class MessageBus:
    """Central message router.

    Routes messages from sender to recipient by name, delegates physical
    delivery to the Transport, applies serialization via the Serializer,
    and generates tracing spans for every send/receive.

    Routing precedence in route():
    1. Registry lookup by recipient name → use RoutingEntry.address
    2. Transport ephemeral reply address → publish directly (for request-reply)
    3. Neither → raise MessageRoutingError
    """

    def __init__(
        self,
        transport: Transport,
        registry: Registry,
        serializer: Serializer,
        tracer: Tracer,
    ) -> None:
        self._transport = transport
        self._registry = registry
        self._serializer = serializer
        self._tracer = tracer

    async def setup_agent(self, agent: AgentProcess) -> None:
        """Subscribe the transport to deliver messages to an agent's mailbox."""

        async def _on_message_received(data: bytes) -> None:
            message = self._serializer.deserialize(data)
            span = self._tracer.start_receive_span(message)
            try:
                await agent.receive(message)
            finally:
                span.end()

        await self._transport.subscribe(agent.name, _on_message_received)

    def _validate_message_type(self, message: Message) -> None:
        """Raise MessageValidationError for unknown _agency.* message types."""
        if message.type.startswith("_agency.") and message.type not in SYSTEM_MESSAGE_TYPES:
            raise MessageValidationError(
                f"Unknown system message type: {message.type}. "
                f"Application messages must not use the '_agency.' prefix."
            )

    def lookup_all(self, pattern: str) -> list[RoutingEntry]:
        """Return all registered agents matching a glob pattern."""
        return self._registry.lookup_all(pattern)

    async def route(self, message: Message) -> None:
        """Route a message to its recipient.

        Validates system message types, creates a send span, serializes the
        message, and publishes through the transport.

        Routing order:
        1. Registry lookup → use RoutingEntry.address
        2. Transport ephemeral reply address (has_reply_address) → publish directly
        3. Neither → raise MessageRoutingError
        """
        self._validate_message_type(message)

        entry = self._registry.lookup(message.recipient)
        if entry is not None:
            address = entry.address
        elif self._transport.has_reply_address(message.recipient):
            # Ephemeral reply endpoint — same-process request-reply short-circuit
            address = message.recipient
        elif message.recipient.startswith("_reply."):
            # Cross-process reply: the runtime's transport owns this ephemeral topic.
            # Route by address directly — ZMQ/NATS delivery handles it.
            address = message.recipient
        else:
            raise MessageRoutingError(f"No agent registered with name: {message.recipient!r}")

        span = self._tracer.start_send_span(message)
        try:
            data = self._serializer.serialize(message)
            await self._transport.publish(address, data)
        finally:
            span.end()

    async def request(self, message: Message, timeout: float = 30.0) -> Message:
        """Send a request message and await a reply.

        Used by ask() — delegates to transport.request() which handles
        correlation and reply routing.
        """
        self._validate_message_type(message)

        entry = self._registry.lookup(message.recipient)
        if entry is None:
            raise MessageRoutingError(f"No agent registered with name: {message.recipient!r}")

        span = self._tracer.start_send_span(message)
        try:
            data = self._serializer.serialize(message)
            reply_data = await self._transport.request(entry.address, data, timeout)
            return self._serializer.deserialize(reply_data)
        finally:
            span.end()
