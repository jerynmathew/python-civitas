"""Agency error hierarchy and ErrorAction enum."""

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


class AgencyError(Exception):
    """Base exception for all Agency runtime errors."""


class TransientError(AgencyError):
    """A transient, retryable error (e.g. network timeout, rate limit)."""


class MessageValidationError(AgencyError):
    """A message failed validation (e.g. reserved type prefix, non-serializable payload)."""


class MessageRoutingError(AgencyError):
    """A message could not be routed (e.g. unknown recipient)."""


class ConfigurationError(AgencyError):
    """Invalid or missing runtime configuration."""


class DeserializationError(AgencyError):
    """Raised when incoming bytes cannot be decoded into a Message.

    Provides a stable exception contract regardless of whether msgpack or JSON
    is in use — callers never need to catch library-specific exceptions.
    """
