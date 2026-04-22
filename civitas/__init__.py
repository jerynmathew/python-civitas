"""Civitas — The Production Runtime for Python Agents.

Public API:
    AgentProcess  — subclass to create agent processes
    GenServer     — OTP-style generic server for stateful service processes
    Supervisor    — monitors children, applies restart strategies
    Runtime       — wires components, manages lifecycle
    Worker        — hosts agents in a remote worker process
    ComponentSet  — assembled infrastructure wiring (transport, bus, registry, tracer)
    Message       — standard message envelope
    CivitasError   — base exception
    ErrorAction   — enum: RETRY, SKIP, ESCALATE, STOP
"""

from __future__ import annotations

from civitas.components import ComponentSet
from civitas.errors import CivitasError, ErrorAction
from civitas.evalloop import CorrectionSignal, EvalAgent, EvalEvent, EvalExporter
from civitas.gateway.core import GatewayConfig, HTTPGateway
from civitas.genserver import GenServer
from civitas.messages import Message
from civitas.process import AgentProcess
from civitas.runtime import Runtime
from civitas.supervisor import Supervisor
from civitas.worker import Worker

__all__ = [
    "AgentProcess",
    "GenServer",
    "EvalAgent",
    "EvalEvent",
    "CorrectionSignal",
    "EvalExporter",
    "GatewayConfig",
    "HTTPGateway",
    "Supervisor",
    "Runtime",
    "Worker",
    "ComponentSet",
    "Message",
    "CivitasError",
    "ErrorAction",
]
