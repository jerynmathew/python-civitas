"""Registry — name-to-address routing table for the message bus."""

from __future__ import annotations

import asyncio
import dataclasses
import fnmatch
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Literal, Protocol, cast, runtime_checkable

logger = logging.getLogger(__name__)

# Listener signature: (name, capabilities, metadata, event)
# Called after every register() and deregister().
RegistryListener = Callable[
    [str, tuple[str, ...], dict[str, Any], Literal["register", "deregister"]],
    Awaitable[None],
]


@dataclasses.dataclass(frozen=True)
class RoutingEntry:
    """Routing metadata for a registered agent.

    ``address`` is the transport-level identifier used by the bus when
    calling ``transport.publish()``.  For in-process and NATS deployments
    this equals the agent name.  For ZMQ point-to-point it is the endpoint
    string (e.g. ``tcp://host:5555``).

    ``is_local`` is True when the agent runs inside this process, False for
    agents registered via cross-process discovery.

    ``capabilities`` is a tuple of capability tag strings declared by the
    agent (e.g. ``("text.summarize", "text.translate")``).

    ``capability_metadata`` is a free-form dict passed through verbatim to
    registry listeners (e.g. Presidium). The runtime never interprets it.
    """

    name: str
    address: str
    is_local: bool
    capabilities: tuple[str, ...] = ()
    capability_metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@runtime_checkable
class Registry(Protocol):  # pragma: no cover
    """Interface for agent routing tables.

    Reads are always synchronous — implementations keep an in-memory cache.
    How entries are *populated* (locally on start, or synced from a cluster
    discovery service) is an implementation detail hidden behind this interface.
    """

    def register(
        self,
        name: str,
        address: str | None = None,
        *,
        is_local: bool = True,
        capabilities: list[str] | tuple[str, ...] | None = None,
        capability_metadata: dict[str, Any] | None = None,
    ) -> None: ...
    def deregister(self, name: str) -> None: ...
    def lookup(self, name: str) -> RoutingEntry | None: ...
    def lookup_all(self, pattern: str) -> list[RoutingEntry]: ...
    def has(self, name: str) -> bool: ...
    def all_names(self) -> list[str]: ...
    def find_by_capability(self, tag: str) -> list[RoutingEntry]: ...


class LocalRegistry:
    """Single-node in-memory registry.

    Default implementation for single-process and same-node deployments.
    All reads are O(1) dict lookups — no I/O, no async.

    Remote agents can be registered via ``register_remote()`` so that
    pattern-based broadcast works across process boundaries; they are
    represented as ``RoutingEntry(is_local=False)`` and carry no object
    reference.

    Capability-based lookups (``find_by_capability``, ``find_by_capabilities``)
    work across both local and remote entries — capability tags are included
    in cross-process Worker announcements so every node has a complete view.

    Listeners registered via ``add_listener()`` are notified after every
    register/deregister. Intended for external governance systems (e.g.
    Presidium) that need a live view of the agent population.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RoutingEntry] = {}
        self._listeners: list[RegistryListener] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        address: str | None = None,
        *,
        is_local: bool = True,
        capabilities: list[str] | tuple[str, ...] | None = None,
        capability_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register an agent.

        ``address`` defaults to ``name`` when not given, which is correct
        for in-process and NATS transports.  Pass an explicit address for
        ZMQ TCP endpoints.

        Raises ``ValueError`` if the name is already registered.
        """
        if name in self._entries:
            raise ValueError(f"Process already registered: {name!r}")
        entry = RoutingEntry(
            name=name,
            address=address if address is not None else name,
            is_local=is_local,
            capabilities=tuple(capabilities) if capabilities else (),
            capability_metadata=dict(capability_metadata) if capability_metadata else {},
        )
        self._entries[name] = entry
        self._fire_listeners(entry, "register")

    def deregister(self, name: str) -> None:
        """Remove an agent. No-op if not registered."""
        entry = self._entries.pop(name, None)
        if entry is not None:
            self._fire_listeners(entry, "deregister")

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

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

    def find_by_capability(self, tag: str) -> list[RoutingEntry]:
        """Return all entries that declare the given capability tag."""
        return [e for e in self._entries.values() if tag in e.capabilities]

    def find_by_capabilities(
        self,
        tags: list[str] | tuple[str, ...],
        match: Literal["any", "all"] = "any",
    ) -> list[RoutingEntry]:
        """Return entries matching the given capability tags.

        ``match="any"`` (default): entry must declare at least one of the tags.
        ``match="all"``: entry must declare every tag.
        """
        tag_set = set(tags)
        if match == "all":
            return [e for e in self._entries.values() if tag_set <= set(e.capabilities)]
        return [e for e in self._entries.values() if tag_set & set(e.capabilities)]

    # ------------------------------------------------------------------
    # Remote agent support (cross-process discovery)
    # ------------------------------------------------------------------

    def register_remote(
        self,
        name: str,
        capabilities: list[str] | tuple[str, ...] | None = None,
        capability_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a remote agent for cross-process pattern matching.

        Idempotent for repeated announcements of the same remote agent.
        Raises ``ValueError`` if the name is already registered as local.
        """
        existing = self._entries.get(name)
        if existing is not None:
            if existing.is_local:
                raise ValueError(f"Cannot register {name!r} as remote: already registered as local")
            return  # idempotent re-announcement
        entry = RoutingEntry(
            name=name,
            address=name,
            is_local=False,
            capabilities=tuple(capabilities) if capabilities else (),
            capability_metadata=dict(capability_metadata) if capability_metadata else {},
        )
        self._entries[name] = entry
        self._fire_listeners(entry, "register")

    def register_b64(self, name: str, public_key_b64: str) -> None:
        """Register a remote agent's public key for signing verification.

        Used by the security layer — stores a RoutingEntry with no capability
        info, solely so the signing layer can look up the public key.
        This is a no-op if the agent is already registered.
        """
        if name not in self._entries:
            self._entries[name] = RoutingEntry(name=name, address=name, is_local=False)

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    # ------------------------------------------------------------------
    # Listeners (Presidium hook)
    # ------------------------------------------------------------------

    def add_listener(self, listener: RegistryListener) -> None:
        """Register a listener called after every register/deregister.

        Listeners receive (name, capabilities, capability_metadata, event).
        They are called as fire-and-forget tasks — the registry does not
        await them or handle their exceptions (logged at WARNING level).
        """
        self._listeners.append(listener)

    def remove_listener(self, listener: RegistryListener) -> None:
        """Remove a previously registered listener."""
        self._listeners = [l for l in self._listeners if l is not listener]  # noqa: E741

    def _fire_listeners(
        self,
        entry: RoutingEntry,
        event: Literal["register", "deregister"],
    ) -> None:
        if not self._listeners:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop — skip (e.g. called from sync test setup)
        for listener in self._listeners:
            coro = cast(
                Coroutine[Any, Any, None],
                listener(entry.name, entry.capabilities, entry.capability_metadata, event),
            )
            task: asyncio.Task[None] = loop.create_task(coro)
            task.add_done_callback(_log_listener_error)


def _log_listener_error(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.warning("Registry listener raised an exception: %s", task.exception())
