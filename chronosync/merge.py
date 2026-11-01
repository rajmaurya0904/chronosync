"""Three-way merge of a local database and a remote snapshot against their last common base."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import DatabaseState, TableState


class SchemaMismatch(RuntimeError):
    """Raised when a table has different columns or keys on the two sides."""


@dataclass
class Conflict:
    table: str
    key: str
    local: dict | None
    remote: dict | None


@dataclass
class MergeResult:
    state: DatabaseState
    conflicts: list[Conflict] = field(default_factory=list)
    # How many rows each side must change to reach the merged state.
    local_changes: int = 0
    remote_changes: int = 0


def merge_states(
    base: DatabaseState | None,
    local: DatabaseState,
    remote: DatabaseState,
    prefer: str = "fail",
) -> MergeResult:
    """Merge ``local`` and ``remote`` rows using ``base`` to tell edits from deletions.

    A row changed on only one side takes that side's version. If both sides changed it
    differently (or one deleted what the other edited) it is a conflict, settled by
    ``prefer`` ("local" or "remote") or reported when ``prefer`` is "fail". Without a base,
    every row present on only one side counts as an addition.
    """
    base = base or DatabaseState()
    merged = DatabaseState()
    result = MergeResult(state=merged)

    for name in sorted(set(local.tables) | set(remote.tables)):
        lt, rt, bt = local.tables.get(name), remote.tables.get(name), base.tables.get(name)
        if lt and rt and (lt.columns != rt.columns or lt.pk != rt.pk):
            raise SchemaMismatch(
                f"Table '{name}' has different columns or primary key locally "
                f"({lt.columns}) and in the snapshot ({rt.columns}); migrate it manually."
            )
        proto = lt or rt
        out = TableState(create_sql=proto.create_sql, columns=proto.columns, pk=proto.pk)
        l_rows = lt.rows if lt else {}
        r_rows = rt.rows if rt else {}
        b_rows = bt.rows if bt else {}

        for key in sorted(set(l_rows) | set(r_rows) | set(b_rows)):
            lv, rv, bv = l_rows.get(key), r_rows.get(key), b_rows.get(key)
            if lv == rv:
                final = lv
            elif lv == bv:
                final = rv
            elif rv == bv:
                final = lv
            elif prefer == "local":
                final = lv
            elif prefer == "remote":
                final = rv
            else:
                result.conflicts.append(Conflict(name, key, lv, rv))
                final = lv  # placeholder; callers must not apply a conflicted merge
            if final is not None:
                out.rows[key] = final
            if final != lv:
                result.local_changes += 1
            if final != rv:
                result.remote_changes += 1
        merged.tables[name] = out
    return result
