"""Tests for chronosync.config module."""

from pathlib import Path

import pytest

from chronosync.config import load_config


def test_load_config_valid(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("database_url: sqlite:///test.db\nsync_interval: 60\n", encoding="utf-8")

    result = load_config(str(cfg_file))
    assert result == {"database_url": "sqlite:///test.db", "sync_interval": 60}


def test_load_config_missing(tmp_path: Path) -> None:
    missing_file = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(str(missing_file))


def test_load_config_empty(tmp_path: Path) -> None:
    cfg_file = tmp_path / "empty.yaml"
    cfg_file.write_text("", encoding="utf-8")
    result = load_config(str(cfg_file))
    assert result == {}
