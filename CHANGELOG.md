# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Dockerfile`: enable gunicorn access and error logging (`--access-logfile -`
  and `--error-logfile -`) for container observability via `docker logs`. (PR #554)
- `variables.css`: add `color-scheme: dark` / `color-scheme: light` declarations
  for proper native form control styling in both themes. (PR #554)
- CSS custom property system for z-index layers (`--z-content`, `--z-toast`,
  `--z-modal`, `--z-loading-overlay`, `--z-wizard`, `--z-skip-link`)
  in `variables.css` to centralise stacking context. All hardcoded z-index
  values across CSS files now reference these variables for maintainability.
- `variables.css`: add `--z-locked-overlay` custom property (value `10`)
  for the lock-section overlay badge. (PR #549)
- `Makefile`: add configurable `PYTEST_ARGS` variable (default `-q`) so
  callers can override pytest verbosity (e.g. `make test PYTEST_ARGS="-v"`)
  without editing the Makefile. (PR #557)
- `Makefile` and `README.md`: apply `PYTEST_ARGS` to `test-all` and
  `test-cov` targets for consistency, add `.env.example` & pre-commit hooks
  to dev setup docs, and document `PYTEST_ARGS` override tip. (PR #558)

### Changed

- `run_tests_to_file.py`: print subprocess exit code after test run completes.
  (PR #554)
- `static/css/components.css`: replace hardcoded `z-index: 10` on
  `.locked-overlay-text` with `var(--z-locked-overlay)`. (PR #549)
- `README.md`: update test count from "650+" to exact "650".
- `static/js/app.js`: keyboard shortcut modal detection now uses
  `getComputedStyle` instead of fragile `[style*=]` CSS attribute selector,
  making it resilient to style-attribute changes.

- `.env.example`: add comment noting `NETWORK_RETRY_TOTAL=0` to disable
  retries entirely. (PR #554)
- `tests/test_routes_uncovered.py`: 12 new direct unit tests for
  `_validate_cron_expressions` covering all valid/invalid cron patterns
  (global schedule, cleanup schedule, group schedule, disabled groups).
  (PR #535)
- `README.md`: update test count from 642+ to 650+. (PR #535)
- `static/js/app.js`: add <kbd>R</kbd> keyboard shortcut to reload the
  groups list without a full page refresh.
- Closed stale PR #545 — already merged into main.

### Fixed

- `network.py`: guard against NaN/Inf `NETWORK_RETRY_BACKOFF_FACTOR` values
  that parses as valid ``float`` but produce unusable retry behaviour.
- `anilist.py`: add missing ``from typing import Any`` import to fix ruff
  F821 undefined-name error.
- `network.py`: fix incorrect ``cast("requests.Session", ...)`` on bound
  method — the ``getattr`` result is a ``Callable``, not a ``Session``, which
  fixes the mypy ``operator`` error. (PR #538)

### Added

- `tests/test_network.py`: add tests for NaN, +Inf, and -Inf backoff factor
  fallback values.
- `static/js/core/state.js`: add ``recommendations_list_order`` display label.
- `templates/partials/main/groupings.html`: add ``recommendations_list_order``
  sort-order dropdown option.
- `routes.py`: add type validation for config fields (`api_key`, `anilist_api_url`,
  `trakt_client_id`, `tmdb_api_key`, `mal_client_id`) and group-level fields
  (`source_type`, `source_value`, `sort_order`, `watch_state`, `schedule`,
  `schedule_enabled`, `seasonal_enabled`, `create_as_collection`, `seasonal_start`,
  `seasonal_end`, `rules`). Validate `jellyfin_url` format (must start with
  `http://` or `https://`). Check file in mount-point directory before pruning
  subdirectories during filesystem search.
- `tests/test_routes_uncovered.py`: 18 new tests covering config type validation
  edge cases (group boolean fields, seasonal date format, rules structure,
  jellyfin_url format).
- `tests/test_routes.py`: 2 new mount-point edge-case tests for
  `_search_local_filesystem` in mount-point directories.
- `.github/CODEOWNERS`: add default code owner (`@entcheneric`).

### Changed

- (empty)

### Added

- `tests/test_sync_uncovered.py`: add `test_build_letterboxd_items_unmatched_id_skipped`
  to cover the `continue` branch when `_match_letterboxd_id` returns `None`.

### Fixed

- `sync.py`: fix `_build_letterboxd_items` docstring — dedup description was
  incorrectly scoped to `letterboxd_list_order` only; dedup applies to all
  sort orders.

### Changed

- `README.md`: update test count from 598+ to 608+.

### Added

- `tmdb.py`: add O(1) dedup set in `fetch_tmdb_list` for defensive duplicate filtering.
- Dockerfile: add `--preload` to gunicorn CMD for memory sharing between workers.
- Dockerfile: increase healthcheck `--start-period` from 10s to 15s for slower gunicorn boot times.
- `anilist.py`: validate user-provided AniList list status against known values; unknown statuses now raise `ValueError` with valid options in the message.
- `routes.py`: add `_ALLOWED_NON_CSRF_REQUESTS` frozenset so endpoints can opt out of the CSRF `X-Requested-With` check (for non-browser clients).
- `tests/test_external.py`: add tests for `_resolve_anilist_status` — valid, invalid, and parametrized invalid values.
- `tests/test_routes.py`: add test confirming CSRF-exempted endpoints can POST without the required header.
- `routes.py`: add `ALLOWED_NON_CSRF_ENDPOINTS` env var support to configure CSRF-exempt endpoints at process start.
- `.env.example`: document the `ALLOWED_NON_CSRF_ENDPOINTS` env var under a new CSRF/Security section.
- `README.md`: document `ALLOWED_NON_CSRF_ENDPOINTS` in env vars table and Docker compose snippet.
- `tests/test_routes.py`: add test verifying env-var parsing populates `_ALLOWED_NON_CSRF_REQUESTS` correctly.
- `.gitignore` now excludes `.ruff_cache/`, `.coverage`, and `htmlcov/`.
- `pyproject.toml` now includes a `[tool.ruff.format]` section with explicit
  quote-style, indent-style, and line-ending settings.

### Changed

- `docker-compose.yml`: sync healthcheck `start_period` from 10s → 15s to match the Dockerfile.
- Dockerfile: remove `requirements-dev.txt` copy from builder stage (unused in production).
- `routes.py`: extract CSRF-mutating method check into `_CSRF_MUTATING_METHODS`
  module-level tuple to avoid re-creating the tuple on every request.
- `routes.py`: use walrus operator in `_ALLOWED_NON_CSRF_REQUESTS` frozenset
  to avoid calling `strip()` twice per env-var element.
- `Makefile`: add `test-to-file` target wrapping `run_tests_to_file.py` for
  developer convenience.
- `pyproject.toml` ruff lint config reverted from `select`/`ignore` back to
  `extend-select`/`extend-ignore`. The change was reverted because `select`
  overrides Ruff's default rule sets (E, F, W, etc.), while `extend-select`
  adds custom rules on top of defaults. `extend-ignore` remains the correct
  key for suppressing rules; `extend-ignore`/`select` were never deprecated.
- `scheduler.py` `validate_cron` docstring: removed skipped doctest examples
  that were never executed.
- `letterboxd.py` `_extract_ids_from_list_page`: removed unnecessary
  `re.DOTALL` flags from single-line regex patterns.
- `ANILIST_API_URL` environment variable example in `docker-compose.yml`.
- Tests for `_fill_defaults` resilience when `scheduler` is `null` or a non-dict
  value in the stored config.
- Documented Makefile targets in README.md (test, lint, typecheck, run, format, etc.)
  for contributor discoverability.
- Initial CHANGELOG.md for project tracking.
- Added `anilist_api_url` to `DEFAULT_CONFIG` to prevent KeyError when config
  is accessed before the key is explicitly set.
- Documented `NETWORK_RETRY_*` environment variables in the README env vars table
  and added them to `.env.example` and `docker-compose.yml` for discoverability.
- Add test coverage for `/api/health` endpoint (configured and unconfigured cases)
  via PR #494.
- Added SVG favicon (`🎬` emoji) to base template for better browser tabs.
- Print-friendly stylesheet with hidden UI chrome, expanded link URLs, and
  readable code blocks when printing docs/setup guides.
- `network.py` now gracefully falls back to default retry settings when
  environment variables contain invalid values (previously raised `ValueError`
  at module import time).
- `sync.py` logs a warning when the config contains no groups to sync.
- `scheduler.py` now logs warnings when a group with `schedule_enabled` is
  missing a name or has a non-string name.
- Path-traversal protection in `routes.py` `_delete_folder`: rejects names
  with path separators and validates the resolved path stays within the
  target base directory.
- `config.py` `_fill_defaults` now recursively populates nested defaults
  (e.g. scheduler sub-keys) instead of only one level deep.
- Added tests for the new code paths:
  - `test_parse_retry_config_module_level_fallback` covers the `ValueError`
    fallback in `network.py` at module import time.
  - `test_delete_folder_invalid_name` covers invalid folder name rejection
    in `_delete_folder`.
  - `test_delete_folder_path_traversal_via_symlink` covers the path-traversal
    detection via symlink resolution.
  - `test_delete_folder_resolve_oserror` covers OSError from `Path.resolve()`.
  - `test_search_filesystem_ismount_oserror` covers OSError from
    `os.path.ismount()` in `_search_local_filesystem`.
- Robust containment check in `routes.py` `_delete_folder` using
  `resolved.relative_to(base_resolved)` instead of substring matching.
- `config.py` `_fill_defaults` now uses `copy.deepcopy` for missing nested
  keys via membership check, eliminating aliasing with `DEFAULT_CONFIG`.
- Scrollbar thumb colors now use `color-mix(in srgb, var(--text-secondary) …%,
  transparent)` instead of hardcoded `rgba(255,255,255,…)` — adapts correctly
  in light theme.
- `#topbar` and `#sidebar::-webkit-scrollbar-thumb` backgrounds use
  `color-mix()` with theme variables for light-mode compatibility.
- Footer color uses `var(--text-secondary)` with `opacity` instead of hardcoded
  `rgba(148, 163, 184, 0.45)`.
- `.pre-commit-config.yaml` splits ruff into `ruff-lint` and `ruff-format`
  hooks to match `make lint` target.
- Removed deprecated `page-break-*` CSS properties (courtesy of CodeRabbit
  review) — using modern `break-*` equivalents only.
- Improved `network.py` error logging to include the actual invalid value when
  `NETWORK_RETRY_TOTAL` or `NETWORK_RETRY_BACKOFF_FACTOR` fails to parse.
- Stricter `_handle_http_error` signature in `routes.py` to accept `HTTPException`
  instead of the generic `Exception`, eliminating a dead re-raise branch.
- Explicit type annotation for `_scheduler` in `scheduler.py`.
- `_prepare_group_directory` now resolves the cover path even during dry runs,
  so callers can access `source_cover` for preview purposes regardless of mode.
- Merged PR #496: Add Makefile for common dev commands; address CodeRabbit review
  comments.
- Fixed `.PHONY` declaration in Makefile to match actual targets (removed `dev`/`docs`,
  added `docker-build`/`docker-run`).
- Simplified `_parse_mmdd` in sync.py by removing redundant `day <= 0` check
  (already covered by `calendar.monthrange` validation).
- Standardised README example commands to use `python3` for consistency with
  system defaults.
- Healthcheck in `docker-compose.yml` uses `python3` for consistency.
- Updated README Docker environment example to include `NETWORK_RETRY_*` vars.
- Fixed output path in `run_tests_to_file.py` to use absolute repo-root path.
- Added PUT and PATCH method support to `_request_or_raise` in jellyfin.py
  (future-proofing — network.py already provides retry-aware helpers for these).
- Achieved 100% code coverage across all 12 source modules (1881/1881 lines).
- Moved `_SOURCE_DISPATCH` routing from a module-level dict of lambdas to a
  `match/case`-based `_dispatch_list_source` function, removing the unused
  dispatch table.
- Renamed `_LIST_SOURCES` to `_LIST_SOURCE_TYPES` and added
  `_COMPLEX_QUERY_SOURCE_TYPES` for more descriptive naming.
- Removed redundant cache clear at end of `run_sync` (the cache is already
  cleared at the start of each sync run).
- Mypy type fixes in `tests/virtual_jellyfin.py` dashboard helper.
- Fixed CONTRIBUTING.md to remove `-n auto` flag from the recommended test
  command, since `pytest-xdist` is not included in dev dependencies.
- Removed unnecessary single quotes from font-family declarations in CSS
  (Inter, Outfit, JetBrains Mono) for valid CSS identifier syntax.
- Fixed `currentcolor` typo → `currentColor` in `responsive.css` high-contrast
  media query for standards compliance.
- `letterboxd.py` `_extract_ids_from_list_page`: DRY three similar regex loops
  into a single `_ID_LIST_PAGE_PATTERNS` list with documented priority ordering.
- `config.py` `_fill_defaults`: replace `elif not isinstance(current, dict)` with
  plain `else` (the missing-key case is already handled by the prior membership
  check).
- `scheduler.py` `validate_cron`: call `expr.strip()` once instead of twice.

### Fixed

- Fixed `_search_local_filesystem` returning `None` on timeout/file-limit
  instead of continuing to the next search root (prevents unbounded filesystem
  scanning after the limit is reached).
- Fixed `_build_letterboxd_items` deduplication: both branches (priority and
  list-order) now use a shared `seen_jf_ids` set to prevent duplicate symlinks
  when a Letterboxd entry matches both IMDb and TMDb provider IDs.
- Fixed `_fill_defaults` in `config.py` to use `copy.deepcopy` for nested
  default dicts instead of `dict.copy()`, preventing shallow-copy issues
  and aliasing with `DEFAULT_CONFIG`.
- Fixed order-dependent `test_clear_library_cache` test in `test_sync_more_edges.py`
  by clearing the module-level cache before populating it.
- Improved CSRF testing check in `routes.py` to use the standard Flask
  `current_app.config.get("TESTING")` pattern instead of `current_app.testing`.
- Better type handling for seasonal start/end strings in `_is_in_season` when
  passed non-string types (already handled gracefully as a fallback).
- Fixed double-checked locking pattern in `_fetch_full_library()` so the cache
  is not overwritten if another thread populated it during the fetch.

## [1.0.0] - 2025-03-01

### Added

- Initial release of Jellyfin Groupings.
- Metadata-based groups (genre, actor, studio, tag, year).
- External list support (IMDb, Trakt, TMDb, Letterboxd, AniList, MyAnimeList).
- Complex query logic with AND, OR, and NOT operators.
- Smart sorting with numeric prefixes.
- Docker-first deployment.
- Auto-detect path mapping.
- Scheduler for automatic syncing and cleanup.
- Seasonal group support.
- Collection (Boxset) mode.
- 550+ tests with 100% coverage.
- REST API for programmatic use.
- Unraid Community Applications support.
