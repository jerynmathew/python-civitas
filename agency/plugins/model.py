"""ModelProvider protocol and ModelResponse dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ModelResponse:
    """Response from an LLM call."""

    content: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    tool_calls: list[dict[str, Any]] | None = None


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
