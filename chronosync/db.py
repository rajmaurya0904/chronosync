"""Reading and writing SQLite databases as :class:`DatabaseState` objects."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .model import DatabaseState, Row, TableState, content_key, decode_value, encode_value


class DatabaseError(RuntimeError):
    """Raised for problems opening or reading a database."""


def quote(name: str) -> str:
    """Quote an SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def connect(path: str | Path, *, create: bool = False) -> sqlite3.Connection:
    p = Path(path)
    if not create and not p.is_file():
        raise DatabaseError(f"Database not found: {path}")
    try:
        conn = sqlite3.connect(p)
        conn.execute("PRAGMA schema_version").fetchone()
    except sqlite3.DatabaseError as exc:
        raise DatabaseError(f"Not a usable SQLite database: {path} ({exc})") from exc
    return conn


def row_key(pk: list[str], row: Row) -> str:
    """Stable string key for a row: its primary key values, else a content hash."""
    if not pk:
        return content_key(row)
    return "|".join(str(row[c]) for c in pk)


def read_database(conn: sqlite3.Connection, exclude: Iterable[str] = ()) -> DatabaseState:
    """Read every user table (schema + rows) into memory."""
    skip = set(exclude)
    state = DatabaseState()
    tables = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for name, sql in tables:
        if name in skip:
            continue
        info = conn.execute(f"PRAGMA table_info({quote(name)})").fetchall()
        columns = [r[1] for r in info]
        pk = [r[1] for r in sorted((r for r in info if r[5] > 0), key=lambda r: r[5])]
        table = TableState(create_sql=sql, columns=columns, pk=pk)
        cursor = conn.execute(f"SELECT * FROM {quote(name)}")
        for values in cursor:
            row = {c: encode_value(v) for c, v in zip(columns, values, strict=True)}
            table.rows[row_key(pk, row)] = row
        state.tables[name] = table
    return state


def write_database(conn: sqlite3.Connection, state: DatabaseState) -> None:
    """Make the database's rows equal ``state`` (creating missing tables).

    Tables that exist in the database but not in ``state`` are left untouched.
    """
    existing = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    with conn:
        for name, table in state.tables.items():
            if name not in existing:
                conn.execute(table.create_sql)
            conn.execute(f"DELETE FROM {quote(name)}")
            cols = ", ".join(quote(c) for c in table.columns)
            marks = ", ".join("?" for _ in table.columns)
            sql = f"INSERT INTO {quote(name)} ({cols}) VALUES ({marks})"
            conn.executemany(
                sql,
                [
                    [decode_value(row.get(c)) for c in table.columns]
                    for row in table.rows.values()
                ],
            )
