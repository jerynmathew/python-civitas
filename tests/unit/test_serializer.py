"""Tests for Serializer protocol and msgpack/json implementations."""

from agency.messages import Message
from agency.serializer import JsonSerializer, MsgpackSerializer


def test_msgpack_roundtrip():
    """MsgpackSerializer preserves all fields through serialize/deserialize."""
    ser = MsgpackSerializer()
    original = Message(
        type="research_query",
        sender="agent_a",
        recipient="agent_b",
        payload={"query": "test", "count": 42, "nested": {"a": [1, 2, 3]}},
        trace_id="trace123",
        span_id="span456",
        parent_span_id="parent789",
        attempt=1,
        priority=1,
        ttl=60.0,
        correlation_id="corr001",
        reply_to="agent_a",
    )
    data = ser.serialize(original)
    assert isinstance(data, bytes)

    restored = ser.deserialize(data)
    assert restored.type == original.type
    assert restored.sender == original.sender
    assert restored.recipient == original.recipient
    assert restored.payload == original.payload
    assert restored.trace_id == original.trace_id
    assert restored.span_id == original.span_id
    assert restored.parent_span_id == original.parent_span_id
    assert restored.attempt == original.attempt
    assert restored.priority == original.priority
    assert restored.ttl == original.ttl
    assert restored.correlation_id == original.correlation_id
    assert restored.reply_to == original.reply_to
    assert restored.id == original.id


def test_json_roundtrip():
    """JsonSerializer preserves all fields through serialize/deserialize."""
    ser = JsonSerializer()
    original = Message(
        type="test",
        sender="a",
        recipient="b",
        payload={"key": "value"},
    )
    data = ser.serialize(original)
    assert isinstance(data, bytes)
    # JSON should be human-readable
    text = data.decode("utf-8")
    assert '"type"' in text
    assert '"test"' in text

    restored = ser.deserialize(data)
    assert restored.type == original.type
    assert restored.payload == original.payload


def test_msgpack_compact():
    """Msgpack output is more compact than JSON for the same message."""
    msg = Message(
        type="test",
        sender="agent_a",
        recipient="agent_b",
        payload={"data": "x" * 100},
    )
    msgpack_data = MsgpackSerializer().serialize(msg)
    json_data = JsonSerializer().serialize(msg)
    assert len(msgpack_data) < len(json_data)


def test_empty_payload_roundtrip():
    """Empty payload roundtrips correctly."""
    for ser in [MsgpackSerializer(), JsonSerializer()]:
        msg = Message(type="ping", payload={})
        restored = ser.deserialize(ser.serialize(msg))
        assert restored.payload == {}


def test_none_optional_fields_roundtrip():
    """None values for optional fields roundtrip correctly."""
    for ser in [MsgpackSerializer(), JsonSerializer()]:
        msg = Message(
            correlation_id=None,
            reply_to=None,
            parent_span_id=None,
            ttl=None,
        )
        restored = ser.deserialize(ser.serialize(msg))
        assert restored.correlation_id is None
        assert restored.reply_to is None
        assert restored.parent_span_id is None
        assert restored.ttl is None
