"""ModelProvider protocol and ModelResponse dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ToolCall:
    """A single tool call requested by the model.

    Normalized across providers: Anthropic ``tool_use`` blocks and LiteLLM
    ``tool_calls`` entries both map to this shape.
    """

    id: str
    name: str
    input: dict[str, Any]


@dataclass(slots=True)
class ModelResponse:
    """Response from an LLM call."""

    content: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None = None
    """Computed cost in USD, or None if the model's pricing is not known."""
    tool_calls: list[ToolCall] | None = None


class ModelProvider(Protocol):
    """Protocol for LLM invocation abstraction."""

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Send a chat completion request to the model."""
        ...
