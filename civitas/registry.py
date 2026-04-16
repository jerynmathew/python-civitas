"""Registry — name-to-address routing table for the message bus."""

from __future__ import annotations

import dataclasses
import fnmatch
from typing import Protocol, runtime_checkable


@dataclasses.dataclass(frozen=True)
class RoutingEntry:
    """Routing metadata for a registered agent.

    ``address`` is the transport-level identifier used by the bus when
    calling ``transport.publish()``.  For in-process and NATS deployments
    this equals the agent name.  For ZMQ point-to-point it is the endpoint
    string (e.g. ``tcp://host:5555``).

    ``is_local`` is True when the agent runs inside this process, False for
    agents registered via cross-process discovery.
    """

    name: str
    address: str
    is_local: bool


@runtime_checkable
class Registry(Protocol):  # pragma: no cover
    """Interface for agent routing tables.

    Reads are always synchronous — implementations keep an in-memory cache.
    How entries are *populated* (locally on start, or synced from a cluster
    discovery service) is an implementation detail hidden behind this interface.
    """

    def register(self, name: str, address: str | None = None, *, is_local: bool = True) -> None: ...
    def deregister(self, name: str) -> None: ...
    def lookup(self, name: str) -> RoutingEntry | None: ...
    def lookup_all(self, pattern: str) -> list[RoutingEntry]: ...
    def has(self, name: str) -> bool: ...
    def all_names(self) -> list[str]: ...


class LocalRegistry:
    """Single-node in-memory registry.

    Default implementation for single-process and same-node deployments.
    All reads are O(1) dict lookups — no I/O, no async.

    Remote agents can be registered via ``register_remote()`` so that
    pattern-based broadcast works across process boundaries; they are
    represented as ``RoutingEntry(is_local=False)`` and carry no object
    reference.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RoutingEntry] = {}

    def register(self, name: str, address: str | None = None, *, is_local: bool = True) -> None:
        """Register an agent.

        ``address`` defaults to ``name`` when not given, which is correct
        for in-process and NATS transports.  Pass an explicit address for
        ZMQ TCP endpoints.

        Raises ``ValueError`` if the name is already registered.
        """
        if name in self._entries:
            raise ValueError(f"Process already registered: {name!r}")
        self._entries[name] = RoutingEntry(
            name=name,
            address=address if address is not None else name,
            is_local=is_local,
        )

    def deregister(self, name: str) -> None:
        """Remove an agent. No-op if not registered."""
        self._entries.pop(name, None)

    def lookup(self, name: str) -> RoutingEntry | None:
        """Return the RoutingEntry for ``name``, or None if not registered."""
        return self._entries.get(name)

    def lookup_all(self, pattern: str) -> list[RoutingEntry]:
        """Return all entries whose name matches a glob pattern."""
        return [entry for name, entry in self._entries.items() if fnmatch.fnmatch(name, pattern)]

    def has(self, name: str) -> bool:
        """Return True if the name is registered."""
        return name in self._entries

    def all_names(self) -> list[str]:
        """Return all registered names."""
        return list(self._entries.keys())

    def register_remote(self, name: str) -> None:
        """Register a remote agent for cross-process pattern matching.

        Idempotent for repeated announcements of the same remote agent.
        Raises ``ValueError`` if the name is already registered as local.
        """
        existing = self._entries.get(name)
        if existing is not None:
            if existing.is_local:
                raise ValueError(f"Cannot register {name!r} as remote: already registered as local")
            return  # idempotent re-announcement
        self._entries[name] = RoutingEntry(name=name, address=name, is_local=False)
