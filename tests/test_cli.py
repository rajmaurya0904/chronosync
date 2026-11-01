"""End-to-end tests for the command line interface."""

import json
import sqlite3
from pathlib import Path

import pytest

from chronosync import cli


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*argv: str) -> int:
    return cli.main(list(argv))


def sql(path: Path | str, *stmts: str) -> list:
    conn = sqlite3.connect(path)
    out: list = []
    for s in stmts:
        out = conn.execute(s).fetchall()
    conn.commit()
    conn.close()
    return out


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        run("--help")
    assert exc.value.code == 0
    assert "sync" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        run("--version")
    assert "chronosync" in capsys.readouterr().out


def test_command_required() -> None:
    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 2


def test_init_writes_config_once(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("init") == 0
    assert (workdir / "chronosync.toml").is_file()
    assert run("init") == 1
    assert "already exists" in capsys.readouterr().err
    assert run("init", "--force") == 0


def test_init_config_is_loadable(workdir: Path) -> None:
    from chronosync.config import resolve_config

    run("init")
    assert resolve_config().snapshot_dir == ".chronosync"


def test_push_then_status_in_sync(make_db, workdir: Path, capsys) -> None:
    db = make_db()
    assert run("push", "-d", str(db), "-s", "snap") == 0
    assert (workdir / "snap" / "data" / "users.jsonl").is_file()
    capsys.readouterr()
    assert run("status", "-d", str(db), "-s", "snap") == 0
    assert "In sync" in capsys.readouterr().out


def test_status_reports_difference(make_db, workdir: Path, capsys) -> None:
    db = make_db()
    run("push", "-d", str(db), "-s", "snap")
    sql(db, "INSERT INTO users VALUES (3, 'linus')")
    capsys.readouterr()
    assert run("status", "-d", str(db), "-s", "snap") == cli.EXIT_DIFFERS
    assert "users: +1" in capsys.readouterr().out


def test_push_dry_run_writes_nothing(make_db, workdir: Path, capsys) -> None:
    db = make_db()
    assert run("push", "-n", "-d", str(db), "-s", "snap") == 0
    assert not (workdir / "snap").exists()
    assert "Dry run" in capsys.readouterr().out


def test_pull_creates_database(make_db, workdir: Path) -> None:
    src = make_db("src.db")
    run("push", "-d", str(src), "-s", "snap")
    assert run("pull", "-d", "fresh.db", "-s", "snap") == 0
    assert sql("fresh.db", "SELECT id, name FROM users ORDER BY id") == [(1, "ada"), (2, "grace")]


def test_pull_overwrites_local_changes(make_db, workdir: Path) -> None:
    db = make_db()
    run("push", "-d", str(db), "-s", "snap")
    sql(db, "DELETE FROM users", "INSERT INTO users VALUES (9, 'x')")
    run("pull", "-d", str(db), "-s", "snap")
    assert sql(db, "SELECT COUNT(*) FROM users") == [(2,)]


def test_pull_dry_run_leaves_database(make_db, workdir: Path) -> None:
    db = make_db()
    run("push", "-d", str(db), "-s", "snap")
    sql(db, "INSERT INTO users VALUES (3, 'z')")
    assert run("pull", "-n", "-d", str(db), "-s", "snap") == 0
    assert sql(db, "SELECT COUNT(*) FROM users") == [(3,)]


def test_pull_without_snapshot_is_error(make_db, workdir: Path, capsys) -> None:
    assert run("pull", "-d", str(make_db()), "-s", "nothing") == 1
    assert "No snapshot" in capsys.readouterr().err


def test_push_missing_database_is_error(workdir: Path, capsys) -> None:
    assert run("push", "-d", "missing.db", "-s", "snap") == 1
    assert "Database not found" in capsys.readouterr().err


def test_exclude_table(make_db, workdir: Path) -> None:
    db = make_db()
    sql(db, "CREATE TABLE secrets (k TEXT)", "INSERT INTO secrets VALUES ('s')")
    run("push", "-d", str(db), "-s", "snap", "-x", "secrets")
    assert not (workdir / "snap" / "data" / "secrets.jsonl").exists()
    assert (workdir / "snap" / "data" / "users.jsonl").exists()


def test_config_file_supplies_defaults(make_db, workdir: Path) -> None:
    db = make_db()
    (workdir / "chronosync.toml").write_text(
        f'database = "{db.as_posix()}"\nsnapshot_dir = "from-config"\n', encoding="utf-8"
    )
    assert run("push") == 0
    assert (workdir / "from-config" / "manifest.json").is_file()


def test_bad_config_is_error(workdir: Path, capsys) -> None:
    (workdir / "chronosync.toml").write_text("bogus = 1\n", encoding="utf-8")
    assert run("status") == 1
    assert "bogus" in capsys.readouterr().err


def test_sync_two_clones_merge(make_db, workdir: Path) -> None:
    alice = make_db("alice.db")
    bob = workdir / "bob.db"
    run("push", "-d", str(alice), "-s", "snap", "--exclude", "none")
    run("pull", "-d", str(bob), "-s", "snap")
    # separate state files so the two "machines" do not share a base
    state_a = workdir / "a.state"
    state_a.write_bytes(Path(".chronosync-state.json").read_bytes())
    sql(bob, "INSERT INTO users VALUES (3, 'linus')")
    assert run("sync", "-d", str(bob), "-s", "snap") == 0
    Path(".chronosync-state.json").write_bytes(state_a.read_bytes())
    sql(alice, "UPDATE users SET name = 'ADA' WHERE id = 1")
    assert run("sync", "-d", str(alice), "-s", "snap") == 0
    assert sql(alice, "SELECT id, name FROM users ORDER BY id") == [
        (1, "ADA"),
        (2, "grace"),
        (3, "linus"),
    ]


def test_sync_conflict_blocks_then_prefer_resolves(make_db, workdir: Path, capsys) -> None:
    db = make_db()
    run("push", "-d", str(db), "-s", "snap")
    # someone else edits the snapshot directly
    path = workdir / "snap" / "data" / "users.jsonl"
    path.write_text(path.read_text().replace('"ada"', '"remote-ada"'), encoding="utf-8")
    sql(db, "UPDATE users SET name = 'local-ada' WHERE id = 1")
    assert run("sync", "-d", str(db), "-s", "snap") == cli.EXIT_CONFLICT
    assert sql(db, "SELECT name FROM users WHERE id = 1") == [("local-ada",)]
    assert "1 conflict" in capsys.readouterr().err
    assert run("sync", "-d", str(db), "-s", "snap", "--prefer", "remote") == 0
    assert sql(db, "SELECT name FROM users WHERE id = 1") == [("remote-ada",)]


def test_sync_dry_run_changes_nothing(make_db, workdir: Path) -> None:
    db = make_db()
    run("push", "-d", str(db), "-s", "snap")
    sql(db, "INSERT INTO users VALUES (3, 'new')")
    before = (workdir / "snap" / "data" / "users.jsonl").read_text()
    assert run("sync", "-n", "-d", str(db), "-s", "snap") == 0
    assert (workdir / "snap" / "data" / "users.jsonl").read_text() == before


def test_sync_first_run_without_snapshot_creates_it(make_db, workdir: Path) -> None:
    db = make_db()
    assert run("sync", "-d", str(db), "-s", "snap") == 0
    assert (workdir / "snap" / "manifest.json").is_file()


def test_sync_schema_mismatch_is_error(make_db, workdir: Path, capsys) -> None:
    db = make_db()
    run("push", "-d", str(db), "-s", "snap")
    sql(db, "ALTER TABLE users ADD COLUMN age INTEGER")
    assert run("sync", "-d", str(db), "-s", "snap") == 1
    assert "migrate it manually" in capsys.readouterr().err


def test_snapshot_files_are_git_friendly(make_db, workdir: Path) -> None:
    db = make_db()
    run("push", "-d", str(db), "-s", "snap")
    manifest = json.loads((workdir / "snap" / "manifest.json").read_text())
    assert manifest["tables"]["users"]["rows"] == 2
    data = (workdir / "snap" / "data" / "users.jsonl").read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
