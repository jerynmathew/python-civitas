"""Shared test fixtures and reusable test agents."""

import asyncio

import pytest

from agency import AgentProcess, Runtime, Supervisor
from agency.messages import Message


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
