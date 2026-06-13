# Jellyfin Groupings

<p align="center">
  <img src="jellyfin_groupings_banner.png" alt="Jellyfin Groupings Banner" width="800">
</p>

> **Virtual Libraries Simplified.** Create dynamic Jellyfin libraries using symlinks without duplicating your media.

[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg?logo=docker&logoColor=white)](https://github.com/entcheneric/jellyfin-groupings)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

> [!NOTE]
> **This project was largely AI-generated.** I'm a CS student who could have written this myself — I just didn't want to. I reviewed the code, understand how it works, and actively maintain it. The AI was basically just a faster keyboard.

**Jellyfin Groupings** is a Flask-powered web utility that allows you to create **virtual libraries** in [Jellyfin](https://jellyfin.org/) by grouping existing media into symlinked directories.

Instead of messing with Jellyfin's internal collections or duplicating multi-gigabyte files, this app creates a folder structure (e.g., `/virtual/Action/`) filled with symlinks to your real files. You then add these folders to Jellyfin as independent libraries — or let the app create them for you.

## ✨ Features

- 📂 **Metadata-based Groups**: Filter by genre, actor, studio, tag, or year directly from your library.
- 📜 **External List Support**: Sync with **IMDb**, **Trakt**, **TMDb**, **Letterboxd**, **AniList**, or **MyAnimeList** lists.
- 🎯 **User Recommendations**: Build libraries from TMDb recommendations based on a Jellyfin user's recently watched items.
- 📦 **Collection mode**: Create Jellyfin Collections (Boxsets) instead of symlink folders — no filesystem output.
- 🗓️ **Seasonal groups**: Automatically remove virtual folders when outside a date window (e.g., Halloween content in October only).
- ⚡ **Complex Logic**: Combine filters with `AND`, `OR`, and `NOT`, including `year:` comparisons (e.g., `year:>2000`).
- 🔢 **Smart Sorting**: Prefix filenames with a numeric index based on Rating, Year, Name, or List Order.
- 🐳 **Docker-First**: Designed to run alongside your Jellyfin container with easy path mapping.
- 🛠️ **Auto-Detect**: Scans your filesystem to help you configure path translations automatically.

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
      - /mnt/user/media:/media:ro
    restart: unless-stopped
```

See [`.env.example`](.env.example) for optional environment variables.

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
| **API Key** | Generate one in Jellyfin: `Dashboard -> API Keys`. Can also be set via `JELLYFIN_API_KEY`. |
| **Base Target Path** | Set this to `/groupings` (the internal path we mapped in Docker). |
| **Media path as Jellyfin sees it** | The path where Jellyfin sees your media (e.g., `/data/movies`). |
| **Same path on this machine** | The path where *this* container sees the same media (e.g., `/media`). |

> [!TIP]
> Use the **"Auto-Detect Settings"** button in the UI! It will scan your media folders and try to match them with what Jellyfin reports to find the correct path translations for you.

### Automatic library creation

By default, Jellyfin libraries are **not** created for you. Enable **Auto-Create Libraries in Jellyfin** in Server Settings (`auto_create_libraries` in config) to register a **Mixed Movies and Shows** library for each grouping after sync. Optionally enable **Auto-Set Library Covers** to upload generated covers to Jellyfin.

When auto-creation is off, add libraries manually:

1. In Jellyfin, go to **Dashboard -> Libraries -> Add Media Library**.
2. Set **Content Type** to **`Mixed Movies and Shows`**.
3. Point the library to a **subdirectory** of your virtual root (e.g., `/mnt/user/jellyfin-groupings-virtual/Action`).
4. Ensure your Jellyfin container has the same virtual root mounted.

Set **Target path as Jellyfin sees it** when Jellyfin's path to the virtual root differs from the host path.

---

## 📚 Grouping features

### User Recommendations

Source type **User Recommendations** (`recommendations`) builds a library from TMDb suggestions based on a Jellyfin user's recently watched movies and series.

Requirements:

- TMDb API key (Server Settings or `TMDB_API_KEY`)
- A Jellyfin user selected as the source

### Collection mode

Enable **Create as Collection (Boxset)** on a group to sync into a Jellyfin Collection instead of creating symlink directories. Items stay in your existing libraries; the app finds or creates a collection by group name and adds matched items. Works with **Auto-Set Library Covers** for collection artwork.

### Seasonal groups

Enable **Seasonal Grouping** and set **Show From** / **Until** dates (`MM-DD`). While outside the window, sync removes the group's virtual folder and skips creating symlinks. Windows can span year boundaries (e.g., December 1 through January 1).

### Complex queries with year

Use the **Complex Rule-set (Mixed)** source type or the **Complex** preview type to combine filters:

- **Operators**: `AND`, `OR`, `AND NOT`, `OR NOT`
- **Prefixes**: `genre:`, `actor:`, `studio:`, `tag:`, `year:`

**Year filters** support exact match and comparisons:

| Example | Meaning |
|---------|---------|
| `year:1999` | Production year equals 1999 |
| `year:>2000` | After 2000 |
| `year:<1990` | Before 1990 |
| `year:>=2020` | 2020 or later |

**Example:**

`actor:Tom Cruise AND genre:Action AND year:>2000 AND NOT genre:Sci-Fi`

---

## 🔐 Environment variables

Copy [`.env.example`](.env.example) as a starting point. API keys set via env override `config.json` at runtime and are **not** written back to disk.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_PASSWORD` | *(empty)* | HTTP Basic Auth password for `/api/*` routes. See [APP_PASSWORD security model](#app_password-security-model). |
| `ALLOWED_NON_CSRF_ENDPOINTS` | *(empty)* | Comma-separated paths exempt from CSRF header checks. |
| `FLASK_PORT` | `5000` | Port for `python app.py` development server. |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode. |
| `LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `GUNICORN_WORKERS` | `2` | Gunicorn worker processes (Docker production). |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn request timeout in seconds. |
| `JELLYFIN_API_KEY` | — | Overrides `api_key` in config. |
| `TRAKT_CLIENT_ID` | — | Overrides Trakt client ID in config. |
| `TMDB_API_KEY` | — | Overrides TMDb API key in config. |
| `MAL_CLIENT_ID` | — | Overrides MyAnimeList client ID in config. |
| `ANILIST_API_URL` | `https://graphql.anilist.co` | AniList GraphQL endpoint. |
| `NETWORK_RETRY_TOTAL` | `3` | Max retries for outbound HTTP requests. |
| `NETWORK_RETRY_BACKOFF_FACTOR` | `1.0` | Backoff factor between HTTP retries. |
| `SCHEDULER_ENABLED` | `1` | Set to `0` to disable the background scheduler. |
| `DISABLE_SCHEDULER` | `0` | Set to `1` to disable the background scheduler. |
| `VIRTUAL_JF_PORT` | `8096` | Port for `python start_virtual_jellyfin.py`. |

E2E-only variables: `E2E_APP_URL`, `E2E_JELLYFIN_URL`, `E2E_JELLYFIN_URL_INTERNAL`.

---

## 🔒 APP_PASSWORD security model

When `APP_PASSWORD` is set:

- **`/api/*` routes** (except `/api/health` and `/api/metrics`) require HTTP Basic Auth. Only the **password** is checked; the username is ignored.
- **`/`, `/test`, and `/static/*`** load without authentication so the SPA assets are reachable.
- The browser UI does **not** prompt for credentials automatically — unauthenticated API calls from the SPA receive `401` until you configure your reverse proxy or browser to send Basic Auth, or you access the app on a trusted network without `APP_PASSWORD`.

For production exposure, place the app behind HTTPS (see below) and set a strong `APP_PASSWORD`. Prefer env vars over storing secrets in `config.json`.

`GET /api/config` masks sensitive keys in responses even when authenticated.

---

## 🌐 HTTPS and reverse proxy

Run Jellyfin Groupings behind nginx, Caddy, or Traefik when exposing it beyond your LAN:

- Terminate TLS at the proxy and forward to `http://127.0.0.1:5000` (or the container port).
- If using `APP_PASSWORD`, configure the proxy to pass through `Authorization` headers.
- Health checks can target `GET /api/health`; Prometheus scraping can use `GET /api/metrics`.

The app does not terminate TLS itself in the default Docker image (Gunicorn on port 5000).

---

## ⌨️ Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Escape` | Close the topmost open modal dialog |

---

## 🧪 End-to-end tests

The `e2e/` directory contains a Docker Compose stack for integration testing against real Jellyfin:

```bash
# Generate sample media (requires ffmpeg)
./e2e/generate_test_media.sh

# Start Jellyfin + app
docker compose -f e2e/docker-compose.e2e.yml up -d

# Run E2E tests (requires JELLYFIN_API_KEY from Jellyfin dashboard)
pytest tests/test_e2e/ -v -m e2e
```

See `e2e/docker-compose.e2e.yml` for service URLs and volume mounts.

---

## 👨‍💻 Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, pre-commit, and PR guidelines.

Quick start:

```bash
git clone https://github.com/entcheneric/jellyfin-groupings.git
cd jellyfin-groupings
pip install -e ".[dev]"
pre-commit install
python app.py
pytest tests/ -v
```

### Python version support

Requires **Python 3.11+** (`requires-python >=3.11` in `pyproject.toml`). CI tests on **3.11** and **3.12**. The Docker image uses Python 3.12.

### Virtual Jellyfin for development

If you don't have a real Jellyfin server handy:

```bash
python start_virtual_jellyfin.py
```

Mock API at `http://localhost:8096` (override with `VIRTUAL_JF_PORT`). Set **Server URL** to that address and **API Key** to anything (e.g., `test`).

### API reference

HTTP routes are documented in [docs/API.md](docs/API.md).

### Unraid Support

An Unraid Community Applications template is available in the `unraid/` directory.

---

## 📜 License

Created and maintained by [entcheneric](https://github.com/entcheneric).
This project is licensed under the MIT License - feel free to use it however you want!
