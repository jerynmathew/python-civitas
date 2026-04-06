"""GeminiProvider — Google Gemini API integration (requires [gemini] extra).

Supports Gemini 2.0 Flash, Gemini 1.5 Pro/Flash, and the full Gemini model family.

Install:
    pip install python-agency[gemini]

Usage:
    from agency.plugins.gemini import GeminiProvider

    runtime = Runtime(
        supervisor=...,
        model_provider=GeminiProvider(),   # reads GEMINI_API_KEY from env
    )

YAML:
    plugins:
      models:
        - type: gemini
          config:
            default_model: gemini-2.0-flash
"""

from __future__ import annotations

import os
from typing import Any

from agency.plugins.model import ModelResponse, ToolCall

try:
    import google.generativeai as genai

    _HAS_GEMINI = True
except ImportError:
    _HAS_GEMINI = False

# Known Gemini pricing (USD per 1M tokens).
# Source: https://ai.google.dev/pricing — update as pricing changes.
# Gemini pricing often varies by prompt length (<=128K vs >128K).
# Values here are for prompts <=128K tokens.
# Models not listed here return cost_usd=None (unknown, not zero).
_PRICING_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # (input $/M, output $/M)
    # Gemini 2.x family
    "gemini-2.0-flash": (0.075, 0.30),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.075, 0.30),
    # Gemini 1.5 family
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-flash-8b": (0.0375, 0.15),
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


def _to_gemini_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-style messages to Gemini content format.

    Gemini uses 'user'/'model' roles (not 'user'/'assistant') and the content
    is wrapped in a 'parts' list.
    """
    gemini_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        if role == "assistant":
            role = "model"
        elif role == "system":
            # Gemini does not have a system role in content history — prepend
            # as a user message so the model sees the instruction.
            gemini_messages.append({"role": "user", "parts": [content]})
            gemini_messages.append({"role": "model", "parts": ["Understood."]})
            continue
        gemini_messages.append({"role": role, "parts": [content]})
    return gemini_messages


class GeminiProvider:
    """ModelProvider implementation backed by the Google Generative AI SDK.

    Requires ``pip install python-agency[gemini]``.

    Args:
        api_key:        Google AI API key. Defaults to ``GEMINI_API_KEY`` env var.
        default_model:  Model used when ``chat()`` is called with ``model=None``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gemini-2.0-flash",
    ) -> None:
        if not _HAS_GEMINI:
            raise ImportError(
                "The 'google-generativeai' package is required. "
                "Install it with: pip install python-agency[gemini]"
            )
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        genai.configure(api_key=resolved_key)
        self._default_model = default_model

    async def chat(
        self,
        model: str | None,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Send a generation request to the Gemini API."""
        resolved_model = model or self._default_model
        gemini_model = genai.GenerativeModel(resolved_model)

        gemini_messages = _to_gemini_messages(messages)

        # Last message must be from the user — split it off as the prompt
        if gemini_messages and gemini_messages[-1]["role"] == "user":
            prompt = gemini_messages[-1]["parts"][0]
            history = gemini_messages[:-1]
        else:
            prompt = ""
            history = gemini_messages

        chat = gemini_model.start_chat(history=history)
        response = await chat.send_message_async(prompt)

        content = response.text or ""
        tokens_in = response.usage_metadata.prompt_token_count or 0
        tokens_out = response.usage_metadata.candidates_token_count or 0

        # Tool calls: Gemini function calling maps to ToolCall
        tool_calls: list[ToolCall] = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=fc.name,
                            name=fc.name,
                            input=dict(fc.args),
                        )
                    )

        return ModelResponse(
            content=content,
            model=resolved_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_compute_cost(resolved_model, tokens_in, tokens_out),
            tool_calls=tool_calls or None,
        )
