"""Core data model: an in-memory view of a database state."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

Row = dict[str, Any]


def encode_value(value: Any) -> Any:
    """Make a SQLite value JSON-safe (blobs become tagged base64 objects)."""
    if isinstance(value, bytes | bytearray | memoryview):
        return {"$blob": base64.b64encode(bytes(value)).decode("ascii")}
    return value


def decode_value(value: Any) -> Any:
    """Inverse of :func:`encode_value`."""
    if isinstance(value, dict) and set(value) == {"$blob"}:
        return base64.b64decode(value["$blob"])
    return value


def row_json(row: Row) -> str:
    """Canonical one-line JSON for a row (sorted keys, stable across runs)."""
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_key(row: Row) -> str:
    """Key for rows that have no primary key: a short hash of their content."""
    return "h:" + hashlib.sha1(row_json(row).encode("utf-8")).hexdigest()[:16]


@dataclass
class TableState:
    """One table: its CREATE statement, column order and rows by key."""

    create_sql: str
    columns: list[str]
    pk: list[str]
    rows: dict[str, Row] = field(default_factory=dict)


@dataclass
class DatabaseState:
    """All tables of a database (or of a snapshot)."""

    tables: dict[str, TableState] = field(default_factory=dict)

    def row_count(self) -> int:
        return sum(len(t.rows) for t in self.tables.values())


def state_to_dict(state: DatabaseState) -> dict[str, Any]:
    """Plain-JSON form of a state (used for the local last-sync record)."""
    return {
        name: {"create_sql": t.create_sql, "columns": t.columns, "pk": t.pk, "rows": t.rows}
        for name, t in state.tables.items()
    }


def state_from_dict(data: dict[str, Any]) -> DatabaseState:
    """Inverse of :func:`state_to_dict`."""
    return DatabaseState(
        {
            name: TableState(t["create_sql"], t["columns"], t["pk"], t["rows"])
            for name, t in data.items()
        }
    )
