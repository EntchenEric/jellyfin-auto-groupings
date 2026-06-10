.PHONY: install dev install-dev test test-all test-cov lint typecheck clean format run virtual-jellyfin docs

# ── Installation ────────────────────────────────────────────────────────────

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

# ── Testing ─────────────────────────────────────────────────────────────────

test:
	python -m pytest -x -q --ignore=tests/test_deep_sync.py

test-all:
	python -m pytest

test-cov:
	python -m pytest --cov=. --cov-report=term-missing

# ── Linting & Type Checking ─────────────────────────────────────────────────

lint:
	ruff check .

typecheck:
	mypy .

# ── Code Quality ────────────────────────────────────────────────────────────

format:
	ruff format .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage

# ── Development ──────────────────────────────────────────────────────────────

run:
	python app.py

virtual-jellyfin:
	python start_virtual_jellyfin.py

# ── Docker ──────────────────────────────────────────────────────────────────

docker-build:
	docker build -t jellyfin-groupings .

docker-run:
	docker run -p 5000:5000 jellyfin-groupings