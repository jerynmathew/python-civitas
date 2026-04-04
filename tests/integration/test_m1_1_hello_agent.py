"""M1.1 — Hello Agent testable criteria.

Each test maps to one bullet in the M1.1 milestone.
"""

from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message
from agency.process import ProcessStatus


class Greeter(AgentProcess):
    async def handle(self, message: Message) -> Message | None:
        return self.reply({"greeting": f"Hello, {message.payload['name']}"})


async def test_agent_starts_and_enters_running_state():
    """AgentProcess starts, enters RUNNING state."""
    runtime = Runtime(supervisor=Supervisor("root", children=[Greeter("greeter")]))
    await runtime.start()
    try:
        agent = runtime.get_agent("greeter")
        assert agent is not None
        assert agent.status == ProcessStatus.RUNNING
    finally:
        await runtime.stop()


async def test_message_sent_via_ask_is_received_by_handle():
    """Message sent via runtime.ask() is received by agent's handle()."""
    runtime = Runtime(supervisor=Supervisor("root", children=[Greeter("greeter")]))
    await runtime.start()
    try:
        result = await runtime.ask("greeter", {"name": "world"})
        assert result.payload["greeting"] == "Hello, world"
    finally:
        await runtime.stop()


async def test_response_returned_to_caller():
    """Response returned to caller with correct payload."""
    runtime = Runtime(supervisor=Supervisor("root", children=[Greeter("greeter")]))
    await runtime.start()
    try:
        result = await runtime.ask("greeter", {"name": "Agency"})
        assert isinstance(result, Message)
        assert result.payload == {"greeting": "Hello, Agency"}
        assert result.sender == "greeter"
    finally:
        await runtime.stop()


async def test_process_shuts_down_cleanly():
    """Process shuts down cleanly on runtime.stop()."""
    runtime = Runtime(supervisor=Supervisor("root", children=[Greeter("greeter")]))
    await runtime.start()
    agent = runtime.get_agent("greeter")
    assert agent.status == ProcessStatus.RUNNING

    await runtime.stop()
    assert agent.status == ProcessStatus.STOPPED


async def test_multiple_messages():
    """Agent handles multiple sequential messages correctly."""
    runtime = Runtime(supervisor=Supervisor("root", children=[Greeter("greeter")]))
    await runtime.start()
    try:
        r1 = await runtime.ask("greeter", {"name": "Alice"})
        r2 = await runtime.ask("greeter", {"name": "Bob"})
        assert r1.payload["greeting"] == "Hello, Alice"
        assert r2.payload["greeting"] == "Hello, Bob"
    finally:
        await runtime.stop()
