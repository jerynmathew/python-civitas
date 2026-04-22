"""Gateway request/response types and middleware protocol."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from civitas.gateway.core import HTTPGateway


@dataclass
class GatewayRequest:
    """Thin HTTP request abstraction passed through the middleware chain."""

    method: str
    path: str
    path_params: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    client_ip: str = ""
    gateway: HTTPGateway | None = None


@dataclass
class GatewayResponse:
    """Thin HTTP response produced by middleware or terminal dispatch handler."""

    status: int = 200
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


# Middleware callable: (request, next) → response
NextMiddleware = Callable[[GatewayRequest], Awaitable[GatewayResponse]]
MiddlewareCallable = Callable[[GatewayRequest, NextMiddleware], Awaitable[GatewayResponse]]
