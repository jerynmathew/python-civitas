"""Tests for Registry: register, lookup, deregister, pattern match."""

import pytest

from agency.registry import Registry


class FakeProcess:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def registry() -> Registry:
    return Registry()


def test_register_and_lookup(registry: Registry):
    """Register a process and look it up by name."""
    proc = FakeProcess("agent_a")
    registry.register("agent_a", proc)
    assert registry.has("agent_a")


async def test_lookup_returns_process(registry: Registry):
    """lookup() returns the registered process."""
    proc = FakeProcess("agent_a")
    registry.register("agent_a", proc)
    result = await registry.lookup("agent_a")
    assert result is proc


async def test_lookup_returns_none_for_missing(registry: Registry):
    """lookup() returns None for an unregistered name."""
    result = await registry.lookup("nonexistent")
    assert result is None


def test_deregister(registry: Registry):
    """deregister() removes the process."""
    proc = FakeProcess("agent_a")
    registry.register("agent_a", proc)
    registry.deregister("agent_a")
    assert not registry.has("agent_a")


def test_deregister_missing_is_noop(registry: Registry):
    """deregister() on a missing name does not raise."""
    registry.deregister("nonexistent")  # should not raise


def test_register_duplicate_raises(registry: Registry):
    """Registering the same name twice raises ValueError."""
    proc = FakeProcess("agent_a")
    registry.register("agent_a", proc)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("agent_a", proc)


async def test_lookup_all_pattern(registry: Registry):
    """lookup_all() matches processes by glob pattern."""
    registry.register("tool_agents.search", FakeProcess("tool_agents.search"))
    registry.register("tool_agents.calc", FakeProcess("tool_agents.calc"))
    registry.register("summarizer", FakeProcess("summarizer"))

    matches = await registry.lookup_all("tool_agents.*")
    assert len(matches) == 2
    names = {p.name for p in matches}
    assert names == {"tool_agents.search", "tool_agents.calc"}


async def test_lookup_all_no_matches(registry: Registry):
    """lookup_all() returns empty list when no processes match."""
    registry.register("agent_a", FakeProcess("agent_a"))
    matches = await registry.lookup_all("nonexistent.*")
    assert matches == []


def test_all_names(registry: Registry):
    """all_names() returns list of all registered names."""
    registry.register("a", FakeProcess("a"))
    registry.register("b", FakeProcess("b"))
    assert set(registry.all_names()) == {"a", "b"}
