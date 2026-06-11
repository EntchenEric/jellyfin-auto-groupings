# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `.gitignore` now excludes `.ruff_cache/`, `.coverage`, and `htmlcov/`.
- `pyproject.toml` now includes a `[tool.ruff.format]` section with explicit
  quote-style, indent-style, and line-ending settings.

### Changed
- `pyproject.toml` ruff lint config updated from deprecated `extend-select`/
  `extend-ignore` to the current `select`/`ignore` keys.
- `scheduler.py` `validate_cron` docstring: removed skipped doctest examples
  that were never executed.
- `letterboxd.py` `_extract_ids_from_list_page`: removed unnecessary
  `re.DOTALL` flags from single-line regex patterns.

### Added
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

### Changed
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

### Fixed
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
