"""Command line interface for ChronoSync."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, ops
from .config import DEFAULT_CONFIG_NAME, PREFER_CHOICES, Config, ConfigError, resolve_config
from .db import DatabaseError
from .diff import summarize
from .merge import SchemaMismatch
from .store import SnapshotError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFLICT = 2
EXIT_DIFFERS = 3  # status: local and snapshot differ


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", help=f"config file (default: ./{DEFAULT_CONFIG_NAME})")
    common.add_argument("-d", "--database", help="SQLite database file")
    common.add_argument("-s", "--snapshot-dir", help="directory holding the snapshot")
    common.add_argument(
        "-x", "--exclude", action="append", metavar="TABLE", help="skip a table (repeatable)"
    )

    parser = argparse.ArgumentParser(
        prog="chronosync",
        description="Sync a local SQLite dev database with a git-friendly snapshot.",
    )
    parser.add_argument("--version", action="version", version=f"chronosync {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("init", help=f"write a starter {DEFAULT_CONFIG_NAME}")
    p.add_argument("--force", action="store_true", help="overwrite an existing config")

    sub.add_parser("status", parents=[common], help="show how the database and snapshot differ")

    p = sub.add_parser("push", parents=[common], help="write the database into the snapshot")
    p.add_argument("-n", "--dry-run", action="store_true", help="show changes without writing")

    p = sub.add_parser("pull", parents=[common], help="load the snapshot into the database")
    p.add_argument("-n", "--dry-run", action="store_true", help="show changes without writing")

    p = sub.add_parser("sync", parents=[common], help="merge changes in both directions")
    p.add_argument("-n", "--dry-run", action="store_true", help="show changes without writing")
    p.add_argument(
        "--prefer",
        choices=PREFER_CHOICES,
        help="how to settle rows changed on both sides (default: fail)",
    )
    return parser


def _config_from_args(args: argparse.Namespace) -> Config:
    cfg = resolve_config(args.config)
    overrides = {}
    if args.database:
        overrides["database"] = args.database
    if args.snapshot_dir:
        overrides["snapshot_dir"] = args.snapshot_dir
    if args.exclude:
        overrides["exclude_tables"] = [*cfg.exclude_tables, *args.exclude]
    return dataclasses.replace(cfg, **overrides)


def _print_diff(result: ops.OpResult, out) -> None:
    lines = summarize(result.diff, result.left, result.right)
    if lines:
        print("\n".join(lines), file=out)


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(DEFAULT_CONFIG_NAME)
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return EXIT_ERROR
    defaults = Config()
    path.write_text(
        "# ChronoSync settings\n"
        f'database = "{defaults.database}"\n'
        f'snapshot_dir = "{defaults.snapshot_dir}"\n'
        "exclude_tables = []\n"
        f'prefer = "{defaults.prefer}"  # fail | local | remote\n',
        encoding="utf-8",
    )
    print(f"Wrote {path}")
    return EXIT_OK


def _cmd_status(cfg: Config) -> int:
    result = ops.status(cfg)
    if not result.diff:
        print("In sync: database matches snapshot.")
        return EXIT_OK
    print("Database differs from snapshot (+ rows only in database, - rows only in snapshot):")
    _print_diff(result, sys.stdout)
    return EXIT_DIFFERS


def _cmd_push_pull(cfg: Config, args: argparse.Namespace) -> int:
    fn = ops.push if args.command == "push" else ops.pull
    result = fn(cfg, dry_run=args.dry_run)
    verb = args.command.capitalize()
    if args.dry_run:
        print(f"Dry run: {args.command} would change {len(result.diff)} table(s).")
        _print_diff(result, sys.stdout)
    elif not result.diff:
        print(f"{verb}ed {result.rows} row(s); nothing changed.")
    else:
        print(f"{verb}ed {result.rows} row(s); changes:")
        _print_diff(result, sys.stdout)
    return EXIT_OK


def _cmd_sync(cfg: Config, args: argparse.Namespace) -> int:
    result = ops.sync(cfg, dry_run=args.dry_run, prefer=args.prefer)
    if result.conflicts:
        print(f"{len(result.conflicts)} conflict(s); nothing was changed:", file=sys.stderr)
        for c in result.conflicts:
            print(
                f"  {c.table} [{c.key}]\n    local:  {c.local}\n    remote: {c.remote}",
                file=sys.stderr,
            )
        print("Re-run with --prefer local or --prefer remote to settle them.", file=sys.stderr)
        return EXIT_CONFLICT
    prefix = "Dry run: would apply" if args.dry_run else "Synced;"
    print(
        f"{prefix} {result.local_changes} row change(s) to the database, "
        f"{result.remote_changes} to the snapshot ({result.rows} row(s) total)."
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            return _cmd_init(args)
        cfg = _config_from_args(args)
        if args.command == "status":
            return _cmd_status(cfg)
        if args.command == "sync":
            return _cmd_sync(cfg, args)
        return _cmd_push_pull(cfg, args)
    except (ConfigError, DatabaseError, SnapshotError, SchemaMismatch, FileNotFoundError) as exc:
        print(f"chronosync: error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
