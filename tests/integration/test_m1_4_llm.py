"""M1.4 — LLM + Tools testable criteria.

Uses a mock ModelProvider — no real API calls.
"""

import asyncio
from typing import Any

import pytest

from agency import AgentProcess, Runtime, Supervisor
from agency.errors import ErrorAction
from agency.messages import Message
from agency.plugins.model import ModelProvider, ModelResponse
from agency.plugins.tools import ToolRegistry


# ------------------------------------------------------------------
# Mock ModelProvider
# ------------------------------------------------------------------


class MockModelProvider:
    """In-memory ModelProvider for testing."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = fail

    async def chat(
        self,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        self.calls.append({"model": model, "messages": messages, "tools": tools})
        if self._fail:
            raise RuntimeError("LLM unavailable")
        return ModelResponse(
            content="Mock response",
            model=model or "mock-model",
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.001,
        )


# ------------------------------------------------------------------
# Mock ToolProvider
# ------------------------------------------------------------------


class MockWebSearch:
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": "web_search",
            "description": "Search the web",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        return {"results": [f"Result for: {kwargs.get('query', '')}"]}


# ------------------------------------------------------------------
# Test agents
# ------------------------------------------------------------------


class LLMAgent(AgentProcess):
    """Agent that calls self.llm.chat()."""

    async def handle(self, message: Message) -> Message | None:
        response = await self.llm.chat(
            model="test-model",
            messages=[{"role": "user", "content": message.payload.get("prompt", "")}],
        )
        return self.reply({
            "content": response.content,
            "model": response.model,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
        })


class ToolAgent(AgentProcess):
    """Agent that uses self.tools."""

    async def handle(self, message: Message) -> Message | None:
        tool = self.tools.get("web_search")
        if tool is None:
            return self.reply({"error": "tool not found"})
        result = await tool.execute(query=message.payload.get("query", ""))
        return self.reply({"tool_result": result})


class LLMErrorAgent(AgentProcess):
    """Agent that handles LLM errors via on_error."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.error_caught: Exception | None = None

    async def handle(self, message: Message) -> Message | None:
        response = await self.llm.chat(
            model="test-model",
            messages=[{"role": "user", "content": "test"}],
        )
        return self.reply({"content": response.content})

    async def on_error(self, error: Exception, message: Message) -> ErrorAction:
        self.error_caught = error
        return ErrorAction.SKIP


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


async def test_model_provider_loads():
    """ModelProvider plugin (mock) loads and is accessible via self.llm."""
    provider = MockModelProvider()
    agent = LLMAgent("llm_agent")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[agent]),
        model_provider=provider,
    )
    await runtime.start()
    try:
        assert agent.llm is provider
    finally:
        await runtime.stop()


async def test_agent_calls_llm_chat():
    """Agent calls self.llm.chat() and receives a response."""
    provider = MockModelProvider()
    runtime = Runtime(
        supervisor=Supervisor("root", children=[LLMAgent("llm_agent")]),
        model_provider=provider,
    )
    await runtime.start()
    try:
        result = await runtime.ask("llm_agent", {"prompt": "Hello"})
        assert result.payload["content"] == "Mock response"
        assert result.payload["model"] == "test-model"
        assert len(provider.calls) == 1
        assert provider.calls[0]["messages"][0]["content"] == "Hello"
    finally:
        await runtime.stop()


async def test_llm_call_includes_token_counts():
    """LLM call response includes token counts."""
    provider = MockModelProvider()
    runtime = Runtime(
        supervisor=Supervisor("root", children=[LLMAgent("llm_agent")]),
        model_provider=provider,
    )
    await runtime.start()
    try:
        result = await runtime.ask("llm_agent", {"prompt": "test"})
        assert result.payload["tokens_in"] == 10
        assert result.payload["tokens_out"] == 20
    finally:
        await runtime.stop()


async def test_tool_provider_registers_with_schema():
    """ToolProvider plugin registers a tool with schema."""
    tools = ToolRegistry()
    tool = MockWebSearch()
    tools.register(tool)

    assert tools.get("web_search") is tool
    assert tool.schema["name"] == "web_search"
    assert "input_schema" in tool.schema


async def test_agent_invokes_tool():
    """Agent invokes tool via self.tools.get("web_search")."""
    tools = ToolRegistry()
    tools.register(MockWebSearch())

    runtime = Runtime(
        supervisor=Supervisor("root", children=[ToolAgent("tool_agent")]),
        tool_registry=tools,
    )
    await runtime.start()
    try:
        result = await runtime.ask("tool_agent", {"query": "python agency"})
        assert result.payload["tool_result"]["results"][0] == "Result for: python agency"
    finally:
        await runtime.stop()


async def test_tool_accessible_via_self_tools():
    """Tools are injected and accessible via self.tools in the agent."""
    tools = ToolRegistry()
    tools.register(MockWebSearch())

    agent = ToolAgent("tool_agent")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[agent]),
        tool_registry=tools,
    )
    await runtime.start()
    try:
        assert agent.tools is tools
        assert agent.tools.get("web_search") is not None
        assert "web_search" in agent.tools.names()
    finally:
        await runtime.stop()


async def test_llm_error_triggers_on_error():
    """Error in LLM call triggers on_error() with typed exception."""
    provider = MockModelProvider(fail=True)
    agent = LLMErrorAgent("error_agent")
    runtime = Runtime(
        supervisor=Supervisor("root", children=[agent]),
        model_provider=provider,
    )
    await runtime.start()
    try:
        # Send a message — the LLM call will fail, on_error will SKIP
        await runtime.send("error_agent", {"prompt": "test"})
        await asyncio.sleep(0.1)

        assert agent.error_caught is not None
        assert isinstance(agent.error_caught, RuntimeError)
        assert "LLM unavailable" in str(agent.error_caught)
    finally:
        await runtime.stop()
