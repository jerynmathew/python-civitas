"""Unit tests for civitas.plugins.loader — entrypoint resolution, constructor errors."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from civitas.plugins.loader import PluginError, resolve_plugin_class

# ---------------------------------------------------------------------------
# Entrypoint resolution (lines 71-76 in loader.py)
# ---------------------------------------------------------------------------


def test_resolve_via_entrypoint() -> None:
    """When an installed entrypoint matches the requested name, it is loaded."""

    class _FakeProvider:
        pass

    fake_ep = MagicMock()
    fake_ep.name = "myprovider"
    fake_ep.load.return_value = _FakeProvider

    with patch("civitas.plugins.loader.entry_points", return_value=[fake_ep]):
        cls = resolve_plugin_class("model", "myprovider")

    assert cls is _FakeProvider
    fake_ep.load.assert_called_once()


def test_resolve_entrypoint_load_error_raises_plugin_error() -> None:
    """If the entrypoint's load() raises, a PluginError is produced."""

    fake_ep = MagicMock()
    fake_ep.name = "broken"
    fake_ep.load.side_effect = ImportError("missing dep")

    with patch("civitas.plugins.loader.entry_points", return_value=[fake_ep]):
        with pytest.raises(PluginError, match="missing dep"):
            resolve_plugin_class("model", "broken")


def test_resolve_entrypoint_name_mismatch_falls_through() -> None:
    """An entrypoint whose name doesn't match is skipped; resolution continues."""
    # Provide an entrypoint that does NOT match, then let the built-in mapping handle it
    wrong_ep = MagicMock()
    wrong_ep.name = "other_provider"  # != "in_memory"

    with patch("civitas.plugins.loader.entry_points", return_value=[wrong_ep]):
        cls = resolve_plugin_class("state", "in_memory")

    from civitas.plugins.state import InMemoryStateStore

    assert cls is InMemoryStateStore
    wrong_ep.load.assert_not_called()


def test_import_dotted_no_module_part_raises() -> None:
    """A dotted path with an empty module part (e.g. '.MyClass') raises PluginError."""
    # "." in ".MyClass" is True, so resolve_plugin_class will call _import_dotted,
    # which then finds module_path="" and raises PluginError at line 177.
    with pytest.raises(PluginError, match="Invalid dotted path"):
        resolve_plugin_class("model", ".MyClass")


# ---------------------------------------------------------------------------
# Constructor TypeError → PluginError (line 108-111 in loader.py)
# ---------------------------------------------------------------------------


def test_load_plugin_constructor_type_error() -> None:
    """load_plugin wraps a constructor TypeError in a PluginError."""
    from civitas.plugins.loader import load_plugin

    # in_memory takes no config kwargs — passing an unexpected kwarg triggers TypeError
    with pytest.raises(PluginError, match="Constructor error"):
        load_plugin("state", "in_memory", {"totally_invalid_kwarg": True})
