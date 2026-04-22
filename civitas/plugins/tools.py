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
        """Register a tool by its name.

        Raises ``ValueError`` on duplicate name — silent overwrite would cause
        the wrong implementation to be called since names are used by the model.
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name!r}. Deregister the existing tool first."
            )
        self._tools[tool.name] = tool

    def deregister(self, name: str) -> None:
        """Remove a tool by name. No-op if not registered."""
        self._tools.pop(name, None)

    def deregister_prefix(self, prefix: str) -> None:
        """Remove all tools whose name starts with prefix."""
        to_remove = [k for k in self._tools if k.startswith(prefix)]
        for k in to_remove:
            del self._tools[k]

    def get(self, name: str) -> ToolProvider | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolProvider]:
        """Return all registered tools."""
        return list(self._tools.values())

    def names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())
