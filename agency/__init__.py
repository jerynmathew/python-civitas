"""Agency — The Production Runtime for Python Agents.

Public API:
    AgentProcess  — subclass to create agent processes
    Supervisor    — monitors children, applies restart strategies
    Runtime       — wires components, manages lifecycle
    Worker        — hosts agents in a remote worker process
    ComponentSet  — assembled infrastructure wiring (transport, bus, registry, tracer)
    Message       — standard message envelope
    AgencyError   — base exception
    ErrorAction   — enum: RETRY, SKIP, ESCALATE, STOP
"""

from __future__ import annotations

from agency.components import ComponentSet
from agency.errors import AgencyError, ErrorAction
from agency.messages import Message
from agency.process import AgentProcess
from agency.runtime import Runtime
from agency.supervisor import Supervisor
from agency.worker import Worker

__all__ = [
    "AgentProcess",
    "Supervisor",
    "Runtime",
    "Worker",
    "ComponentSet",
    "Message",
    "AgencyError",
    "ErrorAction",
]
