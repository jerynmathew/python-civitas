"""Supervisor — monitors child processes and applies restart strategies on failure."""

from __future__ import annotations

import asyncio
import random
import time
from enum import Enum
from typing import TYPE_CHECKING, Any

from agency.process import AgentProcess, ProcessStatus

if TYPE_CHECKING:
    from agency.bus import MessageBus
    from agency.observability.tracer import Tracer
    from agency.registry import Registry


class RestartStrategy(Enum):
    ONE_FOR_ONE = "ONE_FOR_ONE"
    ONE_FOR_ALL = "ONE_FOR_ALL"
    REST_FOR_ONE = "REST_FOR_ONE"


class BackoffPolicy(Enum):
    CONSTANT = "CONSTANT"
    LINEAR = "LINEAR"
    EXPONENTIAL = "EXPONENTIAL"


class Supervisor:
    """Manages child processes with restart strategies.

    When a child crashes, the supervisor applies the configured restart
    strategy. If max_restarts is exceeded within restart_window, the
    supervisor escalates to its parent or stops permanently.
    """

    def __init__(
        self,
        name: str,
        children: list[AgentProcess | Supervisor] | None = None,
        strategy: str = "ONE_FOR_ONE",
        max_restarts: int = 3,
        restart_window: float = 60.0,
        backoff: str = "CONSTANT",
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
    ) -> None:
        self.name = name
        self.children: list[AgentProcess | Supervisor] = children or []
        self.strategy = RestartStrategy(strategy)
        self.max_restarts = max_restarts
        self.restart_window = restart_window
        self.backoff = BackoffPolicy(backoff)
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        # Internal state
        self._restart_timestamps: list[float] = []
        self._restart_counts: dict[str, int] = {}
        self._child_tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._parent: Supervisor | None = None

        # Injected by Runtime
        self._bus: MessageBus | None = None
        self._registry: Registry | None = None
        self._tracer: Tracer | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all children and begin monitoring them."""
        self._running = True

        # Set parent references for child supervisors
        for child in self.children:
            if isinstance(child, Supervisor):
                child._parent = self

        # Start children bottom-up (supervisors first start their children)
        for child in self.children:
            if isinstance(child, Supervisor):
                await child.start()
            else:
                await self._start_child(child)

    async def stop(self) -> None:
        """Stop all children gracefully."""
        self._running = False
        for child in reversed(self.children):
            if isinstance(child, Supervisor):
                await child.stop()
            else:
                await child._stop()

    async def _start_child(self, agent: AgentProcess) -> None:
        """Start a single child agent and monitor its task."""
        await agent._start()
        if agent._task is not None:
            self._child_tasks[agent.name] = agent._task
            agent._task.add_done_callback(
                lambda t, name=agent.name: self._on_child_done(name, t)
            )

    def _on_child_done(self, name: str, task: asyncio.Task[None]) -> None:
        """Callback when a child task completes (crash or normal exit)."""
        if not self._running:
            return
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            asyncio.create_task(self._handle_crash(name, exc))

    # ------------------------------------------------------------------
    # Crash handling
    # ------------------------------------------------------------------

    async def _handle_crash(self, name: str, exc: Exception) -> None:
        """Apply the restart strategy after a child crash."""
        now = time.time()

        # Update crash log for the child
        self._restart_counts.setdefault(name, 0)
        self._restart_counts[name] += 1

        # Track timestamps for rate limiting
        self._restart_timestamps.append(now)
        # Prune old timestamps outside the window
        cutoff = now - self.restart_window
        self._restart_timestamps = [t for t in self._restart_timestamps if t > cutoff]

        # Check if we've exceeded max restarts
        if len(self._restart_timestamps) > self.max_restarts:
            await self._escalate(name, exc)
            return

        # Log the restart
        restart_num = self._restart_counts[name]
        if self._tracer:
            span = self._tracer.start_span(
                f"supervisor.restart",
                attributes={
                    "agency.supervisor": self.name,
                    "agency.child": name,
                    "agency.restart_count": restart_num,
                    "agency.strategy": self.strategy.value,
                    "agency.error": str(exc),
                },
            )
            span.end()
        else:
            print(
                f"[{self.name}] Restart {restart_num}/{self.max_restarts}: "
                f"{name} crashed ({exc})"
            )

        # Apply backoff delay
        delay = self._compute_backoff(restart_num)
        if delay > 0:
            await asyncio.sleep(delay)

        # Apply restart strategy
        if self.strategy == RestartStrategy.ONE_FOR_ONE:
            await self._restart_child(name)
        elif self.strategy == RestartStrategy.ONE_FOR_ALL:
            await self._restart_all_children()
        elif self.strategy == RestartStrategy.REST_FOR_ONE:
            await self._restart_rest_for_one(name)

    async def _restart_child(self, name: str) -> None:
        """Restart a single child by name."""
        agent = self._find_child(name)
        if agent is None or isinstance(agent, Supervisor):
            return

        # Re-initialize the agent
        agent._status = ProcessStatus.INITIALIZING
        agent.id = agent.id  # keep same ID for now
        if self._registry is not None:
            self._registry.deregister(name)
            self._registry.register(name, agent)
        await self._start_child(agent)

    async def _restart_all_children(self) -> None:
        """Stop and restart all children (ONE_FOR_ALL)."""
        # Stop all non-crashed children first
        for child in self.children:
            if isinstance(child, Supervisor):
                await child.stop()
            elif child._status == ProcessStatus.RUNNING:
                await child._stop()

        # Restart all
        for child in self.children:
            if isinstance(child, Supervisor):
                await child.start()
            else:
                child._status = ProcessStatus.INITIALIZING
                if self._registry is not None:
                    self._registry.deregister(child.name)
                    self._registry.register(child.name, child)
                await self._start_child(child)

    async def _restart_rest_for_one(self, name: str) -> None:
        """Restart the crashed child and all children after it (REST_FOR_ONE)."""
        found = False
        to_restart: list[AgentProcess | Supervisor] = []

        for child in self.children:
            child_name = child.name
            if child_name == name:
                found = True
            if found:
                to_restart.append(child)

        # Stop downstream children (reverse order)
        for child in reversed(to_restart):
            if isinstance(child, Supervisor):
                await child.stop()
            elif child._status == ProcessStatus.RUNNING:
                await child._stop()

        # Restart in order
        for child in to_restart:
            if isinstance(child, Supervisor):
                await child.start()
            else:
                child._status = ProcessStatus.INITIALIZING
                if self._registry is not None:
                    self._registry.deregister(child.name)
                    self._registry.register(child.name, child)
                await self._start_child(child)

    async def _escalate(self, name: str, exc: Exception) -> None:
        """Max restarts exceeded — escalate to parent or stop permanently."""
        print(
            f"[{self.name}] Max restarts ({self.max_restarts}) exceeded for {name}. "
            f"Escalating."
        )
        if self._parent is not None:
            # Escalate: parent treats this supervisor as crashed
            await self._parent._handle_crash(self.name, exc)
        else:
            # Top-level: stop the crashed child permanently
            agent = self._find_child(name)
            if agent is not None and not isinstance(agent, Supervisor):
                agent._status = ProcessStatus.STOPPED

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    def _compute_backoff(self, restart_count: int) -> float:
        """Compute the delay before restarting, based on backoff policy."""
        if self.backoff == BackoffPolicy.CONSTANT:
            delay = self.backoff_base
        elif self.backoff == BackoffPolicy.LINEAR:
            delay = self.backoff_base * restart_count
        elif self.backoff == BackoffPolicy.EXPONENTIAL:
            delay = self.backoff_base * (2 ** (restart_count - 1))
            # Add jitter (up to 25%)
            delay += delay * random.random() * 0.25
        else:
            delay = self.backoff_base

        return min(delay, self.backoff_max)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_child(self, name: str) -> AgentProcess | Supervisor | None:
        """Find a child by name."""
        for child in self.children:
            if child.name == name:
                return child
        return None

    def all_agents(self) -> list[AgentProcess]:
        """Recursively collect all AgentProcess instances in the tree."""
        agents: list[AgentProcess] = []
        for child in self.children:
            if isinstance(child, Supervisor):
                agents.extend(child.all_agents())
            else:
                agents.append(child)
        return agents

    def all_supervisors(self) -> list[Supervisor]:
        """Recursively collect all Supervisor instances (including self)."""
        supervisors: list[Supervisor] = [self]
        for child in self.children:
            if isinstance(child, Supervisor):
                supervisors.extend(child.all_supervisors())
        return supervisors
