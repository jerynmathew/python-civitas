"""Serializer protocol and implementations (msgpack, JSON)."""

from __future__ import annotations

import json
from typing import Any, Protocol

import msgpack  # type: ignore[import-untyped]

from agency.messages import Message


class Serializer(Protocol):
    """Protocol for message serialization/deserialization."""

    def serialize(self, message: Message) -> bytes: ...
    def deserialize(self, data: bytes) -> Message: ...


class MsgpackSerializer:
    """Default serializer using MessagePack — fast and compact."""

    def serialize(self, message: Message) -> bytes:
        return msgpack.packb(message.to_dict(), use_bin_type=True)  # type: ignore[no-any-return]

    def deserialize(self, data: bytes) -> Message:
        raw: dict[str, Any] = msgpack.unpackb(data, raw=False)
        return Message.from_dict(raw)


class JsonSerializer:
    """Debug/dev serializer using JSON — human-readable but slower."""

    def serialize(self, message: Message) -> bytes:
        return json.dumps(message.to_dict()).encode("utf-8")

    def deserialize(self, data: bytes) -> Message:
        raw: dict[str, Any] = json.loads(data.decode("utf-8"))
        return Message.from_dict(raw)
