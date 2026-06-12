# Architecture

This document describes the high-level architecture of Jellyfin Groupings.

## Overview

Jellyfin Groupings is a Flask web application that creates **virtual Jellyfin
libraries** without duplicating media files.  It does this by grouping existing
media into directories filled with **symbolic links (symlinks)** back to the
original files.  These directories are then added to Jellyfin as independent
libraries.

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────────┐
│   Frontend   │────▶│   Flask Routes   │────▶│   Sync Engine     │
│  (JS/HTML)   │◀────│  (routes.py)     │◀────│   (sync.py)       │
└──────────────┘     └────────┬─────────┘     └────────┬──────────┘
                              │                         │
                              ▼                         ▼
                     ┌────────────────┐       ┌──────────────────┐
                     │   Config       │       │   Fetchers       │
                     │  (config.py)   │       │  (imdb.py,       │
                     └────────────────┘       │   trakt.py,      │
                                              │   tmdb.py, …)    │
                                              └──────────────────┘
```

## Component Breakdown

### `app.py` — Application Entry Point

Creates and configures the Flask application, sets up logging (console +
rotating file handler), registers the blueprint from `routes.py`, and starts
the background scheduler.  When run directly (`python3 app.py`) it starts the
development server.

### `routes.py` — HTTP Route Handlers

A Flask Blueprint containing all HTTP endpoints:

- **Configuration CRUD** — load, save, validate config (`/api/config`, etc.)
- **Sync operations** — trigger sync, dry-run preview, cleanup broken symlinks
- **Metadata browsing** — fetch genres, actors, studios, tags from Jellyfin
- **Jellyfin proxy** — collections, libraries, virtual folders, health checks
- **Filesystem browser** — auto-detect path mappings by scanning mounted volumes
- **Cover upload & management** — upload, list, rotate cover images
- **Export/Import** — JSON export and import of the full configuration
- **Wizard** — guided setup endpoint

Route handlers are intentionally thin: they validate inputs, delegate to
service functions, and serialise the result back as JSON.

### `config.py` — Configuration Persistence

Handles loading and saving `config/config.json` (never committed — it may
contain API keys).  Includes:

- **Default values** — forward-compatible key filling
- **Legacy key migration** — `jellyfin_root` → `media_path_in_jellyfin`, etc.
- **Environment variable overrides** — sensitive values can be set via env vars

### `sync.py` — Core Synchronisation Engine

The heart of the application.  `run_sync()` is the main entry point:

1. Loads configuration and validates required keys (URL, API key, target path).
2. Iterates over configured groups and delegates to `_process_group()`.
3. For each group:
   - Resolves items from the source (IMDb list, Trakt list, Jellyfin metadata
     filter, complex compound query, etc.).
   - Optionally translates Jellyfin-side paths to host-side paths.
   - Creates (or clears and re-creates) symlinks in the group directory.
   - Optionally creates a Jellyfin collection (boxset) instead of symlinks.
   - Optionally auto-creates a Jellyfin virtual library for the group.
   - Handles seasonal groups (out-of-season groups are cleaned up).

Key helpers:

- **`_match_jellyfin_items_by_provider`** — match external IDs against the
  full Jellyfin library index for O(1) lookups (supports IMDb, TMDb, etc.)
- **`_fetch_full_library`** — double-checked locking cache to avoid redundant
  Jellyfin library fetches when multiple groups share the same server
- **`_sort_items_in_memory`** — in-memory sort by Rating, Year, Name, etc.
- **`parse_complex_query`** — parses compound rules like
  `Action AND NOT Comedy OR Drama` into structured rule dictionaries
- **`preview_group`** — dry-run preview for a single group
- **`run_cleanup_broken_symlinks`** — scans for and removes broken symlinks

### `network.py` — Retry-Aware HTTP Client

Provides explicit `get()` / `post()` / `put()` / `delete()` / `patch()`
helpers that use a shared `requests.Session` configured with exponential
backoff retry on transient failures (5xx, connection errors).  Configured
via environment variables:

- `NETWORK_RETRY_TOTAL` (default `3`)
- `NETWORK_RETRY_BACKOFF_FACTOR` (default `1.0`)
- `NETWORK_RETRY_STATUS_FORCELIST` (default `429,500,502,503,504`)

Properly re-raises `ReadTimeoutError` and `ConnectTimeoutError` as the
expected exception types after all retries are exhausted.

### `jellyfin.py` — Jellyfin API Client

Lower-level HTTP helpers for interacting with the Jellyfin API:

- Authentication (`X-Emby-Token` header)
- JSON response parsing and error handling
- Pagination support (`_paginate_jellyfin`)
- Media item fetching with flexible filters
- Collection CRUD (create, find by name, set images, add items)
- Virtual folder CRUD (create, delete, list, set images)
- Library listing, user listing, recent item fetching
- Sort-order mapping from friendly names to Jellyfin API values

### External List Fetchers

Each fetcher module follows the same pattern: fetch IDs from an external
service and return them as a simple list (string IDs or integer IDs).

| Module | Source | IDs returned |
|--------|--------|-------------|
| `imdb.py` | IMDb list HTML scraping | `tt…` IMDb IDs |
| `trakt.py` | Trakt v2 API | `tt…` IMDb IDs |
| `letterboxd.py` | Letterboxd list HTML scraping | IMDb or TMDb IDs |
| `tmdb.py` | TMDb v3 API | TMDb numeric IDs |
| `tmdb.py` (`get_tmdb_recommendations`) | TMDb recommendations API | TMDb numeric IDs (sorted by score) |
| `anilist.py` | AniList GraphQL API | AniList numeric IDs |
| `mal.py` | MyAnimeList v2 REST API | MAL numeric IDs |

### `scheduler.py` — Background Job Scheduler

Uses APScheduler's `BackgroundScheduler` to run sync and cleanup jobs
according to cron expressions:

- **Global sync** — syncs all non-excluded groups
- **Per-group sync** — individual groups on their own schedule
- **Cleanup** — removes broken symlinks on a schedule

### Frontend (`static/js/`)

Modular JavaScript (ES modules, no bundler):

| Module | Responsibility |
|--------|---------------|
| `core/api.js` | AJAX/`fetch` wrappers for all backend endpoints |
| `core/state.js` | Global application state and constants |
| `core/ui.js` | DOM helpers, toast notifications, loading overlays, modal management |
| `app.js` | Bootstrap, keyboard shortcuts, topbar buttons, form wiring |
| `features/config.js` | Server settings, scheduler toggles, config CRUD |
| `features/groupings.js` | Group CRUD, card rendering, search, global exclusion UI |
| `features/metadata.js` | Metadata type options, source value UI, preview fetches |
| `features/sync.js` | Sync execution, result display, confirmation dialog |
| `features/wizard.js` | Step-by-step setup wizard |
| `features/export-import.js` | Config export/import |
| `features/cover-generator.js` | Cover image upload and management |
| `features/cleanup.js` | Broken symlink cleanup |
| `features/path-picker.js` | Filesystem path browser |
| `features/sidebar-resizer.js` | Draggable sidebar resize |
| `features/test-connection.js` | Connection test utility |

## Data Flow — A Sync Run

```
1. User clicks "Sync" (or scheduler triggers)
2. routes.py receives POST /api/sync
3. route handler calls run_sync(config)
4. run_sync() iterates groups:
   a. For metadata groups: fetch_jellyfin_items() with genre/actor/etc filter
   b. For complex queries: parse_complex_query() → _fetch_items_for_complex_group()
   c. For external lists: fetch_imdb_list()/fetch_trakt_list()/etc →
      _match_jellyfin_items_by_provider() to match IDs against library
   d. For recommendations: match items → get_tmdb_recommendations() →
      match again
5. Items are optionally sorted in memory
6. Symlinks are created in target_path/{group_name}/
7. Results are returned to the route handler → JSON response
```

## Configuration

The single source of truth is `config/config.json`, a JSON file with:

- **Server settings** — Jellyfin URL, API key, path mappings
- **Groups** — array of group definitions (source, sort, schedule, seasonality)
- **Scheduler** — global schedule, cleanup schedule, exclusion list

Environment variables can override sensitive values at runtime without
persisting them to disk.

## Testing

Tests use `pytest` with mocking for external HTTP calls.  The CI pipeline
requires 100% code coverage (`--cov-fail-under=100`).  A virtual Jellyfin
mock server (`start_virtual_jellyfin.py`) is available for integration
testing without a real Jellyfin instance.

For detailed test descriptions and how to run them, see [CONTRIBUTING.md](../CONTRIBUTING.md).