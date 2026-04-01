"""MessageBus — routes messages between AgentProcesses via the transport layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agency.errors import MessageRoutingError, MessageValidationError
from agency.messages import SYSTEM_MESSAGE_TYPES, Message
from agency.observability.tracer import Tracer
from agency.registry import Registry
from agency.serializer import Serializer
from agency.transport import Transport

if TYPE_CHECKING:
    from agency.process import AgentProcess


class MessageBus:
    """Central message router.

    Routes messages from sender to recipient by name, delegates physical
    delivery to the Transport, applies serialization via the Serializer,
    and generates tracing spans for every send/receive.
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

    async def route(self, message: Message) -> None:
        """Route a message to its recipient via the transport.

        Validates system message types, creates a send span, serializes the
        message, and publishes it through the transport.
        """
        self._validate_message_type(message)

        entry = self._registry.lookup(message.recipient)
        if entry is None:
            raise MessageRoutingError(
                f"No agent registered with name: {message.recipient!r}"
            )

        span = self._tracer.start_send_span(message)
        try:
            data = self._serializer.serialize(message)
            await self._transport.publish(entry.address, data)
        finally:
            span.end()

    async def route_reply(self, message: Message) -> None:
        """Route a reply to an ephemeral transport address.

        Bypasses the registry — reply addresses are temporary endpoints
        created by transport.request(), not registered agents.
        """
        span = self._tracer.start_send_span(message)
        try:
            data = self._serializer.serialize(message)
            await self._transport.publish(message.recipient, data)
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
            raise MessageRoutingError(
                f"No agent registered with name: {message.recipient!r}"
            )

        span = self._tracer.start_send_span(message)
        try:
            data = self._serializer.serialize(message)
            reply_data = await self._transport.request(entry.address, data, timeout)
            return self._serializer.deserialize(reply_data)
        finally:
            span.end()
