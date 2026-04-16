"""OpenAIProvider — OpenAI API integration (requires [openai] extra).

Supports GPT-4o, GPT-4o-mini, o1, o3, and compatible endpoints.

Install:
    pip install civitas[openai]

Usage:
    from civitas.plugins.openai import OpenAIProvider

    runtime = Runtime(
        supervisor=...,
        model_provider=OpenAIProvider(),   # reads OPENAI_API_KEY from env
    )

YAML:
    plugins:
      models:
        - type: openai
          config:
            default_model: gpt-4o
"""

from __future__ import annotations

import json
from typing import Any

from civitas.plugins.model import ModelResponse, ToolCall

try:
    import openai as _openai

    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

# Known OpenAI pricing (USD per 1M tokens).
# Source: https://openai.com/api/pricing — update as pricing changes.
# Models not listed here return cost_usd=None (unknown, not zero).
_PRICING_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # (input $/M, output $/M)
    # GPT-4o family
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-audio-preview": (2.50, 10.00),
    # o-series reasoning models
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o1-pro": (150.00, 600.00),
    "o3": (10.00, 40.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    # GPT-4 Turbo (legacy)
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4-turbo-preview": (10.00, 30.00),
}


def _compute_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Return cost in USD for the given model and token counts, or None if unknown."""
    pricing = _PRICING_PER_M_TOKENS.get(model)
    if pricing is None:
        # prefix match for versioned model IDs (e.g. "gpt-4o-2024-11-20")
        for key, val in _PRICING_PER_M_TOKENS.items():
            if model.startswith(key):
                pricing = val
                break
    if pricing is None:
        return None
    input_cost, output_cost = pricing
    return (tokens_in * input_cost + tokens_out * output_cost) / 1_000_000


class OpenAIProvider:
    """ModelProvider implementation backed by the OpenAI SDK.

    Requires ``pip install civitas[openai]``.

    Args:
        api_key:        OpenAI API key. Defaults to ``OPENAI_API_KEY`` env var.
        default_model:  Model used when ``chat()`` is called with ``model=None``.
        base_url:       Override the API base URL (e.g. for Azure OpenAI or
                        compatible endpoints like Together AI, Fireworks AI).
        max_retries:    Number of automatic retries on transient errors (429, 5xx).
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
        base_url: str | None = None,
        max_retries: int = 3,
    ) -> None:
        if not _HAS_OPENAI:
            raise ImportError(
                "The 'openai' package is required. Install it with: pip install civitas[openai]"
            )
        self._client = _openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
        )
        self._default_model = default_model

    async def chat(
        self,
        model: str | None,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Send a chat completion request to the OpenAI API."""
        resolved_model = model or self._default_model

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""

        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=json.loads(tc.function.arguments),
                    )
                )

        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0

        return ModelResponse(
            content=content,
            model=response.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_compute_cost(response.model, tokens_in, tokens_out),
            tool_calls=tool_calls or None,
        )
