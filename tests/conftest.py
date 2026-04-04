"""Shared test fixtures and reusable test agents."""

import asyncio
from collections.abc import Callable

from agency import AgentProcess
from agency.messages import Message
from agency.process import ProcessStatus


async def wait_for_status(
    agent: AgentProcess,
    status: ProcessStatus,
    timeout: float = 2.0,
) -> None:
    """Poll until agent reaches the expected status or timeout expires.

    Replaces asyncio.sleep() waits in supervision tests — responds as soon as
    the status changes rather than waiting a fixed duration.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while agent.status != status:
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(
                f"{agent.name!r} did not reach {status.value} within {timeout}s "
                f"(current: {agent.status.value})"
            )
        await asyncio.sleep(0.01)


async def wait_for(
    condition: Callable[[], bool],
    timeout: float = 2.0,
    msg: str = "condition",
) -> None:
    """Poll until condition() returns True or timeout expires."""
    deadline = asyncio.get_event_loop().time() + timeout
    while not condition():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(f"{msg} not met within {timeout}s")
        await asyncio.sleep(0.01)


class EchoAgent(AgentProcess):
    """Reusable test agent: echoes payload back to sender."""

    async def handle(self, message: Message) -> Message | None:
        return self.reply({"echo": message.payload})


class CrashingAgent(AgentProcess):
    """Reusable test agent: crashes on the Nth message."""

    def __init__(self, name: str, crash_on: int = 1, mailbox_size: int = 1000) -> None:
        super().__init__(name, mailbox_size=mailbox_size)
        self.crash_on = crash_on
        self.count = 0

    async def handle(self, message: Message) -> Message | None:
        self.count += 1
        if self.count == self.crash_on:
            raise ValueError(f"Intentional crash on message {self.count}")
        return self.reply({"count": self.count})
