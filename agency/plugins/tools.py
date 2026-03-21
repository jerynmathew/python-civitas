"""ToolProvider protocol and ToolRegistry."""

from __future__ import annotations

from typing import Any, Protocol


class ToolProvider(Protocol):
    """Protocol for external tool/API invocation with schema."""

    @property
    def name(self) -> str:
        """Human-readable tool name used for lookup."""
        ...

    @property
    def schema(self) -> dict[str, Any]:
        """JSON Schema describing the tool's input parameters."""
        ...

    async def execute(self, **kwargs: Any) -> Any:
        """Invoke the tool with the given keyword arguments."""
        ...


class ToolRegistry:
    """Holds registered tools, injected into AgentProcess as self.tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolProvider] = {}

    def register(self, tool: ToolProvider) -> None:
        """Register a tool by its name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolProvider | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def all(self) -> list[ToolProvider]:
        """Return all registered tools."""
        return list(self._tools.values())

    def names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())
