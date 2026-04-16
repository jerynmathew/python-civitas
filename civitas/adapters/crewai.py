"""CrewAI adapter — not yet implemented."""

from __future__ import annotations


class CrewAIAgent:
    """Placeholder — CrewAI adapter is not yet implemented.

    Raises NotImplementedError on instantiation so callers get a clear
    message rather than an import-time AttributeError.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "CrewAIAgent is not yet implemented. "
            "Track progress at https://github.com/anthropics/civitas/issues."
        )
