"""Configuration loading for ChronoSync.

Configuration files are TOML (``.toml``) or JSON (``.json``) mappings. Unknown keys are
rejected so typos do not silently change behaviour.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_NAME = "chronosync.toml"
PREFER_CHOICES = ("fail", "local", "remote")


class ConfigError(ValueError):
    """Raised when a configuration file is malformed."""


@dataclass
class Config:
    """Resolved ChronoSync settings."""

    database: str = "dev.db"
    snapshot_dir: str = ".chronosync"
    exclude_tables: list[str] = field(default_factory=list)
    prefer: str = "fail"
    state_file: str = ".chronosync-state.json"


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a raw configuration mapping from a TOML or JSON file.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ConfigError: If the file cannot be parsed or is not a mapping.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    text = p.read_text(encoding="utf-8")
    try:
        if p.suffix.lower() == ".json":
            data = json.loads(text) if text.strip() else {}
        else:
            data = tomllib.loads(text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot parse {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Configuration file {path} must contain a mapping.")
    return data


def build_config(raw: dict[str, Any]) -> Config:
    """Validate a raw mapping and turn it into a :class:`Config`."""
    known = set(Config.__dataclass_fields__)
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"Unknown configuration key(s): {', '.join(unknown)}")

    cfg = Config(**raw)
    for name in ("database", "snapshot_dir", "state_file", "prefer"):
        if not isinstance(getattr(cfg, name), str):
            raise ConfigError(f"'{name}' must be a string")
    if not isinstance(cfg.exclude_tables, list) or not all(
        isinstance(t, str) for t in cfg.exclude_tables
    ):
        raise ConfigError("'exclude_tables' must be a list of strings")
    if cfg.prefer not in PREFER_CHOICES:
        raise ConfigError(f"'prefer' must be one of: {', '.join(PREFER_CHOICES)}")
    return cfg


def resolve_config(path: str | Path | None = None) -> Config:
    """Load settings from ``path`` or ``chronosync.toml`` in the cwd, if present."""
    if path is not None:
        return build_config(load_config(path))
    default = Path(DEFAULT_CONFIG_NAME)
    if default.is_file():
        return build_config(load_config(default))
    return Config()
