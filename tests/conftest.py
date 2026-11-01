"""Shared fixtures."""

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def make_db(tmp_path: Path):
    """Factory: create a SQLite file with a users table."""

    def _make(name: str = "dev.db", users=((1, "ada"), (2, "grace"))) -> Path:
        path = tmp_path / name
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conn.executemany("INSERT INTO users VALUES (?, ?)", users)
        conn.commit()
        conn.close()
        return path

    return _make
