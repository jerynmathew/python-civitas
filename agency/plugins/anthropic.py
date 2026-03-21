"""AnthropicProvider — Phase 1 reference implementation (requires [anthropic] extra)."""

from __future__ import annotations

from typing import Any

from agency.plugins.model import ModelResponse

try:
    import anthropic

    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


class AnthropicProvider:
    """ModelProvider implementation backed by the Anthropic SDK.

    Requires ``pip install python-agency[anthropic]``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        if not _HAS_ANTHROPIC:
            raise ImportError(
                "The 'anthropic' package is required. "
                "Install it with: pip install python-agency[anthropic]"
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model
        self._max_tokens = max_tokens

    async def chat(
        self,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Send a chat request to the Anthropic API."""
        resolved_model = model or self._default_model
        msgs = messages or []

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": self._max_tokens,
            "messages": msgs,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return ModelResponse(
            content=content,
            model=response.model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=0.0,  # cost calculation deferred to M1.5
        )
