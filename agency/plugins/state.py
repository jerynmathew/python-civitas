"""StateStore protocol and InMemoryStateStore implementation."""

from __future__ import annotations

from typing import Any, Protocol


class StateStore(Protocol):
    """Protocol for agent state persistence."""

    async def get(self, agent_name: str) -> dict[str, Any] | None: ...
    async def set(self, agent_name: str, state: dict[str, Any]) -> None: ...
    async def delete(self, agent_name: str) -> None: ...


class InMemoryStateStore:
    """Default state store — in-memory, no persistence. State is lost on restart."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def get(self, agent_name: str) -> dict[str, Any] | None:
        return self._data.get(agent_name)

    async def set(self, agent_name: str, state: dict[str, Any]) -> None:
        self._data[agent_name] = state

    async def delete(self, agent_name: str) -> None:
        self._data.pop(agent_name, None)
