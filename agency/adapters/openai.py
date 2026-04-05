"""OpenAIAgent — run an OpenAI Agents SDK agent as an AgentProcess.

Wraps an OpenAI Agents SDK ``Agent`` so it gains Agency supervision, OTEL
tracing, and transport-agnostic messaging.

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

import logging
from typing import Any

from agency.errors import ErrorAction, MessageRoutingError
from agency.messages import Message
from agency.process import AgentProcess

logger = logging.getLogger(__name__)


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
        from agents import Runner  # optional OpenAI Agents SDK

        # F10-2: explicit error on missing input key rather than silent empty string
        user_input = message.payload.get("input")
        if user_input is None:
            return self.reply({"error": "payload must include 'input' key"})

        result = await Runner.run(self._agent, input=user_input)

        # F10-1: log a warning instead of crashing on unregistered handoff targets
        for item in getattr(result, "new_items", []):
            if hasattr(item, "agent") and hasattr(item, "input"):
                try:
                    await self.send(item.agent.name, {"input": item.input})
                except MessageRoutingError:
                    logger.warning(
                        "[OpenAIAgent] handoff to %r failed — not registered in Agency",
                        item.agent.name,
                    )

        return self.reply({"output": result.final_output})

    def _is_transient(self, error: Exception) -> bool:
        """Return True for errors that should be retried rather than escalated.

        Subclasses can override to add retry logic for known-transient errors
        (e.g. httpx.TimeoutException, RateLimitError).
        """
        return False

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        """Retry transient errors; escalate all others to the supervisor."""
        if message.attempt < self._max_retries and self._is_transient(error):
            return ErrorAction.RETRY
        return ErrorAction.ESCALATE
