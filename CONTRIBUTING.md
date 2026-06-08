# Contributing

Thanks for your interest in contributing to Jellyfin Auto Groupings! 🎉

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR-USERNAME/jellyfin-auto-groupings.git`
3. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
4. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   pre-commit install
   ```

## Development Workflow

### Code Style

This project uses **ruff** for both linting and formatting.

```bash
# Check for lint issues
ruff check .

# Auto-fix where possible
ruff check --fix .

# Format code
ruff format .
```

### Type Checking

We use **mypy** for static type analysis:

```bash
mypy .
```

### Testing

```bash
# Run the full test suite
python -m pytest

# Run with coverage
python -m pytest --cov=.

# Run a specific test file
python -m pytest tests/test_network.py -v

# Skip slow external tests
python -m pytest -m "not exhaustive" tests/
```

### Commit Structure

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `fix:` — bug fixes or code corrections
- `feat:` — new features
- `chore:` — maintenance, formatting, tooling
- `docs:` — documentation changes
- `refactor:` — code restructuring without behaviour change
- `test:` — adding or modifying tests
- `style:` — formatting-only changes

## Pull Request Process

1. Create a branch from `main` with a descriptive name:
   - `fix/` — bug fixes
   - `feat/` — new features
   - `docs/` — documentation
   - `test/` — test improvements
2. Make your changes, keeping them focused on one concern
3. Ensure tests pass: `python -m pytest`
4. Ensure linting passes: `ruff check . && ruff format --check .`
5. Ensure type checking passes: `mypy .`
6. Open a PR against `main` with a clear title and description

### PR Checklist

- [ ] Tests pass
- [ ] No new ruff/mypy warnings
- [ ] Changes are focused on a single purpose
- [ ] Commit messages follow conventional commits
- [ ] Documentation updated if applicable

## Project Structure

```
jellyfin-auto-groupings/
├── app.py              # Flask application entrypoint
├── config.py           # Configuration management
├── jellyfin.py         # Jellyfin API client helpers
├── network.py          # Retry-aware HTTP helpers
├── routes.py           # Flask route definitions
├── scheduler.py        # Background task scheduling
├── sync.py             # Core sync logic
├── static/             # Frontend assets (CSS, JS)
├── templates/          # Jinja2 templates
├── tests/              # Test suite
└── Dockerfile          # Container build
```

## Questions?

Open an issue or start a discussion on GitHub.