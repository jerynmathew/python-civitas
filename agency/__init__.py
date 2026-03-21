"""Agency — The Production Runtime for Python Agents.

Public API:
    AgentProcess  — subclass to create agent processes
    Supervisor    — monitors children, applies restart strategies
    Runtime       — wires components, manages lifecycle
    Message       — standard message envelope
    AgencyError   — base exception
    ErrorAction   — enum: RETRY, SKIP, ESCALATE, STOP
"""

from __future__ import annotations

from agency.errors import AgencyError, ErrorAction
from agency.messages import Message
from agency.process import AgentProcess
from agency.runtime import Runtime
from agency.supervisor import Supervisor

__all__ = [
    "AgentProcess",
    "Supervisor",
    "Runtime",
    "Message",
    "AgencyError",
    "ErrorAction",
]
