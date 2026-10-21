"""Configuration loader module for ChronoSync."""

from pathlib import Path

import yaml


def load_config(path: str) -> dict:
    """Load configuration from a YAML file.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"Configuration file {path} must contain a YAML mapping/dictionary.")
    return data
