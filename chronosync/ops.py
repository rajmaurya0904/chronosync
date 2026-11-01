"""High-level operations: push, pull, status and sync."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .db import connect, read_database, write_database
from .diff import TableDiff, diff_states
from .merge import Conflict, merge_states
from .model import DatabaseState, state_from_dict, state_to_dict
from .store import SnapshotError, read_snapshot, snapshot_exists, write_snapshot


@dataclass
class OpResult:
    """Outcome of an operation, for the CLI to print."""

    action: str
    left: str = "snapshot"
    right: str = "database"
    diff: dict[str, TableDiff] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)
    applied: bool = False
    rows: int = 0
    local_changes: int = 0
    remote_changes: int = 0


def _local(cfg: Config, *, create: bool = False) -> DatabaseState:
    conn = connect(cfg.database, create=create)
    try:
        return read_database(conn, cfg.exclude_tables)
    finally:
        conn.close()


def _filter(state: DatabaseState, exclude: list[str]) -> DatabaseState:
    return DatabaseState({n: t for n, t in state.tables.items() if n not in set(exclude)})


def load_base(cfg: Config) -> DatabaseState | None:
    """Load the state recorded at the last successful push/pull/sync, if any."""
    path = Path(cfg.state_file)
    if not path.is_file():
        return None
    try:
        return state_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError) as exc:
        raise SnapshotError(f"Corrupt state file {path}: {exc}") from exc


def save_base(cfg: Config, state: DatabaseState) -> None:
    Path(cfg.state_file).write_text(
        json.dumps(state_to_dict(state), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )


def status(cfg: Config) -> OpResult:
    """Compare the local database with the snapshot (snapshot is 'right')."""
    local = _local(cfg)
    remote = _filter(read_snapshot(cfg.snapshot_dir), cfg.exclude_tables)
    return OpResult("status", diff=diff_states(remote, local))


def push(cfg: Config, *, dry_run: bool = False) -> OpResult:
    """Overwrite the snapshot with the local database."""
    local = _local(cfg)
    previous = (
        _filter(read_snapshot(cfg.snapshot_dir), cfg.exclude_tables)
        if snapshot_exists(cfg.snapshot_dir)
        else DatabaseState()
    )
    result = OpResult("push", diff=diff_states(previous, local), rows=local.row_count())
    if not dry_run:
        write_snapshot(cfg.snapshot_dir, local)
        save_base(cfg, local)
        result.applied = True
    return result


def pull(cfg: Config, *, dry_run: bool = False) -> OpResult:
    """Overwrite the local database's rows with the snapshot."""
    remote = _filter(read_snapshot(cfg.snapshot_dir), cfg.exclude_tables)
    local = _local(cfg) if Path(cfg.database).exists() else DatabaseState()
    result = OpResult(
        "pull",
        left="database",
        right="snapshot",
        diff=diff_states(local, remote),
        rows=remote.row_count(),
    )
    if not dry_run:
        conn = connect(cfg.database, create=True)
        try:
            write_database(conn, remote)
        finally:
            conn.close()
        save_base(cfg, remote)
        result.applied = True
    return result


def sync(cfg: Config, *, dry_run: bool = False, prefer: str | None = None) -> OpResult:
    """Merge local and snapshot changes both ways, relative to the last sync."""
    prefer = prefer or cfg.prefer
    local = _local(cfg)
    if snapshot_exists(cfg.snapshot_dir):
        remote = _filter(read_snapshot(cfg.snapshot_dir), cfg.exclude_tables)
    else:
        remote = DatabaseState()
    merged = merge_states(load_base(cfg), local, remote, prefer)
    result = OpResult(
        "sync",
        diff=diff_states(remote, local),
        conflicts=merged.conflicts,
        rows=merged.state.row_count(),
        local_changes=merged.local_changes,
        remote_changes=merged.remote_changes,
    )
    if merged.conflicts or dry_run:
        return result
    conn = connect(cfg.database)
    try:
        write_database(conn, merged.state)
    finally:
        conn.close()
    write_snapshot(cfg.snapshot_dir, merged.state)
    save_base(cfg, merged.state)
    result.applied = True
    return result
