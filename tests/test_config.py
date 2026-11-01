"""Tests for chronosync.config module."""

from pathlib import Path

import pytest

from chronosync.config import (
    Config,
    ConfigError,
    build_config,
    load_config,
    resolve_config,
)


def test_load_config_toml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('database = "x.db"\nprefer = "local"\n', encoding="utf-8")
    assert load_config(cfg_file) == {"database": "x.db", "prefer": "local"}


def test_load_config_json(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"database": "y.db"}', encoding="utf-8")
    assert load_config(cfg_file) == {"database": "y.db"}


def test_load_config_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.toml")


def test_load_config_empty_json(tmp_path: Path) -> None:
    cfg_file = tmp_path / "empty.json"
    cfg_file.write_text("", encoding="utf-8")
    assert load_config(cfg_file) == {}


def test_load_config_invalid_toml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "bad.toml"
    cfg_file.write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(cfg_file)


def test_load_config_json_not_mapping(tmp_path: Path) -> None:
    cfg_file = tmp_path / "list.json"
    cfg_file.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(cfg_file)


def test_build_config_defaults() -> None:
    cfg = build_config({})
    assert cfg == Config()
    assert cfg.prefer == "fail"


def test_build_config_rejects_unknown_key() -> None:
    with pytest.raises(ConfigError, match="bogus"):
        build_config({"bogus": 1})


def test_build_config_rejects_bad_prefer() -> None:
    with pytest.raises(ConfigError, match="prefer"):
        build_config({"prefer": "both"})


def test_build_config_rejects_bad_exclude() -> None:
    with pytest.raises(ConfigError, match="exclude_tables"):
        build_config({"exclude_tables": "users"})


def test_resolve_config_uses_cwd_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "chronosync.toml").write_text('database = "z.db"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_config().database == "z.db"


def test_resolve_config_without_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert resolve_config() == Config()
