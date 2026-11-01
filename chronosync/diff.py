"""Row-level comparison of two database states."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import DatabaseState


@dataclass
class TableDiff:
    """Differences for one table, as lists of row keys."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    schema_changed: bool = False
    only_in: str | None = None  # "left" / "right" when the table exists on one side only

    @property
    def empty(self) -> bool:
        return not (
            self.added or self.removed or self.changed or self.schema_changed or self.only_in
        )


def diff_states(left: DatabaseState, right: DatabaseState) -> dict[str, TableDiff]:
    """Describe how to get from ``left`` to ``right``.

    ``added`` rows exist only in ``right``; ``removed`` rows only in ``left``.
    Only tables with differences are returned.
    """
    result: dict[str, TableDiff] = {}
    for name in sorted(set(left.tables) | set(right.tables)):
        lt, rt = left.tables.get(name), right.tables.get(name)
        d = TableDiff()
        if lt is None:
            d.only_in = "right"
            d.added = sorted(rt.rows)
        elif rt is None:
            d.only_in = "left"
            d.removed = sorted(lt.rows)
        else:
            d.schema_changed = lt.create_sql != rt.create_sql
            d.added = sorted(set(rt.rows) - set(lt.rows))
            d.removed = sorted(set(lt.rows) - set(rt.rows))
            d.changed = sorted(k for k in set(lt.rows) & set(rt.rows) if lt.rows[k] != rt.rows[k])
        if not d.empty:
            result[name] = d
    return result


def summarize(diff: dict[str, TableDiff], left: str = "left", right: str = "right") -> list[str]:
    """Human-readable one-line-per-table summary; ``left``/``right`` name the two sides."""
    lines = []
    for name, d in diff.items():
        parts = []
        if d.only_in:
            parts.append(f"table only in {left if d.only_in == 'left' else right}")
        if d.added:
            parts.append(f"+{len(d.added)}")
        if d.removed:
            parts.append(f"-{len(d.removed)}")
        if d.changed:
            parts.append(f"~{len(d.changed)}")
        if d.schema_changed:
            parts.append("schema differs")
        lines.append(f"  {name}: {' '.join(parts)}")
    return lines
