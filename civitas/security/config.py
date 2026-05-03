"""Security configuration dataclasses parsed from the topology YAML `security:` block."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IdentityConfig:
    mode: str = "auto"  # "auto" | "provisioned"
    key_dir: Path = field(default_factory=lambda: Path("./civitas-keys"))


@dataclass
class SigningConfig:
    enabled: bool = False
    algorithm: str = "ed25519"
    require_verification: bool = True
    allow_unsigned: bool = False


@dataclass
class SecurityConfig:
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    signing: SigningConfig = field(default_factory=SigningConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityConfig:
        identity_data = data.get("identity", {})
        signing_data = data.get("signing", {})

        key_dir_raw = identity_data.get("key_dir", "./civitas-keys")
        identity = IdentityConfig(
            mode=identity_data.get("mode", "auto"),
            key_dir=Path(key_dir_raw),
        )
        signing = SigningConfig(
            enabled=signing_data.get("enabled", False),
            algorithm=signing_data.get("algorithm", "ed25519"),
            require_verification=signing_data.get("require_verification", True),
            allow_unsigned=signing_data.get("allow_unsigned", False),
        )
        return cls(identity=identity, signing=signing)
