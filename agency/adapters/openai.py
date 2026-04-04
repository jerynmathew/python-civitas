"""OpenAIAgent — run an OpenAI Agents SDK agent as an AgentProcess.

Wraps an OpenAI Agents SDK ``Agent`` so it gains Agency supervision, OTEL
tracing, and transport-agnostic messaging. Under 10 lines of core logic.

Usage:
    from agents import Agent
    from agency.adapters.openai import OpenAIAgent

    agent = Agent(name="assistant", instructions="You are helpful.")

    runtime = Runtime(
        supervisor=Supervisor("root", children=[
            OpenAIAgent("my_agent", agent=agent),
        ])
    )
"""

from __future__ import annotations

from typing import Any

from agency.errors import ErrorAction
from agency.messages import Message
from agency.process import AgentProcess


class OpenAIAgent(AgentProcess):
    """Wraps an OpenAI Agents SDK Agent as an Agency AgentProcess.

    Incoming message payload must include ``"input"`` (the user message).
    The agent's text response is returned as ``{"output": ...}``.
    Handoffs are mapped to Agency ``send()`` calls.
    """

    def __init__(self, name: str, agent: Any, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._agent = agent

    async def handle(self, message: Message) -> Message | None:
        """Run the OpenAI agent and map handoffs to Agency messages."""
        from agents import Runner  # type: ignore[import-not-found]  # optional OpenAI Agents SDK

        result = await Runner.run(self._agent, input=message.payload.get("input", ""))
        # Map handoffs to Agency messages
        for item in getattr(result, "new_items", []):
            if hasattr(item, "agent") and hasattr(item, "input"):
                await self.send(item.agent.name, {"input": item.input})
        return self.reply({"output": result.final_output})

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        """Escalate all errors to the supervisor."""
        return ErrorAction.ESCALATE
