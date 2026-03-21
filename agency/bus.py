"""MessageBus — routes messages between AgentProcesses via the transport layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agency.errors import MessageValidationError
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
            await agent._mailbox.put(message)
            span.end()

        await self._transport.subscribe(agent.name, _on_message_received)

    async def route(self, message: Message) -> None:
        """Route a message to its recipient via the transport.

        Validates system message types, creates a send span, serializes the
        message, and publishes it through the transport.
        """
        # Enforce system message prefix restriction
        if message.type.startswith("_agency.") and message.type not in SYSTEM_MESSAGE_TYPES:
            raise MessageValidationError(
                f"Unknown system message type: {message.type}. "
                f"Application messages must not use the '_agency.' prefix."
            )

        span = self._tracer.start_send_span(message)
        data = self._serializer.serialize(message)
        await self._transport.publish(message.recipient, data)
        span.end()

    async def request(self, message: Message, timeout: float = 30.0) -> Message:
        """Send a request message and await a reply.

        Used by ask() — delegates to transport.request() which handles
        correlation and reply routing.
        """
        if message.type.startswith("_agency.") and message.type not in SYSTEM_MESSAGE_TYPES:
            raise MessageValidationError(
                f"Unknown system message type: {message.type}. "
                f"Application messages must not use the '_agency.' prefix."
            )

        span = self._tracer.start_send_span(message)
        data = self._serializer.serialize(message)
        reply_data = await self._transport.request(message.recipient, data, timeout)
        span.end()
        return self._serializer.deserialize(reply_data)
