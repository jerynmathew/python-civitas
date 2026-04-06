"""AnthropicProvider — first-party Anthropic SDK integration (requires [anthropic] extra)."""

from __future__ import annotations

from typing import Any

from agency.plugins.model import ModelResponse, ToolCall

try:
    import anthropic

    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

# Known Anthropic pricing (USD per 1M tokens).
# Source: https://www.anthropic.com/pricing — update as pricing changes.
# Models not listed here return cost_usd=None (unknown, not zero).
_PRICING_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # (input $/M, output $/M)
    # Claude 4 family
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.8, 4.0),
    # Claude 3.7 / 3.5 family
    "claude-sonnet-4-5-20251001": (3.0, 15.0),
    "claude-3-7-sonnet-20250219": (3.0, 15.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-5-haiku-20241022": (0.8, 4.0),
    # Claude 3 family
    "claude-3-opus-20240229": (15.0, 75.0),
    "claude-3-sonnet-20240229": (3.0, 15.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
}


def _compute_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Return cost in USD for the given model and token counts, or None if unknown."""
    pricing = _PRICING_PER_M_TOKENS.get(model)
    if pricing is None:
        for key, val in _PRICING_PER_M_TOKENS.items():
            if model.startswith(key):
                pricing = val
                break
    if pricing is None:
        return None
    input_cost, output_cost = pricing
    return (tokens_in * input_cost + tokens_out * output_cost) / 1_000_000


class AnthropicProvider:
    """ModelProvider implementation backed by the Anthropic SDK.

    Requires ``pip install python-agency[anthropic]``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        max_retries: int = 3,
    ) -> None:
        if not _HAS_ANTHROPIC:
            raise ImportError(
                "The 'anthropic' package is required. "
                "Install it with: pip install python-agency[anthropic]"
            )
        # max_retries uses the SDK's built-in retry with exponential backoff,
        # handling RateLimitError (429) and OverloadedError (529) automatically.
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=max_retries)
        self._default_model = default_model
        self._max_tokens = max_tokens

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Send a chat request to the Anthropic API."""
        resolved_model = model or self._default_model

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        content = ""
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

        return ModelResponse(
            content=content,
            model=response.model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=_compute_cost(
                response.model, response.usage.input_tokens, response.usage.output_tokens
            ),
            tool_calls=tool_calls or None,
        )
