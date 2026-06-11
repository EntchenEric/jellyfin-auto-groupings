# Contributing to Jellyfin Groupings

Thank you for considering contributing! Here are a few guidelines to help things go smoothly.

## Getting Started

1. Fork the repository.
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/jellyfin-auto-groupings.git
   cd jellyfin-auto-groupings
   ```
3. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   make install-dev
   ```
4. Create a branch for your changes:
   ```bash
   git checkout -b my-feature-branch
   ```

## Development

### Code Style

- Python: Follow [PEP 8](https://peps.python.org/pep-0008/). The project uses `ruff` for linting and formatting.
- JavaScript: Follow standard ES module conventions. JS files are linted via `make lint` (Python-only `ruff` is used for Python; JS currently has no separate linter configured).
- Run linting and format-checking before committing:
  ```bash
  make lint
  ```

### Type Hints

All Python code should use type hints. The project targets Python 3.11+.

### Running Tests and Coverage

- Tests live in the `tests/` directory and use `pytest`.
- Run tests before opening a PR:
  ```bash
  pytest
  ```
- The project requires 100% code coverage (CI uses `--cov-fail-under=100`). New features must include tests.
- Run individual test files during development:
  ```bash
  pytest tests/test_sync.py -v
  ```
- Run type checking before opening a PR:
  ```bash
  mypy .
  ```

### Using the Virtual Jellyfin Server

For development without a real Jellyfin instance, you can run a mock Jellyfin server:

```bash
python3 start_virtual_jellyfin.py
```

Then configure Jellyfin Groupings to use `http://localhost:8096` as the server URL with any API key.

### Linting and Formatting

Before committing, run:

```bash
make lint
```

To auto-format code:

```bash
make format
```

### Running Locally

```bash
python3 app.py
```

The app will be available at `http://localhost:5000`.

## Making Changes

### Priority Order

When making improvements, consider this priority:

1. **Fix bugs** — Open issues on GitHub take highest priority.
2. **Merge PRs** — Review and merge open pull requests.
3. **Documentation** — Improve README, add docstrings, clarify comments.
4. **Code optimization** — Performance, type hints, error handling, edge cases.
5. **Tests** — Unit tests, integration tests, edge cases, coverage.
6. **UI/UX** — CSS improvements, responsive design, accessibility, dark mode.
7. **Refactoring** — Clean up technical debt, split large files, improve structure.

### Commit Messages

Write clear, concise commit messages:

```
component: Brief description of the change

Optional longer explanation of why the change was made and
what it affects.
```

Examples:
- `docker: Add healthcheck timeout to prevent hung probes`
- `docs: Add CONTRIBUTING.md with development guidelines`
- `tests: Add edge case for empty provider IDs in match_by_provider`

## Pull Request Process

1. Ensure your branch is up to date with `main`.
2. Run the full test suite and linting checks.
3. Update documentation if your change affects the public API or configuration.
4. Open a PR against the `main` branch with a clear title and description.
5. A maintainer will review your PR. Please be patient — we'll get to it!

## Reporting Issues

- Use the [GitHub issue tracker](https://github.com/entcheneric/jellyfin-auto-groupings/issues).
- Include steps to reproduce, expected behavior, and actual behavior.
- Include relevant logs (from `logs/jellyfin-groupings.log`) if applicable.
- Include your Jellyfin version and deployment method (Docker, native, etc.).

## Code of Conduct

Be respectful and constructive. We're all here to make something useful.
