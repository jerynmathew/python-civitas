"""Tests for MessageBus routing and validation."""

import pytest

from agency.bus import MessageBus
from agency.errors import MessageValidationError
from agency.messages import Message
from agency.observability.tracer import Tracer
from agency.process import AgentProcess
from agency.registry import Registry
from agency.serializer import MsgpackSerializer
from agency.transport.inprocess import InProcessTransport


class CollectorAgent(AgentProcess):
    """Test agent that collects received messages."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.received: list[Message] = []

    async def handle(self, message: Message) -> Message | None:
        self.received.append(message)
        return self.reply({"ack": True})


@pytest.fixture
def components():
    serializer = MsgpackSerializer()
    transport = InProcessTransport(serializer)
    registry = Registry()
    tracer = Tracer()
    bus = MessageBus(transport, registry, serializer, tracer)
    return bus, transport, registry, serializer, tracer


async def test_route_delivers_to_agent(components):
    """route() delivers a message to the agent's mailbox via transport."""
    bus, transport, registry, _, _ = components
    await transport.start()

    agent = CollectorAgent("agent_a")
    agent._bus = bus
    registry.register("agent_a", agent)
    await bus.setup_agent(agent)

    msg = Message(
        type="test",
        sender="sender",
        recipient="agent_a",
        payload={"data": 1},
    )
    await bus.route(msg)

    # Message should be in the agent's mailbox
    received = await agent._mailbox.get()
    assert received.type == "test"
    assert received.payload == {"data": 1}

    await transport.stop()


async def test_route_rejects_unknown_system_message(components):
    """route() raises MessageValidationError for unknown _agency.* types."""
    bus, transport, _, _, _ = components
    await transport.start()

    msg = Message(
        type="_agency.unknown_type",
        sender="sender",
        recipient="agent_a",
    )
    with pytest.raises(MessageValidationError, match="Unknown system message"):
        await bus.route(msg)

    await transport.stop()


async def test_route_allows_valid_system_message(components):
    """route() accepts known _agency.* system message types."""
    bus, transport, registry, _, _ = components
    await transport.start()

    agent = CollectorAgent("agent_a")
    agent._bus = bus
    registry.register("agent_a", agent)
    await bus.setup_agent(agent)

    msg = Message(
        type="_agency.shutdown",
        sender="_agency",
        recipient="agent_a",
        priority=1,
    )
    # Should not raise
    await bus.route(msg)

    received = await agent._mailbox.get()
    assert received.type == "_agency.shutdown"

    await transport.stop()


async def test_route_allows_application_message(components):
    """route() accepts any message type that doesn't start with '_agency.'."""
    bus, transport, registry, _, _ = components
    await transport.start()

    agent = CollectorAgent("agent_a")
    agent._bus = bus
    registry.register("agent_a", agent)
    await bus.setup_agent(agent)

    msg = Message(
        type="custom_type",
        sender="sender",
        recipient="agent_a",
    )
    await bus.route(msg)  # should not raise

    received = await agent._mailbox.get()
    assert received.type == "custom_type"

    await transport.stop()
