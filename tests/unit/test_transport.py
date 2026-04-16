"""Unit tests for InProcessTransport — lifecycle, routing, request-reply edge cases."""

from __future__ import annotations

import pytest

from civitas.messages import Message
from civitas.serializer import MsgpackSerializer
from civitas.transport.inprocess import InProcessTransport


def _transport() -> InProcessTransport:
    return InProcessTransport(MsgpackSerializer())


# ---------------------------------------------------------------------------
# start() — idempotent guard
# ---------------------------------------------------------------------------


async def test_start_idempotent() -> None:
    """Calling start() twice is safe — second call is a no-op (line 29)."""
    t = _transport()
    await t.start()
    await t.start()  # must not raise
    assert t._started is True


# ---------------------------------------------------------------------------
# publish() — no handler registered
# ---------------------------------------------------------------------------


async def test_publish_to_unregistered_address_is_noop() -> None:
    """publish() to an address with no handler silently does nothing (branch 50->exit)."""
    t = _transport()
    await t.start()
    # No handler subscribed — should not raise
    await t.publish("unknown.agent", b"data")


# ---------------------------------------------------------------------------
# request() — no handler raises RuntimeError
# ---------------------------------------------------------------------------


async def test_request_no_handler_raises() -> None:
    """request() raises RuntimeError when no handler is registered for the address (line 72)."""
    t = _transport()
    serializer = MsgpackSerializer()
    await t.start()
    data = serializer.serialize(Message(type="ping", sender="a", recipient="nobody"))
    with pytest.raises(RuntimeError, match="No handler registered"):
        await t.request("nobody", data, timeout=1.0)
