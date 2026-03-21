"""Centralized configuration — single source for all environment variables.

Usage:
    from agency.config import settings
    serializer_name = settings.serializer
"""

from __future__ import annotations

import os


class Settings:
    """Read-only access to Agency environment variables.

    All environment variable reads are centralized here. Application code
    should never call ``os.environ`` directly — use ``settings.<property>``
    instead.
    """

    @property
    def serializer(self) -> str:
        """Serializer format: ``'msgpack'`` (default) or ``'json'``."""
        return os.environ.get("AGENCY_SERIALIZER", "msgpack")

    @property
    def otel_endpoint(self) -> str | None:
        """OTEL collector gRPC endpoint, or ``None`` for console export."""
        return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    @property
    def anthropic_api_key(self) -> str | None:
        """Anthropic API key for AnthropicProvider."""
        return os.environ.get("ANTHROPIC_API_KEY")

    @property
    def openai_api_key(self) -> str | None:
        """OpenAI API key (used via LiteLLM)."""
        return os.environ.get("OPENAI_API_KEY")

    @property
    def gemini_api_key(self) -> str | None:
        """Google Gemini API key (used via LiteLLM)."""
        return os.environ.get("GEMINI_API_KEY")

    @property
    def fiddler_api_key(self) -> str | None:
        """Fiddler API key for the Fiddler exporter plugin."""
        return os.environ.get("FIDDLER_API_KEY")

    @property
    def nats_url(self) -> str:
        """NATS server URL for distributed transport."""
        return os.environ.get("NATS_URL", "nats://localhost:4222")


settings = Settings()
