"""Supervisor — monitors child processes and applies restart strategies on failure."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from enum import Enum
from typing import TYPE_CHECKING

from agency.messages import Message, _new_span_id, _uuid7
from agency.process import AgentProcess, ProcessStatus

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agency.bus import MessageBus
    from agency.observability.tracer import Tracer
    from agency.registry import Registry


class HeartbeatTimeout(Exception):
    """Raised when a remote agent fails to respond to heartbeat pings."""

    def __init__(self, agent_name: str, missed: int) -> None:
        self.agent_name = agent_name
        self.missed = missed
        super().__init__(f"Agent '{agent_name}' missed {missed} heartbeats")


class RestartStrategy(Enum):
    """Strategy used by a Supervisor when a child process crashes."""

    ONE_FOR_ONE = "ONE_FOR_ONE"
    ONE_FOR_ALL = "ONE_FOR_ALL"
    REST_FOR_ONE = "REST_FOR_ONE"


class BackoffPolicy(Enum):
    """Delay strategy applied between successive restart attempts."""

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

        # Heartbeat monitoring for remote agents
        self._remote_children: set[str] = set()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_interval: float = 5.0
        self._heartbeat_timeout: float = 2.0
        self._missed_heartbeats_threshold: int = 3
        self._missed_heartbeats: dict[str, int] = {}

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

        # Start heartbeat monitoring for remote children
        await self._start_heartbeat_monitor()

    async def stop(self) -> None:
        """Stop all children gracefully."""
        self._running = False
        await self._stop_heartbeat_monitor()
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
    # Remote child / heartbeat support
    # ------------------------------------------------------------------

    def add_remote_child(
        self,
        name: str,
        heartbeat_interval: float = 5.0,
        heartbeat_timeout: float = 2.0,
        missed_heartbeats_threshold: int = 3,
    ) -> None:
        """Register a remote child for heartbeat-based monitoring.

        Remote children are agents running in a Worker process. They are
        monitored via periodic heartbeat pings instead of task callbacks.
        """
        self._remote_children.add(name)
        self._missed_heartbeats[name] = 0
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._missed_heartbeats_threshold = missed_heartbeats_threshold

    async def _start_heartbeat_monitor(self) -> None:
        """Start the heartbeat monitoring loop for remote children."""
        if not self._remote_children:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Periodically ping remote children and detect crashes."""
        while self._running:
            for name in list(self._remote_children):
                if not self._running:
                    break
                try:
                    heartbeat = Message(
                        type="_agency.heartbeat",
                        sender=self.name,
                        recipient=name,
                        correlation_id=_uuid7(),
                        span_id=_new_span_id(),
                    )
                    if self._bus is None:
                        break
                    await asyncio.wait_for(
                        self._bus.request(heartbeat, timeout=self._heartbeat_timeout),
                        timeout=self._heartbeat_timeout + 1.0,
                    )
                    # Got ack — reset missed counter
                    self._missed_heartbeats[name] = 0
                except TimeoutError:
                    self._missed_heartbeats[name] = (
                        self._missed_heartbeats.get(name, 0) + 1
                    )
                    missed = self._missed_heartbeats[name]
                    if missed >= self._missed_heartbeats_threshold:
                        await self._handle_crash(
                            name, HeartbeatTimeout(name, missed)
                        )
                        self._missed_heartbeats[name] = 0

            await asyncio.sleep(self._heartbeat_interval)

    async def _stop_heartbeat_monitor(self) -> None:
        """Stop the heartbeat monitor task."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

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
                "supervisor.restart",
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
            logger.info(
                "[%s] Restart %d/%d: %s crashed (%s)",
                self.name, restart_num, self.max_restarts, name, exc,
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
        """Restart a single child by name (local or remote)."""
        # Remote child — send restart command via message bus
        if name in self._remote_children:
            await self._restart_remote_child(name)
            return

        agent = self._find_child(name)
        if agent is None or isinstance(agent, Supervisor):
            return

        # Re-initialize the agent
        agent._status = ProcessStatus.INITIALIZING
        agent.id = agent.id  # keep same ID for now
        if self._registry is not None:
            self._registry.deregister(name)
            self._registry.register(name)
        await self._start_child(agent)

    async def _restart_remote_child(self, name: str) -> None:
        """Send a restart command to a remote worker via ZMQ."""
        if self._bus is None:
            return
        restart_msg = Message(
            type="_agency.restart",
            sender=self.name,
            recipient="_agency.worker.restart",
            payload={"agent_name": name},
        )
        await self._bus.route(restart_msg)

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
                    self._registry.register(child.name)
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
                    self._registry.register(child.name)
                await self._start_child(child)

    async def _escalate(self, name: str, exc: Exception) -> None:
        """Max restarts exceeded — escalate to parent or stop permanently."""
        logger.warning(
            "[%s] Max restarts (%d) exceeded for %s. Escalating.",
            self.name, self.max_restarts, name,
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
