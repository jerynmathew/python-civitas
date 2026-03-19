"""Tests for Message construction, serialization round-trip, and UUID7 generation."""

from agency.messages import SYSTEM_MESSAGE_TYPES, Message, _uuid7


def test_uuid7_format():
    """UUID7 is a valid 36-char hyphenated hex string."""
    uid = _uuid7()
    assert len(uid) == 36
    parts = uid.split("-")
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]
    # Version nibble (13th hex char) should be '7'
    assert uid[14] == "7"


def test_uuid7_time_sortable():
    """UUID7s generated at different times should sort in order."""
    import time

    a = _uuid7()
    time.sleep(0.002)  # ensure different millisecond
    b = _uuid7()
    assert a < b


def test_message_defaults():
    """Message with no args gets sensible defaults."""
    msg = Message()
    assert msg.type == "message"
    assert msg.sender == ""
    assert msg.recipient == ""
    assert msg.payload == {}
    assert msg.attempt == 0
    assert msg.priority == 0
    assert msg.ttl is None
    assert msg.correlation_id is None
    assert msg.reply_to is None
    assert len(msg.id) == 36  # UUID7


def test_message_construction():
    """Message can be constructed with explicit values."""
    msg = Message(
        type="research_query",
        sender="agent_a",
        recipient="agent_b",
        payload={"query": "test"},
        priority=1,
    )
    assert msg.type == "research_query"
    assert msg.sender == "agent_a"
    assert msg.recipient == "agent_b"
    assert msg.payload == {"query": "test"}
    assert msg.priority == 1


def test_message_to_dict():
    """to_dict() produces a plain dict with all fields."""
    msg = Message(type="test", sender="a", recipient="b", payload={"x": 1})
    d = msg.to_dict()
    assert d["type"] == "test"
    assert d["sender"] == "a"
    assert d["recipient"] == "b"
    assert d["payload"] == {"x": 1}
    assert "id" in d
    assert "timestamp" in d


def test_message_from_dict_roundtrip():
    """from_dict(to_dict()) preserves all fields."""
    original = Message(
        type="query",
        sender="a",
        recipient="b",
        payload={"key": "value"},
        trace_id="abc123",
        span_id="def456",
        attempt=2,
        priority=1,
        ttl=30.0,
    )
    restored = Message.from_dict(original.to_dict())
    assert restored.type == original.type
    assert restored.sender == original.sender
    assert restored.recipient == original.recipient
    assert restored.payload == original.payload
    assert restored.trace_id == original.trace_id
    assert restored.span_id == original.span_id
    assert restored.attempt == original.attempt
    assert restored.priority == original.priority
    assert restored.ttl == original.ttl
    assert restored.id == original.id


def test_from_dict_ignores_unknown_keys():
    """from_dict() silently ignores keys not in the dataclass."""
    d = Message().to_dict()
    d["unknown_field"] = "should be ignored"
    msg = Message.from_dict(d)
    assert not hasattr(msg, "unknown_field")


def test_system_message_types():
    """SYSTEM_MESSAGE_TYPES contains the expected reserved types."""
    assert "_agency.heartbeat" in SYSTEM_MESSAGE_TYPES
    assert "_agency.shutdown" in SYSTEM_MESSAGE_TYPES
    assert "_agency.restart" in SYSTEM_MESSAGE_TYPES
    assert "_agency.register" in SYSTEM_MESSAGE_TYPES
    assert "_agency.deregister" in SYSTEM_MESSAGE_TYPES
    assert "_agency.heartbeat_ack" in SYSTEM_MESSAGE_TYPES
    # Application types should not be in it
    assert "research_query" not in SYSTEM_MESSAGE_TYPES
