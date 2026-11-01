"""Tests for db, store, model and diff modules."""

import sqlite3
from pathlib import Path

import pytest

from chronosync.db import DatabaseError, connect, read_database, write_database
from chronosync.diff import diff_states, summarize
from chronosync.model import DatabaseState, content_key, decode_value, encode_value
from chronosync.store import SnapshotError, read_snapshot, snapshot_exists, write_snapshot


def test_blob_roundtrip() -> None:
    encoded = encode_value(b"\x00\xff")
    assert encoded == {"$blob": "AP8="}
    assert decode_value(encoded) == b"\x00\xff"
    assert decode_value("plain") == "plain"


def test_content_key_is_stable_and_order_independent() -> None:
    assert content_key({"a": 1, "b": 2}) == content_key({"b": 2, "a": 1})
    assert content_key({"a": 1}) != content_key({"a": 2})


def test_read_database(make_db) -> None:
    state = read_database(connect(make_db()))
    users = state.tables["users"]
    assert users.pk == ["id"]
    assert users.columns == ["id", "name"]
    assert users.rows["1"] == {"id": 1, "name": "ada"}
    assert state.row_count() == 2


def test_read_database_excludes_tables(make_db) -> None:
    conn = connect(make_db())
    conn.execute("CREATE TABLE cache (k TEXT)")
    state = read_database(conn, exclude=["cache"])
    assert list(state.tables) == ["users"]


def test_table_without_primary_key_uses_content_keys(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "a.db")
    conn.execute("CREATE TABLE log (msg TEXT)")
    conn.executemany("INSERT INTO log VALUES (?)", [("a",), ("b",)])
    state = read_database(conn)
    assert all(k.startswith("h:") for k in state.tables["log"].rows)
    assert len(state.tables["log"].rows) == 2


def test_connect_missing_database(tmp_path: Path) -> None:
    with pytest.raises(DatabaseError):
        connect(tmp_path / "nope.db")


def test_connect_rejects_non_sqlite(tmp_path: Path) -> None:
    bad = tmp_path / "bad.db"
    bad.write_text("this is definitely not sqlite " * 20)
    with pytest.raises(DatabaseError):
        connect(bad)


def test_snapshot_roundtrip(make_db, tmp_path: Path) -> None:
    state = read_database(connect(make_db()))
    snap = tmp_path / "snap"
    assert not snapshot_exists(snap)
    write_snapshot(snap, state)
    assert snapshot_exists(snap)
    loaded = read_snapshot(snap)
    assert loaded.tables["users"].rows == state.tables["users"].rows
    assert loaded.tables["users"].create_sql == state.tables["users"].create_sql


def test_snapshot_is_deterministic(make_db, tmp_path: Path) -> None:
    state = read_database(connect(make_db()))
    write_snapshot(tmp_path / "s1", state)
    write_snapshot(tmp_path / "s2", state)
    for rel in ("manifest.json", "data/users.jsonl", "schema/users.sql"):
        assert (tmp_path / "s1" / rel).read_bytes() == (tmp_path / "s2" / rel).read_bytes()


def test_snapshot_removes_stale_table_files(make_db, tmp_path: Path) -> None:
    conn = connect(make_db())
    conn.execute("CREATE TABLE extra (id INTEGER PRIMARY KEY)")
    snap = tmp_path / "snap"
    write_snapshot(snap, read_database(conn))
    assert (snap / "data" / "extra.jsonl").exists()
    write_snapshot(snap, read_database(conn, exclude=["extra"]))
    assert not (snap / "data" / "extra.jsonl").exists()


def test_read_snapshot_missing(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError):
        read_snapshot(tmp_path / "none")


def test_read_snapshot_corrupt(make_db, tmp_path: Path) -> None:
    snap = tmp_path / "snap"
    write_snapshot(snap, read_database(connect(make_db())))
    (snap / "data" / "users.jsonl").write_text("{not json\n", encoding="utf-8")
    with pytest.raises(SnapshotError):
        read_snapshot(snap)


def test_write_database_mirrors_state(make_db) -> None:
    src = read_database(connect(make_db("a.db", users=[(1, "x"), (5, "y")])))
    target = connect(make_db("b.db", users=[(9, "old")]))
    write_database(target, src)
    rows = target.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    assert rows == [(1, "x"), (5, "y")]


def test_write_database_creates_missing_table(make_db, tmp_path: Path) -> None:
    src = read_database(connect(make_db()))
    empty = sqlite3.connect(tmp_path / "empty.db")
    write_database(empty, src)
    assert empty.execute("SELECT COUNT(*) FROM users").fetchone() == (2,)


def test_blob_survives_snapshot(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "b.db")
    conn.execute("CREATE TABLE f (id INTEGER PRIMARY KEY, data BLOB)")
    conn.execute("INSERT INTO f VALUES (1, ?)", (b"\x00\x01\x02",))
    write_snapshot(tmp_path / "s", read_database(conn))
    other = sqlite3.connect(tmp_path / "o.db")
    write_database(other, read_snapshot(tmp_path / "s"))
    assert other.execute("SELECT data FROM f").fetchone() == (b"\x00\x01\x02",)


def test_diff_states(make_db) -> None:
    a = read_database(connect(make_db("a.db", users=[(1, "a"), (2, "b")])))
    b = read_database(connect(make_db("b.db", users=[(2, "B"), (3, "c")])))
    d = diff_states(a, b)["users"]
    assert d.added == ["3"]
    assert d.removed == ["1"]
    assert d.changed == ["2"]
    assert summarize({"users": d}) == ["  users: +1 -1 ~1"]


def test_diff_identical_is_empty(make_db) -> None:
    a = read_database(connect(make_db()))
    assert diff_states(a, a) == {}


def test_diff_table_on_one_side(make_db) -> None:
    a = read_database(connect(make_db()))
    d = diff_states(a, DatabaseState())["users"]
    assert d.only_in == "left"
    assert d.removed == ["1", "2"]
