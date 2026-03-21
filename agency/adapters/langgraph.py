"""LangGraphAgent — run a LangGraph compiled graph as an AgentProcess.

Wraps any LangGraph ``CompiledGraph`` so it gains Agency supervision, OTEL
tracing, and transport-agnostic messaging. Under 10 lines of core logic.

Usage:
    from langgraph.graph import StateGraph
    from agency.adapters.langgraph import LangGraphAgent

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

from agency.errors import ErrorAction
from agency.messages import Message
from agency.process import AgentProcess


class LangGraphAgent(AgentProcess):
    """Wraps a LangGraph CompiledGraph as an Agency AgentProcess.

    The graph receives ``message.payload`` as input and its output
    dict is returned as the reply payload.
    """

    def __init__(self, name: str, graph: Any, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._graph = graph

    async def handle(self, message: Message) -> Message | None:
        """Invoke the LangGraph compiled graph with the message payload."""
        output = await self._graph.ainvoke(message.payload)
        return self.reply(output if isinstance(output, dict) else {"output": output})

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        """Escalate all errors to the supervisor."""
        return ErrorAction.ESCALATE
