"""Tests for chronosync.ops using the Python API directly."""

import sqlite3
from pathlib import Path

import pytest

from chronosync import ops
from chronosync.config import Config
from chronosync.db import read_database


def cfg_for(tmp_path: Path, db: Path, **kw) -> Config:
    return Config(
        database=str(db),
        snapshot_dir=str(tmp_path / "snap"),
        state_file=str(tmp_path / "state.json"),
        **kw,
    )


def test_composite_primary_key(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE m (a INTEGER, b INTEGER, v TEXT, PRIMARY KEY (a, b))")
    conn.executemany("INSERT INTO m VALUES (?,?,?)", [(1, 1, "x"), (1, 2, "y")])
    conn.commit()
    state = read_database(conn)
    assert sorted(state.tables["m"].rows) == ["1|1", "1|2"]
    assert state.tables["m"].pk == ["a", "b"]


def test_unicode_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "u.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, s TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'héllo ✓ 日本')")
    conn.commit()
    conn.close()
    cfg = cfg_for(tmp_path, db)
    ops.push(cfg)
    other = tmp_path / "o.db"
    ops.pull(cfg_for(tmp_path, other))
    assert sqlite3.connect(other).execute("SELECT s FROM t").fetchone() == ("héllo ✓ 日本",)


def test_push_result_counts(make_db, tmp_path: Path) -> None:
    cfg = cfg_for(tmp_path, make_db())
    first = ops.push(cfg)
    assert first.applied and first.rows == 2
    again = ops.push(cfg)
    assert again.diff == {}


def test_status_empty_after_push(make_db, tmp_path: Path) -> None:
    cfg = cfg_for(tmp_path, make_db())
    ops.push(cfg)
    assert ops.status(cfg).diff == {}


def test_sync_local_delete_propagates(make_db, tmp_path: Path) -> None:
    db = make_db()
    cfg = cfg_for(tmp_path, db)
    ops.push(cfg)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM users WHERE id = 2")
    conn.commit()
    conn.close()
    result = ops.sync(cfg)
    assert result.applied and result.remote_changes == 1
    assert list(ops.status(cfg).diff) == []
    assert ops.pull(cfg_for(tmp_path, tmp_path / "fresh.db")).rows == 1


def test_sync_excluded_tables_are_ignored(make_db, tmp_path: Path) -> None:
    db = make_db()
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE cache (k TEXT)")
    conn.execute("INSERT INTO cache VALUES ('x')")
    conn.commit()
    conn.close()
    cfg = cfg_for(tmp_path, db, exclude_tables=["cache"])
    ops.sync(cfg)
    assert not (tmp_path / "snap" / "data" / "cache.jsonl").exists()
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM cache").fetchone() == (1,)


def test_corrupt_state_file_is_reported(make_db, tmp_path: Path) -> None:
    cfg = cfg_for(tmp_path, make_db())
    ops.push(cfg)
    Path(cfg.state_file).write_text("not json", encoding="utf-8")
    from chronosync.store import SnapshotError

    with pytest.raises(SnapshotError):
        ops.sync(cfg)
