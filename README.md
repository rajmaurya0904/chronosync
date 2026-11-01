# ChronoSync

**A lightweight CLI tool to bidirectionally synchronize local development database states and test fixtures across team members without dumping heavy files into git.**

ChronoSync solves the pain of sharing database states and test fixtures among developers. Instead of committing bulky dumps to git, it lets you push and pull a lightweight snapshot of your local data, keeping the repository clean and ensuring every team member works with the same baseline.

The snapshot is a directory of one-line-per-row JSON files in a stable order, so a changed row is a one-line git diff and unchanged data produces no diff at all. It has no third-party dependencies (Python 3.11+).

## Example

Alice pushes her dev database, Bob pulls it and edits it, and both later sync. The output below
is copied from a real run (`-s ../shared` points both at one shared snapshot directory, which in
practice is a folder in your git repo):

```console
$ chronosync push -s ../shared
Pushed 3 row(s); changes:
  users: table only in database +3
$ chronosync pull -s ../shared
Pulled 3 row(s); changes:
  users: table only in snapshot +3
$ chronosync status -s ../shared
Database differs from snapshot (+ rows only in database, - rows only in snapshot):
  users: +1 ~1
$ chronosync sync -s ../shared
Synced; 0 row change(s) to the database, 2 to the snapshot (4 row(s) total).
$ chronosync sync -s ../shared
1 conflict(s); nothing was changed:
  users [1]
    local:  {"email":"ada@example.com","id":1,"name":"Ada L."}
    remote: {"email":"ada@example.com","id":1,"name":"Ada Lovelace"}
Re-run with --prefer local or --prefer remote to settle them.
$ chronosync sync -s ../shared --prefer remote
Synced; 2 row change(s) to the database, 1 to the snapshot (3 row(s) total).
$ cat ../shared/data/users.jsonl
{"email":"ada@example.com","id":1,"name":"Ada Lovelace"}
{"email":"grace@example.com","id":2,"name":"Grace"}
{"email":"ken@example.com","id":4,"name":"Ken"}
```

## Install

```bash
pip install -e ".[dev]"
```

This installs the `chronosync` command (also available as `python -m chronosync`).

## Usage

```bash
chronosync init                           # write a starter chronosync.toml
chronosync push                           # database -> snapshot
chronosync pull                           # snapshot -> database (creates it if missing)
chronosync status                         # how do they differ? (exit code 3 if they do)
chronosync sync [--prefer local|remote]   # merge changes made on both sides
```

Every command that writes accepts `-n/--dry-run` to preview. Common options:

| Option | Meaning |
| --- | --- |
| `-c, --config FILE` | config file (default `./chronosync.toml`; TOML or `.json`) |
| `-d, --database FILE` | SQLite file (default `dev.db`) |
| `-s, --snapshot-dir DIR` | snapshot directory (default `.chronosync`) |
| `-x, --exclude TABLE` | skip a table; repeat for several |
| `--prefer {fail,local,remote}` | `sync` only: how to settle rows changed on both sides |

Config file keys: `database`, `snapshot_dir`, `exclude_tables`, `prefer`, `state_file`.
Command-line options override the config file.

Exit codes: `0` ok, `1` error, `2` unresolved sync conflicts, `3` `status` found differences.

Commit the snapshot directory and gitignore `.chronosync-state.json`. That file records your
last push/pull/sync and is what lets `sync` tell "I deleted this row" from "someone added it".

## How it works

- `push` and `pull` mirror one side onto the other: rows missing from the source are deleted from the target.
- A snapshot holds `manifest.json`, `schema/<table>.sql` and `data/<table>.jsonl` (rows sorted by primary key, keys sorted, LF newlines).
- Tables without a primary key are keyed by a hash of each row's content, so they sync as sets of rows.
- BLOB values are stored as `{"$blob": "<base64>"}`.
- `sync` does a three-way merge per row against the state saved at your last push/pull/sync: a change on one side wins, deletions propagate, and a row changed differently on both sides is a conflict.
- With conflicts and `--prefer fail` (the default) nothing is written; `--prefer local` or `remote` settles them.

## Limitations

- Only supports SQLite databases; other database engines are not currently supported.
- Does not handle automatic schema migrations; you must manage schema changes manually. `sync` refuses to merge a table whose columns differ between database and snapshot.
- Tables are held in memory while syncing, so very large databases are not a good fit.
- Tables removed from the database are not dropped by `pull`/`sync`; only rows are mirrored.

## Development

```bash
python -m venv .venv && . .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
python -m pytest -q
ruff check .
```

## License

MIT -- see [LICENSE](LICENSE).
