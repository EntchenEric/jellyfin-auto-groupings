# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial CHANGELOG.md for project tracking.

### Fixed
- Improved CSRF testing check in `routes.py` to use the standard Flask
  `current_app.config.get("TESTING")` pattern instead of `current_app.testing`.
- Better type handling for seasonal start/end strings in `_is_in_season` when
  passed non-string types (already handled gracefully as a fallback).

### Changed
- Minor documentation improvements in README.md and docstrings.

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