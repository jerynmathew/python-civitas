"""MistralProvider — Mistral AI API integration (requires [mistral] extra).

Supports Mistral Large, Mistral Small, Codestral, and the full Mistral model family.

Install:
    pip install civitas[mistral]

Usage:
    from civitas.plugins.mistral import MistralProvider

    runtime = Runtime(
        supervisor=...,
        model_provider=MistralProvider(),   # reads MISTRAL_API_KEY from env
    )

YAML:
    plugins:
      models:
        - type: mistral
          config:
            default_model: mistral-large-latest
"""

from __future__ import annotations

import json
from typing import Any

from civitas.plugins.model import ModelResponse, ToolCall

try:
    from mistralai import Mistral as _Mistral

    _HAS_MISTRAL = True
except ImportError:
    _HAS_MISTRAL = False

# Known Mistral pricing (USD per 1M tokens).
# Source: https://mistral.ai/technology/#pricing — update as pricing changes.
# Models not listed here return cost_usd=None (unknown, not zero).
_PRICING_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # (input $/M, output $/M)
    # Premier models
    "mistral-large-latest": (2.00, 6.00),
    "mistral-medium-latest": (0.40, 2.00),
    "mistral-small-latest": (0.20, 0.60),
    # Specialised
    "codestral-latest": (0.20, 0.60),
    "mistral-embed": (0.10, 0.10),
    # Open-weight hosted
    "open-mistral-nemo": (0.15, 0.15),
    "open-mixtral-8x22b": (2.00, 6.00),
}


def _compute_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Return cost in USD for the given model and token counts, or None if unknown."""
    pricing = _PRICING_PER_M_TOKENS.get(model)
    if pricing is None:
        for key, val in _PRICING_PER_M_TOKENS.items():
            if model.startswith(key.removesuffix("-latest")):
                pricing = val
                break
    if pricing is None:
        return None
    input_cost, output_cost = pricing
    return (tokens_in * input_cost + tokens_out * output_cost) / 1_000_000


class MistralProvider:
    """ModelProvider implementation backed by the Mistral AI SDK.

    Requires ``pip install civitas[mistral]``.

    Args:
        api_key:        Mistral API key. Defaults to ``MISTRAL_API_KEY`` env var.
        default_model:  Model used when ``chat()`` is called with ``model=None``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "mistral-large-latest",
    ) -> None:
        if not _HAS_MISTRAL:
            raise ImportError(
                "The 'mistralai' package is required. Install it with: pip install civitas[mistral]"
            )
        self._client = _Mistral(api_key=api_key)
        self._default_model = default_model

    async def chat(
        self,
        model: str | None,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Send a chat completion request to the Mistral API."""
        resolved_model = model or self._default_model

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.chat.complete_async(**kwargs)

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
            model=response.model or resolved_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_compute_cost(resolved_model, tokens_in, tokens_out),
            tool_calls=tool_calls or None,
        )
