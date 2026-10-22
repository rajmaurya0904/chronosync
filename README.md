# ChronoSync

**A lightweight CLI tool to bidirectionally synchronize local development database states and test fixtures across team members without dumping heavy files into git.**

ChronoSync solves the pain of sharing database states and test fixtures among developers. Instead of committing bulky dumps to git, it lets you push and pull a lightweight snapshot of your local data, keeping the repository clean and ensuring every team member works with the same baseline.

## Example

<!-- A real command and its REAL pasted output. Run it first. -->

## Install

```bash
pip install -e ".[dev]"
```

## Usage

<!-- The 2-4 commands people actually need, one line each. -->

## How it works

<!-- 3-6 bullets: what it checks, computes or produces. -->

## Limitations

<!-- Honest and short: what it does NOT do, known gaps. -->

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

## License

MIT -- see [LICENSE](LICENSE).
