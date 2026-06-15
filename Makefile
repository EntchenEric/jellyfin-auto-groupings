.PHONY: install install-dev test test-all test-cov test-to-file lint format-check typecheck clean format run virtual-jellyfin docker-build docker-run

# ── Installation ────────────────────────────────────────────────────────────

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

# ── Testing ─────────────────────────────────────────────────────────────────

# PYTEST_ARGS can be overridden to add/remove flags e.g.: make test PYTEST_ARGS="-v"
# The -q flag reduces pytest verbosity; remove it for full output during debugging.
PYTEST_ARGS ?= -q

test:
	python3 -m pytest -x $(PYTEST_ARGS) --ignore=tests/test_deep_sync.py

test-all:
	python3 -m pytest $(PYTEST_ARGS)

test-cov:
	python3 -m pytest $(PYTEST_ARGS) --cov=. --cov-report=term-missing

test-fast:
	python3 -m pytest -x $(PYTEST_ARGS) -m "not exhaustive and not e2e" \
		--ignore=tests/test_deep_sync.py \
		--ignore=tests/test_virtual_jellyfin_exhaustive.py \
		--ignore=tests/test_e2e \
		tests/test_config.py tests/test_cleanup.py tests/test_scheduler.py tests/test_network.py tests/test_sync.py

test-to-file:
	python3 run_tests_to_file.py

# ── Linting & Type Checking ─────────────────────────────────────────────────

lint:
	ruff check .
	ruff format --check .

format-check:
	ruff format --check .

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
	python3 app.py

virtual-jellyfin:
	python3 start_virtual_jellyfin.py

# ── Docker ──────────────────────────────────────────────────────────────────

docker-build:
	docker build -t jellyfin-groupings .

docker-run:
	docker run -p 5000:5000 jellyfin-groupings