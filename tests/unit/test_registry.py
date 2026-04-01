"""Tests for LocalRegistry: routing entries, lookup, deregister, pattern match."""

import pytest

from agency.registry import LocalRegistry, RoutingEntry


@pytest.fixture
def registry() -> LocalRegistry:
    return LocalRegistry()


def test_register_and_has(registry: LocalRegistry):
    """Registering a name makes has() return True."""
    registry.register("agent_a")
    assert registry.has("agent_a")


def test_register_returns_routing_entry(registry: LocalRegistry):
    """lookup() returns a RoutingEntry with correct fields."""
    registry.register("agent_a")
    entry = registry.lookup("agent_a")
    assert entry is not None
    assert isinstance(entry, RoutingEntry)
    assert entry.name == "agent_a"
    assert entry.address == "agent_a"  # defaults to name
    assert entry.is_local is True


def test_register_explicit_address(registry: LocalRegistry):
    """register() accepts an explicit address distinct from name."""
    registry.register("worker_1", address="tcp://host:5555")
    entry = registry.lookup("worker_1")
    assert entry is not None
    assert entry.name == "worker_1"
    assert entry.address == "tcp://host:5555"
    assert entry.is_local is True


def test_lookup_returns_none_for_missing(registry: LocalRegistry):
    """lookup() returns None for an unregistered name."""
    assert registry.lookup("nonexistent") is None


def test_deregister(registry: LocalRegistry):
    """deregister() removes the entry."""
    registry.register("agent_a")
    registry.deregister("agent_a")
    assert not registry.has("agent_a")


def test_deregister_missing_is_noop(registry: LocalRegistry):
    """deregister() on a missing name does not raise."""
    registry.deregister("nonexistent")  # should not raise


def test_register_duplicate_raises(registry: LocalRegistry):
    """Registering the same name twice raises ValueError."""
    registry.register("agent_a")
    with pytest.raises(ValueError, match="already registered"):
        registry.register("agent_a")


def test_lookup_all_pattern(registry: LocalRegistry):
    """lookup_all() matches entries by glob pattern."""
    registry.register("tool_agents.search")
    registry.register("tool_agents.calc")
    registry.register("summarizer")

    matches = registry.lookup_all("tool_agents.*")
    assert len(matches) == 2
    names = {e.name for e in matches}
    assert names == {"tool_agents.search", "tool_agents.calc"}


def test_lookup_all_no_matches(registry: LocalRegistry):
    """lookup_all() returns empty list when no entries match."""
    registry.register("agent_a")
    assert registry.lookup_all("nonexistent.*") == []


def test_all_names(registry: LocalRegistry):
    """all_names() returns all registered names."""
    registry.register("a")
    registry.register("b")
    assert set(registry.all_names()) == {"a", "b"}


def test_all_names_after_deregister(registry: LocalRegistry):
    """all_names() is consistent after deregister."""
    registry.register("a")
    registry.register("b")
    registry.deregister("a")
    assert registry.all_names() == ["b"]


def test_register_remote_creates_non_local_entry(registry: LocalRegistry):
    """register_remote() creates a RoutingEntry with is_local=False."""
    registry.register_remote("remote_1")
    entry = registry.lookup("remote_1")
    assert entry is not None
    assert entry.name == "remote_1"
    assert entry.is_local is False


def test_register_remote_idempotent(registry: LocalRegistry):
    """register_remote() is idempotent for the same remote name."""
    registry.register_remote("remote_1")
    registry.register_remote("remote_1")  # should not raise
    assert registry.has("remote_1")


def test_register_remote_raises_if_already_local(registry: LocalRegistry):
    """register_remote() raises if the name is already a local registration."""
    registry.register("agent_a")
    with pytest.raises(ValueError, match="already registered as local"):
        registry.register_remote("agent_a")


def test_lookup_all_includes_remote_entries(registry: LocalRegistry):
    """lookup_all() returns remote entries that match the pattern."""
    registry.register_remote("remote_1")
    registry.register_remote("remote_2")
    matches = registry.lookup_all("remote_*")
    assert len(matches) == 2
    assert all(not e.is_local for e in matches)
