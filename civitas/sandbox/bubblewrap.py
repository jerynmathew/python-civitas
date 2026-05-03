"""Bubblewrap sandbox wrapper for MCP stdio subprocess execution."""

from __future__ import annotations

import shutil

from civitas.errors import ConfigurationError
from civitas.sandbox.config import SandboxConfig

# Common paths that most MCP servers need to run.
# Mounted read-only to give the subprocess a functional root filesystem
# without exposing host-writable state.
_BASE_RO_MOUNTS = [
    "/usr",
    "/lib",
    "/lib64",
    "/bin",
    "/sbin",
    "/etc/ssl/certs",
    "/etc/resolv.conf",
]


class BubblewrapSandbox:
    """Wraps an MCP subprocess command with bubblewrap (bwrap).

    Applies read-only root, optional network isolation, a tmpfs at /tmp,
    and the operator-declared filesystem mounts from ``SandboxConfig``.

    Usage::

        sandbox = BubblewrapSandbox(config)
        sandbox.check_or_raise()           # fails fast if bwrap is absent
        cmd, args = sandbox.wrap("python", ["-m", "my_mcp_server"])
    """

    def __init__(self, config: SandboxConfig) -> None:
        self._config = config

    @staticmethod
    def available() -> bool:
        """Return True if ``bwrap`` is on PATH."""
        return shutil.which("bwrap") is not None

    def check_or_raise(self) -> None:
        """Raise ``ConfigurationError`` if bwrap is not available.

        Called before starting any sandboxed subprocess so the runtime fails
        loudly rather than silently falling back to an unsandboxed process.
        """
        if not self.available():
            raise ConfigurationError(
                "sandbox.enabled: true but 'bwrap' (bubblewrap) is not available on PATH. "
                "Install it and retry, or set sandbox.enabled: false for development topologies.\n"
                "\n"
                "Install instructions:\n"
                "  Debian/Ubuntu:  apt install bubblewrap\n"
                "  Fedora/RHEL:    dnf install bubblewrap\n"
                "  Arch Linux:     pacman -S bubblewrap\n"
                "  macOS:          not supported — use sandbox.enabled: false\n"
                "  Windows:        not supported — use sandbox.enabled: false"
            )

    def wrap(self, command: str, args: list[str]) -> tuple[str, list[str]]:
        """Return ``("bwrap", bwrap_args)`` that runs ``command args`` inside the sandbox.

        The caller substitutes the returned command/args for the original ones
        when constructing the subprocess.

        Args:
            command: The MCP server executable path.
            args:    The MCP server arguments.

        Returns:
            A 2-tuple ``(new_command, new_args)`` where ``new_command == "bwrap"``.
        """
        bwrap_args: list[str] = []

        # Base read-only filesystem — give the subprocess a functional root
        for path in _BASE_RO_MOUNTS:
            bwrap_args.extend(["--ro-bind-try", path, path])

        # Scratch /tmp — MCP servers often write temp files
        bwrap_args.extend(["--tmpfs", "/tmp"])

        # proc filesystem — required by many runtimes (Python, Node, etc.)
        bwrap_args.extend(["--proc", "/proc"])

        # dev filesystem — /dev/null, /dev/urandom, etc.
        bwrap_args.extend(["--dev", "/dev"])

        # Network isolation
        if self._config.network == "deny":
            bwrap_args.append("--unshare-net")

        # Operator-declared filesystem mounts (applied after base mounts)
        for mount in self._config.filesystem:
            if mount.mode == "rw":
                bwrap_args.extend(["--bind", mount.path, mount.path])
            else:
                bwrap_args.extend(["--ro-bind", mount.path, mount.path])

        # Unshare PID and IPC namespaces for additional isolation
        bwrap_args.extend(["--unshare-pid", "--unshare-ipc"])

        # Terminate the bwrap flags and start the actual command
        bwrap_args.extend(["--", command, *args])

        return "bwrap", bwrap_args
