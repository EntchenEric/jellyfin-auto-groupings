# Jellyfin Groupings

<p align="center">
  <img src="jellyfin_groupings_banner.png" alt="Jellyfin Groupings Banner" width="800">
</p>

> **Virtual Libraries Simplified.** Create dynamic Jellyfin libraries using symlinks without duplicating your media.

[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg?logo=docker&logoColor=white)](https://github.com/entcheneric/jellyfin-auto-groupings)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Tests](https://github.com/EntchenEric/jellyfin-auto-groupings/actions/workflows/test.yml/badge.svg)](https://github.com/EntchenEric/jellyfin-auto-groupings/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://python.org)

---

## 📑 Table of Contents

- [✨ Features](#features)
- [🚀 Quick Start with Docker](#quick-start-with-docker)
- [⚙️ Configuration Guide](#configuration-guide)
- [📂 Setting up Jellyfin Libraries](#setting-up-jellyfin-libraries)
- [🛠️ Advanced: Complex Queries](#advanced-complex-queries)
- [🎬 Watch State Filtering](#watch-state-filtering)
- [🤖 TMDb Recommendations](#tmdb-recommendations)
- [⏰ Scheduler Configuration](#scheduler-configuration)
- [🌿 Seasonal Groups](#seasonal-groups)
- [🗂️ Collection Mode (Boxsets)](#collection-mode-boxsets)
- [🔌 REST API](#rest-api)
- [🧹 Cover Images](#cover-images)
- [💻 Development](#development)
- [🐳 Docker Environment Variables](#docker-environment-variables)
- [📜 License](#license)
- [🐛 Troubleshooting](#troubleshooting)
- [❓ FAQ](#faq)

---

> [!NOTE]
> **This project was largely AI-generated.** I'm a CS student who could have written this myself — I just didn't want to. I reviewed the code, understand how it works, and actively maintain it. The AI was basically just a faster keyboard.

**Jellyfin Groupings** is a Flask-powered web utility that allows you to create **virtual libraries** in [Jellyfin](https://jellyfin.org/) by grouping existing media into symlinked directories. 

Instead of messing with Jellyfin's internal collections or duplicating multi-gigabyte files, this app creates a folder structure (e.g., `/virtual/Action/`) filled with symlinks to your real files. You then add these folders to Jellyfin as independent libraries.

## ✨ Features

- 📂 **Metadata-based Groups**: Filter by genre, actor, studio, tag, or year directly from your library.
- 📜 **External List Support**: Sync with **IMDb**, **Trakt**, **TMDb**, **Letterboxd**, **AniList**, or **MyAnimeList** lists.
- 🤖 **TMDb Recommendations**: Generate groups from TMDb content-based recommendations.
- 🎬 **Watch State Filtering**: Filter by watched/unwatched status per user.
- ⚡ **Complex Logic**: Combine filters with `AND`, `OR`, and `NOT` (e.g., `Genre: Action AND NOT Genre: Sci-Fi`).
- 🔢 **Smart Sorting**: Prefix filenames with a numeric index based on Rating, Year, Name, or List Order.
- 🐳 **Docker-First**: Designed to run alongside your Jellyfin container with easy path mapping.
- 🛠️ **Auto-Detect**: Scans your filesystem to help you configure path translations automatically.
- ⌨️ **Keyboard Shortcuts**: Press <kbd>S</kbd> to sync, <kbd>D</kbd> for a dry-run preview, <kbd>C</kbd> to clean up broken symlinks, or <kbd>R</kbd> to reload the groups list — no mouse needed.

---

## 🚀 Quick Start with Docker

The easiest way to run Jellyfin Groupings is via Docker Compose.

### 1. Create `docker-compose.yml`

```yaml
services:
  jellyfin-groupings:
    image: ghcr.io/entcheneric/jellyfin-groupings:latest
    container_name: jellyfin-groupings
    ports:
      - "5000:5000"
    volumes:
      # Persistent config (API keys, group definitions)
      - ./config:/app/config
      
      # The output directory where virtual folders (symlinks) are created.
      # This MUST be shared with your Jellyfin container.
      - /mnt/user/jellyfin-groupings-virtual:/groupings
      
      # Your media root. Needed so the app can verify files and follow symlinks.
      # Use the same path Jellyfin uses if possible to simplify mapping.
      - /mnt/user/media:/media:ro
      
      # Optional: persist application logs for troubleshooting
      # - ./logs:/app/logs
    restart: unless-stopped
```

### 2. Launch the app

```bash
docker-compose up -d
```

Access the UI at `http://your-server-ip:5000`.

---

## ⚙️ Configuration Guide

When running in Docker, you need to tell the app how to translate paths between what **Jellyfin sees** and what **this container sees**.

### Server Settings

| Field | Description |
|---|---|
| **Jellyfin Server URL** | The address of your Jellyfin server (e.g., `http://192.168.1.50:8096`). |
| **API Key** | Generate one in Jellyfin: `Dashboard -> API Keys`. |
| **Base Target Path** | Set this to `/groupings` (the internal path we mapped in Docker). |
| **Media path as Jellyfin sees it** | The path where Jellyfin sees your media (e.g., `/data/movies`). |
| **Same path on this machine** | The path where *this* container sees the same media (e.g., `/media`). |

> [!TIP]
> Use the **"Auto-Detect Settings"** button in the UI! It will scan your media folders and try to match them with what Jellyfin reports to find the correct path translations for you.

---

## 📂 Setting up Jellyfin Libraries

**Jellyfin libraries are not created automatically.** After you sync your groups, follow these steps:

1. In Jellyfin, go to **Dashboard -> Libraries -> Add Media Library**.
2. Set **Content Type** to **`Mixed Movies and Shows`**.
3. Point the library to a **subdirectory** of your virtual root.
   - *Example:* If your Target Path is mapped to `/mnt/user/jellyfin-groupings-virtual` on the host, and you created a group named `Action`, add `/mnt/user/jellyfin-groupings-virtual/Action` to Jellyfin.
   - **Note:** Ensure your Jellyfin container also has this virtual root mounted!

---

## 🛠️ Advanced: Complex Queries

You can use the **Complex** source type to build highly specific libraries. The query syntax supports:
- **Operators**: `AND`, `OR`, `AND NOT`, `OR NOT`
- **Prefixes**: `genre:`, `actor:`, `studio:`, `tag:`, `year:`

**Example:**
`actor:Tom Cruise AND genre:Action AND NOT genre:Sci-Fi`

## 🎬 Watch State Filtering

Each group can optionally filter by watch state, based on a specific Jellyfin user's
playback history:

| Setting | Effect |
|---|---|
| `Unwatched` | Only include items that the specified user has **not** watched |
| `Watched` | Only include items the specified user **has** watched |
| `(default)` | Include all items regardless of watch state |

To use this, expand **Advanced Settings** in the group editor and select a
Jellyfin user and watch state filter.

## 🤖 TMDb Recommendations

You can generate a group from **TMDb content-based recommendations**.

1. Select the **Recommendations** source type.
2. Add one or more seed items (by TMDb ID) to get recommendations from.
3. The app calls the TMDb `/recommendations` endpoint for each seed item and
   aggregates the results, weighted by position (top recommendations score higher).

Requires a valid `TMDB_API_KEY` in the server settings.

## ⏰ Scheduler Configuration

Jellyfin Groupings includes a built-in scheduler that can automatically sync groups and clean up broken symlinks on a recurring basis.

### Scheduler Settings

| Setting | Description | Default |
|---|---|---|
| **Global Sync Enabled** | Toggle automatic syncing of all groups on a schedule | `false` |
| **Global Sync Schedule** | Cron expression for global sync (e.g., `0 0 * * *` = daily at midnight) | `0 0 * * *` |
| **Excluded Groups** | List of group names that should NOT be synced automatically | `[]` |
| **Cleanup Enabled** | Automatically remove broken symlinks on a schedule | `true` |
| **Cleanup Schedule** | Cron expression for cleanup (e.g., `0 * * * *` = hourly) | `0 * * * *` |

### Per-Group Schedules

Each group can also have its own schedule (override the global cron). When set, that group
will sync at its own cadence regardless of the global setting.

### Example Cron Expressions

| Expression | Meaning |
|---|---|
| `0 0 * * *` | Daily at midnight |
| `0 */6 * * *` | Every 6 hours |
| `0 3 * * 0` | Every Sunday at 3:00 AM |
| `*/30 * * * *` | Every 30 minutes |

---

## 🌿 Seasonal Groups

Groups can be configured to only appear during a specific time of year — useful for
holiday-themed libraries or seasonal collections.

1. In the group editor, enable **Seasonal**.
2. Set the **Start** and **End** dates in `MM-DD` format (e.g., `10-01` to `10-31` for October/Halloween).
3. When the group is out of season, its symlinks are removed automatically.
4. When it re-enters season, the next sync recreates them.

> [!TIP]
> Seasonal groups that are out of season will show a "Seasonal group — out of season"
> message in the sidebar, making it clear why they're currently empty.

---

## 🗂️ Collection Mode (Boxsets)

Instead of symlink-based virtual folders, each group can be synced as a Jellyfin
**Collection (Boxset)**. Enable **"Sync as Collection"** in the group settings.

When enabled:
- The group resolves matching items as usual.
- Instead of creating symlinks, the items are gathered into a Jellyfin Boxset.
- Cover images can be auto-applied (same as library covers).
- Duplicate additions are safely ignored by the Jellyfin API.

> [!NOTE]
> This is useful for curated collections like "Best of 2024" or "Tom Cruise Movies"
> that you want to appear as a single item in your library rather than a whole folder.

---

## 🔌 REST API

The application exposes several API endpoints for programmatic use. All API routes
are prefixed with `/api/`.

### Configuration

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | `GET` | Load the current configuration |
| `/api/config` | `POST` | Save the configuration (requires JSON body with config fields)

### Server / Connection

| Endpoint | Method | Description |
|---|---|---|
| `/api/test-server` | `POST` | Test connectivity to a Jellyfin server |
| `/api/upload_cover` | `POST` | Upload a cover image for a group (base64-encoded data URL) |

### Jellyfin

| Endpoint | Method | Description |
|---|---|---|
| `/api/jellyfin/metadata` | `GET` | Fetch available metadata (genres, actors, studios, tags) |
| `/api/jellyfin/users` | `GET` | Fetch the list of Jellyfin users (for recommendations) |
| `/api/jellyfin/auto-detect-paths` | `POST` | Auto-detect path mappings between Jellyfin and host |

### Sync & Preview

| Endpoint | Method | Description |
|---|---|---|
| `/api/grouping/preview` | `POST` | Preview which items match a single grouping rule |
| `/api/sync/preview_all` | `POST` | Preview all configured groups without making changes |
| `/api/sync` | `POST` | Execute a full synchronisation (creates symlinks / collections) |

### Cleanup

| Endpoint | Method | Description |
|---|---|---|
| `/api/cleanup` | `GET` | List logical folders in the target directory |
| `/api/cleanup` | `POST` | Delete selected folders and optionally their Jellyfin libraries |

### Filesystem

| Endpoint | Method | Description |
|---|---|---|
| `/api/browse` | `GET` | Browse the host filesystem (restricted to home + `/media` + `/mnt`) |

### Diagnostics

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | Health check endpoint for Docker/Kubernetes probes |
| `/api/test/results` | `GET` | Return the latest test output logs |

---

## 🧹 Cover Images

Cover images are stored and managed automatically:

- **Storage**: `{target_path}/.covers/{md5_hash}.jpg`
- **Priority**: Library-local `.covers/` directory → legacy `config/covers/` directory
- **Auto-apply**: When enabled, covers are applied to both virtual libraries and Boxset collections

To set a cover for a group, upload an image via the group editor UI.

---

## 💻 Development

<a id="development"></a>

### Environment Variables

The application reads the following environment variables (which take precedence over values set in the UI config):

| Variable | Purpose |
|---|---|
| `JELLYFIN_API_KEY` | Jellyfin API key override |
| `TRAKT_CLIENT_ID` | Trakt Client ID override |
| `TMDB_API_KEY` | TMDb API Key override |
| `MAL_CLIENT_ID` | MyAnimeList Client ID override |
| `APP_PASSWORD` | Enables HTTP Basic Auth on the web UI |
| `FLASK_PORT` | Server port (default: `5000`) |
| `FLASK_DEBUG` | Enable Flask debug mode (`true`/`false`) |
| `LOG_LEVEL` | Log level for application output. Accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`) |
| `GUNICORN_TIMEOUT` | Gunicorn worker timeout in seconds for long-running API calls (default: `120`). Increase this if sync operations time out |
| `GUNICORN_WORKERS` | Number of gunicorn worker processes for handling concurrent requests (default: `2`). Increase for multi-core hosts |
| `ANILIST_API_URL` | AniList GraphQL endpoint (default: `https://graphql.anilist.co`) |
| `VIRTUAL_JF_PORT` | Port for mock Jellyfin server used during development (default: `8096`) |
| `NETWORK_RETRY_TOTAL` | Max HTTP retries for external API calls (default: `3`; set `0` to disable) |
| `NETWORK_RETRY_BACKOFF_FACTOR` | Sleep multiplier between retries (default: `1.0`) |
| `NETWORK_RETRY_STATUS_FORCELIST` | Status codes that trigger retry (default: `429,500,502,503,504`) |
| `ALLOWED_NON_CSRF_ENDPOINTS` | Comma-separated list of [Flask endpoint names](https://flask.palletsprojects.com/quickstart/#about-responses) exempt from the CSRF header check. These are `blueprint.view` names (e.g., `"main.webhook,main.callback"`), **not** URL paths like `/api/...`. Default: none |

> **Note**: Environment variable overrides are *never* persisted back to `config.json`. They only affect the current process.

See [`.env.example`](.env.example) for quick setup.

### Building from Source

1. Clone the repo.
2. Copy `.env.example` to `.env` and fill in your values for local development.
3. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
4. Install the package (including dev extras):
   ```bash
   pip install -e .[dev]
   ```
5. (Optional) Install pre-commit hooks for lint/format/typecheck/coverage checks:
   ```bash
   pip install pre-commit
   pre-commit install
   ```
6. Run: `python3 app.py`.

### Print-Friendly Pages

The UI includes a print stylesheet that:
- Hides navigation chrome (sidebar, topbar, modals, toasts), so you get clean
  printed output of setup guides, API docs, or troubleshooting sections.
- Shows link URLs after anchor text so printed references are still useful.
- Prevents page breaks inside cards and headings.
- Displays code blocks with visible borders for readability.

Use your browser's **Print** function on any page to see the print-optimized
layout.

### Makefile Targets

A `Makefile` is provided for common development tasks:

| Target | Description |
|---|---|
| `install` | Install the package (`pip install -e .`) |
| `install-dev` | Install with dev extras (`pip install -e ".[dev]"`) |
| `test` | Run the test suite (skips slow integration tests) |
| `test-all` | Run the full test suite including integration tests |
| `test-cov` | Run tests with a coverage report |
| `test-to-file` | Run tests and write output to a file (`python run_tests_to_file.py`) |
| `lint` | Run Ruff linter and format check (`ruff check .` + `ruff format --check .`) |
| `format-check` | Check code formatting without auto-fixing (`ruff format --check .`) |
| `typecheck` | Run mypy type checker (`mypy .`) |
| `format` | Auto-format code with Ruff (`ruff format .`) |
| `clean` | Remove `__pycache__`, `.pytest_cache`, and build artifacts |
| `run` | Start the Flask development server (`python app.py`) |
| `virtual-jellyfin` | Start the mock Jellyfin server for testing |
| `docker-build` | Build the Docker image |
| `docker-run` | Run the Docker container |

```bash
# Quick start after cloning
make install-dev
make test
make run
```

> [!TIP]
> The default `make test` (and `make test-all` / `make test-cov`) uses pytest's `-q` flag for quiet output.
> Override verbosity by setting `PYTEST_ARGS`, e.g.:
> ```bash
> make test PYTEST_ARGS='-v'    # verbose output
> make test PYTEST_ARGS=''      # default pytest verbosity
> ```

### 🧪 Testing

```bash
# Run the full test suite (1354 tests, 100% coverage)
python3 -m pytest

# Run tests with coverage report
python3 -m pytest --cov=.

# Run a specific test file
python3 -m pytest tests/test_sync.py -v -k "complex"

# Run without slow integration/exhaustive tests
python3 -m pytest -m "not exhaustive" tests/

# Generate an HTML coverage report
python3 -m pytest --cov=. --cov-report=html
open htmlcov/index.html
```

Run tests and save output to a file:
```bash
python3 run_tests_to_file.py
```

#### Virtual Jellyfin for Development
If you don't have a real Jellyfin server handy, or want to test without affecting your real setup, you can run a **mock Jellyfin server**:

```bash
python3 start_virtual_jellyfin.py
```

This will start a mock API at `http://localhost:8096`. You can then:
- Access the **Dashboard** at [http://localhost:8096](http://localhost:8096) to see the mock state.
- In the Jellyfin Groupings UI, set the **Server URL** to `http://localhost:8096` and **API Key** to anything (e.g., `test`).

> **Note:** The virtual Jellyfin server is minimal and intended for development/testing. It does not provide all Jellyfin API endpoints.

### Unraid Support
An Unraid Community Applications template is available in the `unraid/` directory.

---

## 🐳 Docker Environment Variables

> **Multi-arch support:** Images are built for both `linux/amd64` and `linux/arm64`.
> Raspberry Pi and other ARM-based homelab users can pull the same image tag.

> **Offline/air-gapped deployments:** All fonts (Inter, Outfit) are self-hosted.
> No external CDN requests are made at page load.

When running via Docker, you can set environment variables to override sensitive config values:

```yaml
services:
  jellyfin-groupings:
    image: ghcr.io/entcheneric/jellyfin-groupings:latest
    container_name: jellyfin-groupings
    ports:
      - "5000:5000"
    volumes:
      - ./config:/app/config
      - /mnt/user/jellyfin-groupings-virtual:/groupings
      - /mnt/user/media:/media:ro
    environment:
      - JELLYFIN_API_KEY=your-api-key
      - TRAKT_CLIENT_ID=your-trakt-client-id
      - TMDB_API_KEY=your-tmdb-api-key
      - MAL_CLIENT_ID=your-myanimelist-client-id
      - APP_PASSWORD=your-password  # Enables HTTP Basic Auth
      - ANILIST_API_URL=            # optional: custom AniList API endpoint
      - NETWORK_RETRY_TOTAL=3         # optional: HTTP retry count for external APIs
      - NETWORK_RETRY_BACKOFF_FACTOR=1.0 # optional: retry backoff multiplier
      - NETWORK_RETRY_STATUS_FORCELIST=429,500,502,503,504 # optional: retry status codes
      - ALLOWED_NON_CSRF_ENDPOINTS= # optional: comma-separated Flask endpoint names (e.g. "main.webhook,main.callback") exempt from CSRF check
      - LOG_LEVEL=INFO                   # optional: log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
      - GUNICORN_TIMEOUT=120            # optional: gunicorn worker timeout in seconds (default: 120)
      - GUNICORN_WORKERS=2              # optional: gunicorn worker process count (default: 2)
      - FLASK_PORT=5000                 # optional: server port (default: 5000)
      - FLASK_DEBUG=false               # optional: set to true for debug mode (default: false)
    restart: unless-stopped
```

## 📜 License

Created and maintained by [entcheneric](https://github.com/entcheneric). 
This project is licensed under the MIT License - feel free to use it however you want!

## 🐛 Troubleshooting

### Enabling Debug Logging

Set the ``LOG_LEVEL`` environment variable to ``DEBUG`` to get more
detailed logs:

```bash
# Docker: add to docker-compose.yml environment section
# LOG_LEVEL=DEBUG

# Native: export before running the app
# export LOG_LEVEL=DEBUG
```

Logs are written to ``logs/jellyfin-groupings.log`` with a rotating
file handler (10 MB max, 3 backups).

### "504 Gateway Time-out" or Sync Hangs

If syncing large libraries triggers a 504 timeout or the sync operation
hangs without completing, the gunicorn worker may be hitting its timeout
limit. Increase it by setting ``GUNICORN_TIMEOUT`` in your
``docker-compose.yml`` environment section:

```yaml
environment:
  - GUNICORN_TIMEOUT=300  # seconds; default is 120
```

After changing this, recreate the container with:

```bash
docker compose up -d
```

> **Note:** ``GUNICORN_TIMEOUT`` only applies to Docker deployments
> that use the default gunicorn entrypoint. Native/flask run deployments
> are not affected.

### Path Translation Issues
If symlinks point to non-existent files, verify your path mapping:
1. Go to **Server Settings** in the UI.
2. Ensure **Media path as Jellyfin sees it** and **Same path on this machine** are correctly set.
3. Use the **Auto-Detect Settings** button to automatically detect the correct mapping.

### "Permission denied" when creating virtual directories
- Ensure the target path is writable by the container/process.
- On Docker, verify the volume mount for the virtual output directory has correct permissions.
- If running as a non-root user, ensure the container user has write access to the mounted volume. You may need to set the user/group ID in your Docker Compose file:
  ```yaml
  services:
    jellyfin-groupings:
      image: ghcr.io/entcheneric/jellyfin-groupings:latest
      user: "1000:1000"  # Match your host user's UID/GID
  ```

### Jellyfin Connection Errors
1. Confirm your Jellyfin server is accessible from the app container.
2. If using Docker networking, use the container name or internal Docker network address.
3. Verify your API key is valid (regenerate in Jellyfin Dashboard if needed).

### Groups Show 0 Items
- Verify the source type and value match actual metadata in Jellyfin.
- For external lists (IMDb, Trakt, etc.), confirm your API keys are configured.
- Try the **Preview** button before syncing to see what will match.

### Cover Images Not Showing
- Jellyfin caches images aggressively — try a **Library Scan** or restart Jellyfin.
- Covers are stored in `{target_path}/.covers/` — ensure the directory persists across restarts.
- If using the legacy `config/covers/` directory, migrate covers to `{target_path}/.covers/` for better persistence.

### Nothing Happens When I Click Sync
- Check the browser console (F12) for JavaScript errors.
- Verify the Jellyfin server is reachable from the app container.
- Check the app logs for detailed error messages. Logs are written to
  `/app/logs/jellyfin-groupings.log` inside the container. To persist them
  across restarts, add a volume mount in your docker-compose:

  ```yaml
  volumes:
    - ./logs:/app/logs
  ```

- Verify the Flask backend is running (`docker logs jellyfin-groupings`).
- Ensure you have at least one group configured.

### Getting More Help
If the above doesn't resolve your issue, please [open a GitHub issue](https://github.com/entcheneric/jellyfin-auto-groupings/issues) with:
- Your Docker/installation setup
- Steps to reproduce
- Relevant logs or error messages

### Keeping Your Fork Up-to-Date

If you've forked the repo, you can pull latest changes from upstream:

```bash
git remote add upstream https://github.com/entcheneric/jellyfin-auto-groupings.git
git fetch upstream
git checkout main
git rebase upstream/main
```

---

### API Error Reference

The REST API returns standard HTTP status codes with JSON error bodies containing
a `message` field:

| Status | Meaning | Common Causes |
|---|---|---|
| `400` | Bad Request | Missing/invalid input fields, failed external list fetch |
| `401` | Unauthorized | Invalid or missing Jellyfin API key |
| `403` | Forbidden | App password required but missing/invalid |
| `500` | Internal Error | Server-side failure (check logs) |

Errors also include an `error` field in the response body with a human-readable description.
When preview or sync fails, the error is shown in a modal dialog within the UI.

> **Delete confirmations:** Deleting a grouping or clearing all groupings uses
> an in-app modal dialog instead of the browser's native `confirm()` prompt,
> providing a consistent experience across browsers and platforms.

---

## ❓ FAQ

### Why does the app need both a Jellyfin-side path and a host-side path?

Because Jellyfin often runs in a Docker container and sees your media at a different
path than this app does. For example, Jellyfin might see files under `/data/movies`
while this app sees them under `/mnt/user/media/movies`. The two path settings
tell the app how to translate between the two views so symlinks point to the right
files.

### Can I use this alongside my existing Jellyfin libraries?

Yes — the app creates *new* virtual directories and symlinks; it never modifies or removes your original media files. Jellyfin scans the new directories as independent libraries.

### Does this duplicate my media files?

No. Symlinks are tiny files that point to the original media. The Jellyfin Groupings app never copies, moves, or alters your media files.

### Why aren't my groups appearing after syncing?

1. Ensure the **target path** symlink folder is added as a library in Jellyfin.
2. Perform a **Library Scan** in Jellyfin (or wait for the auto-scan).
3. Groups with 0 items will not create symlinks — use the **Preview** button to check matches first.

### Can I use the same media item in multiple groups?

Yes. Since each group creates its own symlink (not a copy), the same movie can appear in as many virtual libraries as you like — for example "Action Movies", "90s Movies", and "Christopher Nolan" — all pointing to the same file on disk.

### Can I hide the original libraries in Jellyfin?

Yes. In Jellyfin Dashboard > Libraries, you can uncheck "Display library in home screen" or restrict access per user to keep the original libraries hidden while showing only the virtual groupings.

### What happens if I rename/move a media file?

The symlink will break (show as missing). Run the **Cleanup** operation in the app to remove broken symlinks, then re-sync affected groups. Consider making media files read-only via Docker volume mounts to prevent accidental moves.

### Can I use this without Docker?

Absolutely. See the **Building from Source** section above. You need Python 3.11+, Flask, and the dependencies listed in `pyproject.toml`.

### Does the app need to run on the same machine as Jellyfin?

It needs filesystem access to both your media files and the target symlink directory. If using Docker, both volumes must be mounted into the container. If running natively, the app needs read access to your media directory and write access to the target directory.

### How do I back up my configuration?

Your group definitions and settings are stored in `config/config.json`. Back up this file to preserve all your groups, schedules, and API keys.

### Can multiple users access the web UI?

Yes. You can optionally set an `APP_PASSWORD` environment variable to enable HTTP Basic Auth. Without it, the UI is accessible to anyone on your network.

### Why is my cover image not updating?

Jellyfin aggressively caches images. After uploading a new cover, trigger a **Library Scan** in Jellyfin or restart the container. Covers are stored in `{target_path}/.covers/`.

---

