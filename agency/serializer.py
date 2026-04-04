"""Serializer protocol and implementations (msgpack, JSON)."""

from __future__ import annotations

import json
from typing import Any, Protocol

import msgpack  # type: ignore[import-untyped]

from agency.errors import DeserializationError
from agency.messages import Message


class Serializer(Protocol):
    """Protocol for message serialization/deserialization."""

    def serialize(self, message: Message) -> bytes:
        """Encode a Message to bytes for transport."""
        ...

    def deserialize(self, data: bytes) -> Message:
        """Decode bytes back into a Message.

        Raises:
            DeserializationError: if the bytes are corrupt, malformed, or in the
                wrong format. Callers never need to catch library-specific exceptions.
        """
        ...


class MsgpackSerializer:
    """Default serializer using MessagePack — fast and compact."""

    def serialize(self, message: Message) -> bytes:
        """Encode a Message to MessagePack bytes."""
        return msgpack.packb(message.to_dict(), use_bin_type=True)  # type: ignore[no-any-return]

    def deserialize(self, data: bytes) -> Message:
        """Decode MessagePack bytes into a Message.

        Raises:
            DeserializationError: on corrupt or malformed bytes.
        """
        try:
            raw: dict[str, Any] = msgpack.unpackb(data, raw=False)
            return Message.from_dict(raw)
        except Exception as exc:
            raise DeserializationError(
                f"Failed to deserialize msgpack data: {exc}"
            ) from exc


class JsonSerializer:
    """Debug/dev serializer using JSON — human-readable but slower."""

    def serialize(self, message: Message) -> bytes:
        """Encode a Message to JSON bytes."""
        return json.dumps(message.to_dict()).encode("utf-8")

    def deserialize(self, data: bytes) -> Message:
        """Decode JSON bytes into a Message.

        Raises:
            DeserializationError: on corrupt, malformed, or non-UTF-8 bytes.
        """
        try:
            raw: dict[str, Any] = json.loads(data.decode("utf-8"))
            return Message.from_dict(raw)
        except Exception as exc:
            raise DeserializationError(
                f"Failed to deserialize JSON data: {exc}"
            ) from exc
