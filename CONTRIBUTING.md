# Contributing to Jellyfin Groupings

Thank you for your interest in contributing. This guide covers local setup, testing, and pull request expectations.

## Prerequisites

- Python 3.11 or 3.12 (see [README.md](README.md#python-version-support))
- Git

## Local setup

```bash
git clone https://github.com/entcheneric/jellyfin-groupings.git
cd jellyfin-groupings
pip install -e ".[dev]"
```

The editable install pulls runtime dependencies from `pyproject.toml` and dev tools (pytest, ruff, mypy, coverage plugins) from the `[dev]` extra.

## Pre-commit hooks

Install hooks once, then run them before pushing:

```bash
pre-commit install
pre-commit run --all-files
```

Hooks run **ruff**, **mypy**, and **pytest with 99% coverage** (see `.pre-commit-config.yaml`).

## Running tests

```bash
export PYTHONPATH=.
pytest tests/ -v
```

Useful variants:

```bash
pytest tests/ -v --cov=. --cov-report=term-missing
pytest tests/test_e2e/ -v -m e2e
python start_virtual_jellyfin.py
```

E2E tests require the stack in `e2e/` — see [README.md](README.md#end-to-end-tests).

## Code style

| Tool | Purpose | Command |
|------|---------|---------|
| [Ruff](https://docs.astral.sh/ruff/) | Linting and import sorting | `ruff check .` |
| [mypy](https://mypy.readthedocs.io/) | Static type checking | `mypy --ignore-missing-imports --exclude tests --exclude venv --exclude __pycache__ --exclude node_modules .` |

Configuration lives in `pyproject.toml`. Match existing patterns: thin route handlers, business logic in service modules (`sync.py`, `jellyfin.py`, etc.), minimal scope in PRs.

Do not add comments that merely restate what the code does.

## Pull request guidelines

1. **Branch** from `development` (or the branch named in open issues).
2. **Keep PRs focused** — one logical change per PR when possible.
3. **Run checks locally** — at minimum `pre-commit run --all-files` or `ruff check .`, `mypy …`, and `pytest`.
4. **Add or update tests** when fixing bugs or adding behavior that unit tests can cover.
5. **Update docs** if you change user-facing behavior, environment variables, or API routes.
6. **Describe the why** in the PR body: problem, approach, and how you tested.

CI runs ruff, mypy, and pytest on Python 3.11 and 3.12 (see `.github/workflows/test.yml`).

## Questions

Open a [GitHub issue](https://github.com/entcheneric/jellyfin-groupings/issues) for bugs, feature ideas, or questions before large changes.
