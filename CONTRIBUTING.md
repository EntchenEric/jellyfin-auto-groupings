# Contributing to Jellyfin Groupings

Thanks for your interest! This is a small but active project, and contributions —
bug reports, feature ideas, docs, or code — are very welcome.

## Getting Started

1. **Fork** the repo on GitHub.
2. **Clone** your fork:
   ```bash
   git clone https://github.com/<your-username>/jellyfin-auto-groupings.git
   cd jellyfin-auto-groupings
   ```
3. **Set up** a development environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"
   ```
4. **Run tests** before making changes:
   ```bash
   python3 -m pytest -n auto --cov=. -m "not exhaustive"
   ```

## Code Style

- This project uses **Ruff** for linting and formatting. Run `ruff check .` and `ruff format .` before committing.
- **mypy** is used for static type checking: `mypy .`
- All Python 3.11+ features are fair game (pattern matching, `|` union syntax, etc.).

## Commit Convention

We follow **Conventional Commits**:

```
feat: add support for Plex lists
fix: handle empty API key gracefully
docs: update README with new env vars
refactor: extract path translation helper
test: add edge-case tests for _parse_mmdd
```

## Pull Request Process

1. Create a feature branch from `main`.
2. Make your changes — keep PRs focused on a single concern.
3. Update docs and tests if applicable.
4. Ensure `ruff check .`, `mypy .`, and `pytest` all pass.
5. Open the PR with a clear description of *what* and *why*.

## Testing

- All new logic should have corresponding unit tests.
- Tests use **pytest** with standard fixtures in `conftest.py`.
- A **virtual Jellyfin server** is available for integration tests:
  ```bash
  python3 start_virtual_jellyfin.py &
  python3 -m pytest tests/ -m "exhaustive"
  ```
- Coverage target is **100%**. Run `pytest --cov=. --cov-report=html` to check.

## Feature Requests & Bug Reports

Open a [GitHub issue](https://github.com/entcheneric/jellyfin-auto-groupings/issues) with:

- A clear title and description
- For bugs: your setup (Docker / native, Jellyfin version), steps to reproduce, and logs
- For features: the use case you're trying to solve

## Questions?

Feel free to open a [Discussion](https://github.com/entcheneric/jellyfin-auto-groupings/discussions) or tag `@entcheneric` in an issue.