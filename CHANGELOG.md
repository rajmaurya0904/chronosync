## [0.1.0] - 2025-01-24

- Initial release: SQLite snapshot sync with `push`, `pull`, `status` and `sync` commands
- Deterministic, git-friendly snapshot format (JSON lines per table)
- Three-way row merge with conflict detection and `--prefer local|remote`
- Config loading from TOML and JSON files
- Dry-run mode to preview changes before applying
