"""Civitas error hierarchy and ErrorAction enum."""

from __future__ import annotations

from enum import Enum


class ErrorAction(Enum):
    """Actions an agent can take when an error occurs in handle()."""

    RETRY = "RETRY"
    """Re-deliver the same message (up to retry limit)."""

    SKIP = "SKIP"
    """Discard the failed message, continue with next."""

    ESCALATE = "ESCALATE"
    """Crash the process — supervisor applies restart strategy."""

    STOP = "STOP"
    """Graceful shutdown of this process."""


class CivitasError(Exception):
    """Base exception for all Civitas runtime errors."""


class TransientError(CivitasError):
    """A transient, retryable error (e.g. network timeout, rate limit)."""


class MessageValidationError(CivitasError):
    """A message failed validation (e.g. reserved type prefix, non-serializable payload)."""


class MessageRoutingError(CivitasError):
    """A message could not be routed (e.g. unknown recipient)."""


class ConfigurationError(CivitasError):
    """Invalid or missing runtime configuration."""


class DeserializationError(CivitasError):
    """Raised when incoming bytes cannot be decoded into a Message.

    Provides a stable exception contract regardless of whether msgpack or JSON
    is in use — callers never need to catch library-specific exceptions.
    """


class PluginError(CivitasError):
    """Raised when a plugin cannot be loaded or instantiated.

    Inherits from CivitasError so callers catching the Civitas error hierarchy
    also catch plugin load failures.
    """

    def __init__(self, plugin_type: str, name: str, reason: str) -> None:
        self.plugin_type = plugin_type
        self.name = name
        self.reason = reason
        super().__init__(
            f"Failed to load {plugin_type} plugin '{name}': {reason}\n"
            f"  Hint: pip install civitas[{name}]"
        )


class SpawnError(CivitasError):
    """Raised when a dynamic agent spawn, despawn, or stop operation fails."""
