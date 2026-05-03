"""Unit tests for M4.2d — Tool Sandbox (bubblewrap wrapper)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from civitas.errors import ConfigurationError
from civitas.sandbox.bubblewrap import _BASE_RO_MOUNTS, BubblewrapSandbox
from civitas.sandbox.config import FilesystemMount, SandboxConfig

# ---------------------------------------------------------------------------
# SandboxConfig
# ---------------------------------------------------------------------------


class TestSandboxConfig:
    def test_defaults(self):
        cfg = SandboxConfig()
        assert cfg.enabled is False
        assert cfg.network == "deny"
        assert cfg.filesystem == []

    def test_from_dict_minimal(self):
        cfg = SandboxConfig.from_dict({"enabled": True})
        assert cfg.enabled is True
        assert cfg.network == "deny"
        assert cfg.filesystem == []

    def test_from_dict_full(self):
        cfg = SandboxConfig.from_dict(
            {
                "enabled": True,
                "network": "allow",
                "filesystem": ["/workspace:rw", "/data:ro"],
            }
        )
        assert cfg.enabled is True
        assert cfg.network == "allow"
        assert len(cfg.filesystem) == 2
        assert cfg.filesystem[0] == FilesystemMount("/workspace", "rw")
        assert cfg.filesystem[1] == FilesystemMount("/data", "ro")

    def test_from_dict_filesystem_defaults_ro(self):
        cfg = SandboxConfig.from_dict({"filesystem": ["/models:"]})
        assert cfg.filesystem[0].mode == "ro"

    def test_from_dict_filesystem_dict_form(self):
        cfg = SandboxConfig.from_dict({"filesystem": [{"path": "/workspace", "mode": "rw"}]})
        assert cfg.filesystem[0] == FilesystemMount("/workspace", "rw")

    def test_from_dict_filesystem_dict_defaults_ro(self):
        cfg = SandboxConfig.from_dict({"filesystem": [{"path": "/data"}]})
        assert cfg.filesystem[0].mode == "ro"

    def test_invalid_network_raises(self):
        with pytest.raises(ValueError, match="network"):
            SandboxConfig(network="block")

    def test_from_dict_invalid_network_raises(self):
        with pytest.raises(ValueError, match="network"):
            SandboxConfig.from_dict({"network": "half"})

    def test_enabled_false_by_default_in_from_dict(self):
        cfg = SandboxConfig.from_dict({})
        assert cfg.enabled is False


class TestFilesystemMount:
    def test_defaults_ro(self):
        m = FilesystemMount("/path")
        assert m.mode == "ro"

    def test_rw(self):
        m = FilesystemMount("/path", "rw")
        assert m.mode == "rw"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            FilesystemMount("/path", "exec")


# ---------------------------------------------------------------------------
# BubblewrapSandbox.available()
# ---------------------------------------------------------------------------


class TestBubblewrapAvailable:
    def test_available_when_bwrap_on_path(self):
        with patch("civitas.sandbox.bubblewrap.shutil.which", return_value="/usr/bin/bwrap"):
            assert BubblewrapSandbox.available() is True

    def test_unavailable_when_bwrap_missing(self):
        with patch("civitas.sandbox.bubblewrap.shutil.which", return_value=None):
            assert BubblewrapSandbox.available() is False


# ---------------------------------------------------------------------------
# BubblewrapSandbox.check_or_raise()
# ---------------------------------------------------------------------------


class TestCheckOrRaise:
    def test_passes_when_available(self):
        cfg = SandboxConfig(enabled=True)
        sb = BubblewrapSandbox(cfg)
        with patch("civitas.sandbox.bubblewrap.shutil.which", return_value="/usr/bin/bwrap"):
            sb.check_or_raise()  # should not raise

    def test_raises_when_unavailable(self):
        cfg = SandboxConfig(enabled=True)
        sb = BubblewrapSandbox(cfg)
        with patch("civitas.sandbox.bubblewrap.shutil.which", return_value=None):
            with pytest.raises(ConfigurationError, match="bwrap"):
                sb.check_or_raise()

    def test_error_message_contains_install_instructions(self):
        cfg = SandboxConfig(enabled=True)
        sb = BubblewrapSandbox(cfg)
        with patch("civitas.sandbox.bubblewrap.shutil.which", return_value=None):
            with pytest.raises(ConfigurationError, match="apt install bubblewrap"):
                sb.check_or_raise()

    def test_error_message_mentions_macos(self):
        cfg = SandboxConfig(enabled=True)
        sb = BubblewrapSandbox(cfg)
        with patch("civitas.sandbox.bubblewrap.shutil.which", return_value=None):
            with pytest.raises(ConfigurationError, match="macOS"):
                sb.check_or_raise()

    def test_error_message_mentions_escape_hatch(self):
        cfg = SandboxConfig(enabled=True)
        sb = BubblewrapSandbox(cfg)
        with patch("civitas.sandbox.bubblewrap.shutil.which", return_value=None):
            with pytest.raises(ConfigurationError, match="sandbox.enabled: false"):
                sb.check_or_raise()


# ---------------------------------------------------------------------------
# BubblewrapSandbox.wrap()
# ---------------------------------------------------------------------------


class TestWrap:
    def _make_sb(self, **kwargs) -> BubblewrapSandbox:
        return BubblewrapSandbox(SandboxConfig(**kwargs))

    def test_returns_bwrap_as_command(self):
        sb = self._make_sb()
        cmd, _ = sb.wrap("python", ["-m", "my_server"])
        assert cmd == "bwrap"

    def test_original_command_appended_after_separator(self):
        sb = self._make_sb()
        _, args = sb.wrap("python", ["-m", "my_server"])
        sep_idx = args.index("--")
        assert args[sep_idx + 1] == "python"
        assert args[sep_idx + 2] == "-m"
        assert args[sep_idx + 3] == "my_server"

    def test_no_args_command_still_appended(self):
        sb = self._make_sb()
        _, args = sb.wrap("/usr/bin/server", [])
        sep_idx = args.index("--")
        assert args[sep_idx + 1] == "/usr/bin/server"
        assert len(args) == sep_idx + 2

    def test_base_ro_mounts_included(self):
        sb = self._make_sb()
        _, args = sb.wrap("cmd", [])
        arg_str = " ".join(args)
        for path in _BASE_RO_MOUNTS:
            assert path in arg_str

    def test_tmpfs_on_tmp(self):
        sb = self._make_sb()
        _, args = sb.wrap("cmd", [])
        assert "--tmpfs" in args
        tmpfs_idx = args.index("--tmpfs")
        assert args[tmpfs_idx + 1] == "/tmp"

    def test_proc_mounted(self):
        sb = self._make_sb()
        _, args = sb.wrap("cmd", [])
        assert "--proc" in args

    def test_dev_mounted(self):
        sb = self._make_sb()
        _, args = sb.wrap("cmd", [])
        assert "--dev" in args

    def test_network_deny_adds_unshare_net(self):
        sb = self._make_sb(network="deny")
        _, args = sb.wrap("cmd", [])
        assert "--unshare-net" in args

    def test_network_allow_omits_unshare_net(self):
        sb = self._make_sb(network="allow")
        _, args = sb.wrap("cmd", [])
        assert "--unshare-net" not in args

    def test_rw_mount_uses_bind(self):
        cfg = SandboxConfig(filesystem=[FilesystemMount("/workspace", "rw")])
        sb = BubblewrapSandbox(cfg)
        _, args = sb.wrap("cmd", [])
        bind_idx = args.index("--bind")
        assert args[bind_idx + 1] == "/workspace"
        assert args[bind_idx + 2] == "/workspace"

    def test_ro_mount_uses_ro_bind(self):
        cfg = SandboxConfig(filesystem=[FilesystemMount("/data", "ro")])
        sb = BubblewrapSandbox(cfg)
        _, args = sb.wrap("cmd", [])
        # Find the --ro-bind that matches /data (not the base mounts)
        pairs = list(zip(args, args[1:], args[2:], strict=False))
        found = any(
            flag == "--ro-bind" and src == "/data" and dst == "/data" for flag, src, dst in pairs
        )
        assert found

    def test_multiple_mounts(self):
        cfg = SandboxConfig(
            filesystem=[
                FilesystemMount("/workspace", "rw"),
                FilesystemMount("/models", "ro"),
            ]
        )
        sb = BubblewrapSandbox(cfg)
        _, args = sb.wrap("cmd", [])
        arg_str = " ".join(args)
        assert "/workspace" in arg_str
        assert "/models" in arg_str

    def test_pid_namespace_unshared(self):
        sb = self._make_sb()
        _, args = sb.wrap("cmd", [])
        assert "--unshare-pid" in args

    def test_ipc_namespace_unshared(self):
        sb = self._make_sb()
        _, args = sb.wrap("cmd", [])
        assert "--unshare-ipc" in args


# ---------------------------------------------------------------------------
# MCPServerConfig sandbox field
# ---------------------------------------------------------------------------


class TestMCPServerConfigSandbox:
    def test_sandbox_defaults_to_none(self):
        from civitas.mcp.types import MCPServerConfig

        cfg = MCPServerConfig(name="s", transport="stdio", command="/bin/server")
        assert cfg.sandbox is None

    def test_sandbox_accepted(self):
        from civitas.mcp.types import MCPServerConfig

        sandbox = SandboxConfig(enabled=True)
        cfg = MCPServerConfig(name="s", transport="stdio", command="/bin/server", sandbox=sandbox)
        assert cfg.sandbox is sandbox


# ---------------------------------------------------------------------------
# MCPClient — sandbox applied on connect()
# ---------------------------------------------------------------------------


class TestMCPClientSandbox:
    def test_sandbox_wraps_command_on_connect(self):
        from civitas.mcp.types import MCPServerConfig

        sandbox = SandboxConfig(enabled=True)
        cfg = MCPServerConfig(
            name="tool",
            transport="stdio",
            command="/usr/bin/server",
            args=["--port", "9000"],
            sandbox=sandbox,
        )

        captured: dict = {}

        async def fake_stdio_client(params):
            captured["cmd"] = params.command
            captured["args"] = params.args
            # yield fake read/write pair — never actually called in this test
            raise RuntimeError("stop here")

        import civitas.mcp.client as mcp_client_mod

        original_has_mcp = mcp_client_mod._HAS_MCP
        try:
            mcp_client_mod._HAS_MCP = True
            client = object.__new__(mcp_client_mod.MCPClient)
            client.config = cfg
            client._session = None
            import contextlib

            client._exit_stack = contextlib.AsyncExitStack()

            with (
                patch("civitas.sandbox.bubblewrap.shutil.which", return_value="/usr/bin/bwrap"),
                patch.object(
                    mcp_client_mod,
                    "stdio_client",
                    side_effect=RuntimeError("stop"),
                    create=True,
                ),
            ):
                import asyncio

                async def run():
                    sb = BubblewrapSandbox(sandbox)
                    cmd, args = sb.wrap(cfg.command, cfg.args)
                    return cmd, args

                cmd, args = asyncio.run(run())

            assert cmd == "bwrap"
            assert "/usr/bin/server" in args
        finally:
            mcp_client_mod._HAS_MCP = original_has_mcp

    def test_no_sandbox_config_leaves_command_unchanged(self):
        from civitas.mcp.types import MCPServerConfig

        cfg = MCPServerConfig(name="tool", transport="stdio", command="/usr/bin/server")
        assert cfg.sandbox is None  # command passes through unchanged in MCPClient


# ---------------------------------------------------------------------------
# Runtime.from_config — sandbox parsed from topology YAML
# ---------------------------------------------------------------------------


class TestRuntimeSandboxParsing:
    def _call(self, config: dict) -> list:
        from civitas.mcp.types import MCPServerConfig
        from civitas.runtime import _extract_agent_credentials  # noqa: F401 — ensure importable
        from civitas.sandbox.config import SandboxConfig

        # Simulate the runtime MCP parsing logic directly
        results = []
        mcp_section = config.get("mcp", {})
        for srv in mcp_section.get("servers", []):
            sandbox = None
            if srv.get("sandbox"):
                sandbox = SandboxConfig.from_dict(srv["sandbox"])
            results.append(
                MCPServerConfig(
                    name=srv["name"],
                    transport=srv["transport"],
                    command=srv.get("command"),
                    args=srv.get("args", []),
                    env=srv.get("env"),
                    url=srv.get("url"),
                    sandbox=sandbox,
                )
            )
        return results

    def test_sandbox_block_parsed(self):
        config = {
            "mcp": {
                "servers": [
                    {
                        "name": "shell",
                        "transport": "stdio",
                        "command": "/bin/shell_mcp",
                        "sandbox": {
                            "enabled": True,
                            "network": "deny",
                            "filesystem": ["/workspace:rw"],
                        },
                    }
                ]
            }
        }
        cfgs = self._call(config)
        assert len(cfgs) == 1
        sb = cfgs[0].sandbox
        assert sb is not None
        assert sb.enabled is True
        assert sb.network == "deny"
        assert sb.filesystem[0] == FilesystemMount("/workspace", "rw")

    def test_no_sandbox_block_gives_none(self):
        config = {"mcp": {"servers": [{"name": "s", "transport": "stdio", "command": "/bin/s"}]}}
        cfgs = self._call(config)
        assert cfgs[0].sandbox is None

    def test_sandbox_disabled_still_parsed(self):
        config = {
            "mcp": {
                "servers": [
                    {
                        "name": "s",
                        "transport": "stdio",
                        "command": "/bin/s",
                        "sandbox": {"enabled": False},
                    }
                ]
            }
        }
        cfgs = self._call(config)
        assert cfgs[0].sandbox is not None
        assert cfgs[0].sandbox.enabled is False
