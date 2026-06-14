# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- **Config persistence**: atomic writes via temp file + rename; corrupt `config.json` backed up to `.json.corrupt.bak` before falling back to defaults.
- **Config API**: sensitive keys (`api_key`, `trakt_client_id`, `tmdb_api_key`, `mal_client_id`) masked as `****` in `GET /api/config` responses.
- **Group validation**: duplicate names, empty names, invalid `source_type`, and a 200-group cap enforced on config save.
- **Sync concurrency**: sync and preview requests serialized with the scheduler lock to prevent overlapping runs.
- **Connection test**: SSRF mitigation blocks `test-server` requests to private, link-local, and loopback IP addresses.
- **Auto-detect paths**: suggested target path falls back to the current working directory when the home directory is not writable.
- **Error UX**: sync and API errors surfaced in a modal dialog; permission-denied symlink failures handled gracefully.

### Added

- **Health endpoint**: `GET /api/health` — uptime, Jellyfin configured flag, scheduler status.
- **Metrics endpoint**: `GET /api/metrics` — Prometheus-format counters for sync requests and uptime.
- **Config schema version**: `CONFIG_SCHEMA_VERSION` field in default config for forward compatibility.
