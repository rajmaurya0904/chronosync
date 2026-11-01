"""On-disk snapshot format.

A snapshot directory contains::

    manifest.json     table list with column order, primary key and row counts
    schema/<t>.sql    the CREATE TABLE statement of each table
    data/<t>.jsonl    one canonical JSON object per row, sorted by key

Every file is deterministic, so unchanged data produces no git diff and changed rows show
up as single-line diffs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .db import row_key
from .model import DatabaseState, TableState, row_json

FORMAT_VERSION = 1
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


class SnapshotError(RuntimeError):
    """Raised when a snapshot directory is missing or corrupt."""


def _fname(table: str) -> str:
    return _SAFE.sub("_", table)


def snapshot_exists(directory: str | Path) -> bool:
    return (Path(directory) / "manifest.json").is_file()


def write_snapshot(directory: str | Path, state: DatabaseState) -> None:
    """Replace the contents of ``directory`` with ``state``."""
    root = Path(directory)
    (root / "schema").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    for old in [*(root / "schema").glob("*.sql"), *(root / "data").glob("*.jsonl")]:
        old.unlink()

    manifest: dict = {"format": FORMAT_VERSION, "tables": {}}
    for name in sorted(state.tables):
        table = state.tables[name]
        fname = _fname(name)
        (root / "schema" / f"{fname}.sql").write_text(table.create_sql + "\n", encoding="utf-8")
        lines = [row_json(table.rows[k]) for k in sorted(table.rows)]
        (root / "data" / f"{fname}.jsonl").write_text(
            "".join(line + "\n" for line in lines), encoding="utf-8", newline="\n"
        )
        manifest["tables"][name] = {
            "file": fname,
            "columns": table.columns,
            "primary_key": table.pk,
            "rows": len(lines),
        }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def read_snapshot(directory: str | Path) -> DatabaseState:
    """Load a snapshot directory back into a :class:`DatabaseState`."""
    root = Path(directory)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotError(f"No snapshot found in {directory} (missing manifest.json)")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != FORMAT_VERSION:
            raise SnapshotError(f"Unsupported snapshot format: {manifest.get('format')!r}")
        state = DatabaseState()
        for name, meta in manifest["tables"].items():
            fname = meta["file"]
            sql = (root / "schema" / f"{fname}.sql").read_text(encoding="utf-8").strip()
            table = TableState(create_sql=sql, columns=meta["columns"], pk=meta["primary_key"])
            data = (root / "data" / f"{fname}.jsonl").read_text(encoding="utf-8")
            for line in data.splitlines():
                if line.strip():
                    row = json.loads(line)
                    table.rows[row_key(table.pk, row)] = row
            state.tables[name] = table
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Corrupt snapshot in {directory}: {exc}") from exc
    return state
