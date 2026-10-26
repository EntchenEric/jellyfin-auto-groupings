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
- **`_sort_items_in_memory`** — in-memory sort by Rating, Year, Name, etc. for
  external-list sources, which Jellyfin cannot order server-side. It tolerates
  the shapes Jellyfin actually returns (numeric or numeric-string years,
  `null` ratings, missing fields), applies the tie-break key from `SORT_MAP`
  (so same-year titles come out in name order), and shuffles for `Random`.
  Items missing the sort field always sort last, in either direction.
- **`parse_complex_query`** — parses compound rules like
  `Action AND NOT Comedy OR Drama` into structured rule dictionaries.
  Operators are only recognised as standalone words, so a value such as
  `Andor` is never split. A leading or trailing operator is dropped instead of
  becoming a filter value, stacked operators collapse to the one nearest the
  operand, and stacked `NOT`s toggle (`NOT NOT Comedy` is just `Comedy`).
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
expected exception types after all retries are exhausted: a read timeout
becomes `requests.Timeout`, a handshake timeout stays a
`requests.ConnectionError` with "Connection timed out.". A
`NewConnectionError` (refused port, unresolvable host) is re-raised
unchanged, because urllib3 derives it from `ConnectTimeoutError` and
relabelling it would hide the host and the `errno` from the caller.

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

Every outbound request passes an explicit `timeout=`. `requests` has no
default timeout, so an omitted value made a stalled Jellyfin server block the
caller indefinitely rather than raising an error the sync layer could log and
move past. The same rule applies to the legacy `JellyfinGroupings` client in
`jellyfin_groupings/main.py`, which takes a `timeout` argument (default 30
seconds).

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

### Run lock

`sync.sync_run_guard()` serialises every run that writes to the target
directory: `POST /api/sync`, `POST /api/cleanup`, and the three scheduled jobs.
It combines an in-process `threading.Lock` with an exclusive `flock` on
`<config dir>/sync.lock`, because gunicorn runs several worker *processes*
(two by default) and each would otherwise hold its own unrelated lock.

This matters because each group directory is cleared and then refilled one
symlink at a time. Two overlapping runs therefore delete each other's links
mid-flight, leaving the directory with an arbitrary mix of both runs and a
reported count that does not describe what is on disk. A run that cannot take
the lock within `SYNC_LOCK_TIMEOUT` raises `SyncBusyError`; the HTTP routes
answer `409`, and the scheduler logs a skip instead of queueing an unbounded
backlog behind a long run. Dry runs write nothing, so they take no lock.

### Frontend (`static/js/`)

Modular JavaScript (ES modules, no bundler):

| Module | Responsibility |
|--------|---------------|
| `core/api.js` | AJAX/`fetch` wrappers for all backend endpoints |
| `core/state.js` | Global application state and constants |
| `core/ui.js` | DOM helpers, toast notifications, loading overlays, modal lifecycle and the confirmation dialog |
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

A seasonal group is bounded by `seasonal_start` / `seasonal_end` in `MM-DD`
form. The window is inclusive of the start and exclusive of the end, and may
cross a year boundary (`12-01` to `01-01`). Dates are validated against a
real calendar when the config is saved: an unparseable window is treated as
"always in season", so it would never be cleaned up.
- **Scheduler** — global schedule, cleanup schedule, exclusion list

Environment variables can override sensitive values at runtime without
persisting them to disk.

## Testing

Tests use `pytest` with mocking for external HTTP calls.  The CI pipeline
enforces a coverage ratchet baseline (`--cov-fail-under=46`, raised as
coverage improves).  A virtual Jellyfin mock server
(`start_virtual_jellyfin.py`) is available for integration testing without
a real Jellyfin instance.

For detailed test descriptions and how to run them, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Accessibility

The dashboard is server-rendered from Jinja partials in `templates/`, so a
control without an accessible name still renders and still passes every
behavioural test — the regression is invisible until someone uses a screen
reader. `tests/test_template_accessibility.py` parses the partials directly
and fails when:

- an `<input>` / `<select>` / `<textarea>` has no accessible name. Give it a
  wrapping `<label>`, a `<label for="...">`, or an `aria-label` (the last is
  correct for a control whose visible context already names it, such as the
  file picker behind a styled button).
- an inline `<svg>` icon is not marked `aria-hidden="true"`. Icons next to a
  text label are decorative; leaving them exposed makes a screen reader
  announce an unnamed graphic before every button label.
- a `<label for="...">` points at an id that no longer exists, in which case
  the label is silently dropped from the accessibility tree.

Labels that only exist for assistive technology use the `.sr-only` class from
`static/css/components.css` rather than being omitted; a visually implied
label (the day dropdown beside a month dropdown) still needs a name.