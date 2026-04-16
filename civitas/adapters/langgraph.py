"""LangGraphAgent — run a LangGraph compiled graph as an AgentProcess.

Wraps any LangGraph ``CompiledGraph`` so it gains Civitas supervision, OTEL
tracing, and transport-agnostic messaging.

Usage:
    from langgraph.graph import StateGraph
    from civitas.adapters.langgraph import LangGraphAgent

    graph = StateGraph(...)  # define your graph
    compiled = graph.compile()

    runtime = Runtime(
        supervisor=Supervisor("root", children=[
            LangGraphAgent("my_graph", graph=compiled),
        ])
    )
"""

from __future__ import annotations

from typing import Any

from civitas.errors import ErrorAction
from civitas.messages import Message
from civitas.process import AgentProcess


class LangGraphAgent(AgentProcess):
    """Wraps a LangGraph CompiledGraph as a Civitas AgentProcess.

    The graph receives ``message.payload`` as input and its output
    dict is returned as the reply payload.

    Args:
        name:         Civitas agent name.
        graph:        LangGraph compiled graph.
        input_schema: Optional callable/type to coerce the message payload
                      before passing to ainvoke(). Useful for typed TypedDict
                      state schemas — catches payload mismatches early with a
                      clear error rather than a deep LangGraph ValidationError.
    """

    def __init__(
        self,
        name: str,
        graph: Any,
        input_schema: type[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._graph = graph
        self._input_schema = input_schema  # F10-4: optional payload coercion

    async def handle(self, message: Message) -> Message | None:
        """Invoke the LangGraph compiled graph with the message payload."""
        # F10-4: coerce payload through input_schema if provided
        payload = self._input_schema(**message.payload) if self._input_schema else message.payload
        output = await self._graph.ainvoke(payload)
        return self.reply(output if isinstance(output, dict) else {"output": output})

    def _is_transient(self, error: Exception) -> bool:
        """Return True for errors that should be retried rather than escalated.

        Subclasses can override to add retry logic for known-transient errors.
        """
        return False

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        """Retry transient errors; escalate all others to the supervisor."""
        if message.attempt < self._max_retries and self._is_transient(error):
            return ErrorAction.RETRY
        return ErrorAction.ESCALATE
