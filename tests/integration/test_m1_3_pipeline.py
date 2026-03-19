"""M1.3 — Multi-Agent Communication testable criteria.

Each test maps to one bullet in the M1.3 milestone.
"""

import asyncio

import pytest

from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message
from agency.process import ProcessStatus


# ------------------------------------------------------------------
# Test agents
# ------------------------------------------------------------------


class EchoAgent(AgentProcess):
    """Simple echo agent."""

    async def handle(self, message: Message) -> Message | None:
        return self.reply({"echo": message.payload})


class CollectorAgent(AgentProcess):
    """Collects all received fire-and-forget messages."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.received: list[dict] = []

    async def handle(self, message: Message) -> Message | None:
        self.received.append(message.payload)
        if message.correlation_id:
            return self.reply({"ack": True})
        return None


class PipelineAgent(AgentProcess):
    """Asks another agent and returns the combined result."""

    def __init__(self, name: str, downstream: str) -> None:
        super().__init__(name)
        self.downstream = downstream

    async def handle(self, message: Message) -> Message | None:
        result = await self.ask(self.downstream, message.payload)
        return self.reply({"from": self.name, "downstream": result.payload})


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


async def test_three_agents_start_and_register():
    """Three agents start and register in Registry."""
    a1, a2, a3 = EchoAgent("agent_1"), EchoAgent("agent_2"), EchoAgent("agent_3")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[a1, a2, a3])
    )
    await runtime.start()
    try:
        for name in ("agent_1", "agent_2", "agent_3"):
            agent = await runtime._registry.lookup(name)
            assert agent is not None
            assert agent.status == ProcessStatus.RUNNING
    finally:
        await runtime.stop()


async def test_messages_route_by_name():
    """Messages route correctly by name via MessageBus."""
    a1 = EchoAgent("alpha")
    a2 = EchoAgent("beta")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[a1, a2])
    )
    await runtime.start()
    try:
        r1 = await runtime.ask("alpha", {"target": "alpha"})
        r2 = await runtime.ask("beta", {"target": "beta"})
        assert r1.payload["echo"]["target"] == "alpha"
        assert r2.payload["echo"]["target"] == "beta"
    finally:
        await runtime.stop()


async def test_fire_and_forget_send():
    """Fire-and-forget (send) works."""
    collector = CollectorAgent("collector")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[collector])
    )
    await runtime.start()
    try:
        await runtime.send("collector", {"msg": "hello"})
        await runtime.send("collector", {"msg": "world"})
        # Give time for messages to be processed
        await asyncio.sleep(0.1)

        assert len(collector.received) == 2
        assert collector.received[0]["msg"] == "hello"
        assert collector.received[1]["msg"] == "world"
    finally:
        await runtime.stop()


async def test_request_reply_ask_with_timeout():
    """Request-reply (ask) works with timeout."""
    echo = EchoAgent("echo")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[echo])
    )
    await runtime.start()
    try:
        result = await runtime.ask("echo", {"key": "value"}, timeout=5.0)
        assert result.payload["echo"]["key"] == "value"
        assert result.sender == "echo"
    finally:
        await runtime.stop()


async def test_broadcast_to_pattern():
    """Broadcast to pattern (tool_agents.*) delivers to all matching agents."""
    t1 = CollectorAgent("tool_agents.search")
    t2 = CollectorAgent("tool_agents.calc")
    other = CollectorAgent("other_agent")

    # Create a sender agent that broadcasts
    class BroadcastSender(AgentProcess):
        async def handle(self, message: Message) -> Message | None:
            await self.broadcast("tool_agents.*", {"broadcast": True})
            return self.reply({"sent": True})

    sender = BroadcastSender("sender")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[t1, t2, other, sender])
    )
    await runtime.start()
    try:
        await runtime.ask("sender", {"go": True})
        await asyncio.sleep(0.1)

        # Both tool_agents.* should have received, other should not
        assert len(t1.received) == 1
        assert t1.received[0]["broadcast"] is True
        assert len(t2.received) == 1
        assert t2.received[0]["broadcast"] is True
        assert len(other.received) == 0
    finally:
        await runtime.stop()


async def test_backpressure_when_mailbox_full():
    """Backpressure: sender pauses when recipient mailbox is full."""

    class SlowAgent(AgentProcess):
        """Agent that processes messages slowly."""

        def __init__(self, name: str) -> None:
            super().__init__(name, mailbox_size=2)
            self.processed = 0

        async def handle(self, message: Message) -> Message | None:
            await asyncio.sleep(0.05)
            self.processed += 1
            return None

    slow = SlowAgent("slow")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[slow])
    )
    await runtime.start()
    try:
        # Send multiple messages — mailbox size is 2, so some will block
        # Using send (fire-and-forget) to test backpressure
        tasks = []
        for i in range(5):
            tasks.append(asyncio.create_task(runtime.send("slow", {"i": i})))

        # All sends should eventually complete (backpressure, not drop)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

        # Wait for processing
        await asyncio.sleep(0.5)
        assert slow.processed == 5
    finally:
        await runtime.stop()


async def test_registry_lookup_by_name_and_pattern():
    """Registry lookup by name and by pattern both work."""
    a1 = EchoAgent("svc.alpha")
    a2 = EchoAgent("svc.beta")
    a3 = EchoAgent("other")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[a1, a2, a3])
    )
    await runtime.start()
    try:
        # Lookup by exact name
        agent = await runtime._registry.lookup("svc.alpha")
        assert agent is not None
        assert agent.name == "svc.alpha"

        # Lookup by pattern
        matches = await runtime._registry.lookup_all("svc.*")
        names = [a.name for a in matches]
        assert "svc.alpha" in names
        assert "svc.beta" in names
        assert "other" not in names
    finally:
        await runtime.stop()
