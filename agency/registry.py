"""Registry — named lookup for running AgentProcesses."""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

# Use Any for process type to avoid circular import with process.py.
# At runtime, values are AgentProcess instances.


class Registry:
    """In-memory process registry for Level 1 (single-process).

    Provides register, lookup, pattern-based lookup, and deregister.
    """

    def __init__(self) -> None:
        self._processes: dict[str, Any] = {}

    def register(self, name: str, process: Any) -> None:
        """Register a process under the given name."""
        if name in self._processes:
            raise ValueError(f"Process already registered: {name}")
        self._processes[name] = process

    def deregister(self, name: str) -> None:
        """Remove a process from the registry."""
        self._processes.pop(name, None)

    async def lookup(self, name: str) -> Any | None:
        """Look up a process by exact name. Returns None if not found."""
        return self._processes.get(name)

    async def lookup_all(self, pattern: str) -> list[Any]:
        """Look up all processes matching a glob pattern (e.g. 'tool_agents.*')."""
        return [
            proc
            for name, proc in self._processes.items()
            if fnmatch.fnmatch(name, pattern)
        ]

    def has(self, name: str) -> bool:
        """Check if a process is registered under the given name."""
        return name in self._processes

    def all_names(self) -> list[str]:
        """Return all registered process names."""
        return list(self._processes.keys())
