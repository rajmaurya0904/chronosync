"""Tests for the three-way merge."""

import pytest

from chronosync.merge import SchemaMismatch, merge_states
from chronosync.model import DatabaseState, TableState


def state(rows: dict[str, str], cols=("id", "name")) -> DatabaseState:
    t = TableState(
        create_sql="CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)",
        columns=list(cols),
        pk=["id"],
    )
    t.rows = {k: {"id": int(k), "name": v} for k, v in rows.items()}
    return DatabaseState({"t": t})


def names(result) -> dict[str, str]:
    return {k: r["name"] for k, r in result.state.tables["t"].rows.items()}


def test_identical_sides_no_changes() -> None:
    s = state({"1": "a"})
    r = merge_states(s, s, s)
    assert names(r) == {"1": "a"}
    assert (r.local_changes, r.remote_changes, r.conflicts) == (0, 0, [])


def test_remote_edit_applies_locally() -> None:
    r = merge_states(state({"1": "a"}), state({"1": "a"}), state({"1": "b"}))
    assert names(r) == {"1": "b"}
    assert (r.local_changes, r.remote_changes) == (1, 0)


def test_local_edit_applies_to_remote() -> None:
    r = merge_states(state({"1": "a"}), state({"1": "z"}), state({"1": "a"}))
    assert names(r) == {"1": "z"}
    assert (r.local_changes, r.remote_changes) == (0, 1)


def test_additions_on_both_sides_combine() -> None:
    r = merge_states(state({}), state({"1": "a"}), state({"2": "b"}))
    assert names(r) == {"1": "a", "2": "b"}
    assert (r.local_changes, r.remote_changes) == (1, 1)


def test_remote_deletion_propagates() -> None:
    r = merge_states(state({"1": "a"}), state({"1": "a"}), state({}))
    assert names(r) == {}
    assert r.local_changes == 1


def test_no_base_keeps_one_sided_rows() -> None:
    r = merge_states(None, state({"1": "a"}), state({}))
    assert names(r) == {"1": "a"}


def test_conflict_reported_by_default() -> None:
    r = merge_states(state({"1": "a"}), state({"1": "L"}), state({"1": "R"}))
    assert len(r.conflicts) == 1
    assert (r.conflicts[0].table, r.conflicts[0].key) == ("t", "1")


def test_conflict_prefer_local_and_remote() -> None:
    args = (state({"1": "a"}), state({"1": "L"}), state({"1": "R"}))
    assert names(merge_states(*args, prefer="local")) == {"1": "L"}
    assert names(merge_states(*args, prefer="remote")) == {"1": "R"}
    assert merge_states(*args, prefer="local").conflicts == []


def test_edit_vs_delete_is_conflict() -> None:
    r = merge_states(state({"1": "a"}), state({"1": "L"}), state({}))
    assert len(r.conflicts) == 1
    assert r.conflicts[0].remote is None


def test_schema_mismatch_raises() -> None:
    with pytest.raises(SchemaMismatch):
        merge_states(None, state({}), state({}, cols=("id", "title")))


def test_table_only_on_remote_is_added() -> None:
    r = merge_states(DatabaseState(), DatabaseState(), state({"1": "a"}))
    assert names(r) == {"1": "a"}
