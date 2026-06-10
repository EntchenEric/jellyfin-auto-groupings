# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial CHANGELOG.md for project tracking.
- Added `anilist_api_url` to `DEFAULT_CONFIG` to prevent KeyError when config
  is accessed before the key is explicitly set.
- Documented `NETWORK_RETRY_*` environment variables in the README env vars table
  and added them to `.env.example` and `docker-compose.yml` for discoverability.

### Fixed
- Improved CSRF testing check in `routes.py` to use the standard Flask
  `current_app.config.get("TESTING")` pattern instead of `current_app.testing`.
- Better type handling for seasonal start/end strings in `_is_in_season` when
  passed non-string types (already handled gracefully as a fallback).
- Fixed double-checked locking pattern in `_fetch_full_library()` so the cache
  is not overwritten if another thread populated it during the fetch.

### Changed
- Standardised README example commands to use `python3` for consistency with
  system defaults.
- Healthcheck in `docker-compose.yml` uses `python3` for consistency.
- Updated README Docker environment example to include `NETWORK_RETRY_*` vars.
- Fixed output path in `run_tests_to_file.py` to use absolute repo-root path.
- Moved `_SOURCE_DISPATCH` routing from a module-level dict of lambdas to a
  `match/case`-based `_dispatch_list_source` function, removing the unused
  dispatch table.
- Renamed `_LIST_SOURCES` to `_LIST_SOURCE_TYPES` and added
  `_COMPLEX_QUERY_SOURCE_TYPES` for more descriptive naming.
- Removed redundant cache clear at end of `run_sync` (the cache is already
  cleared at the start of each sync run).
- Mypy type fixes in `tests/virtual_jellyfin.py` dashboard helper.

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