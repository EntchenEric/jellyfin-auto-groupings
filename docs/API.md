# HTTP API

All `/api/*` routes return JSON unless noted. State-changing requests (`POST`, `PUT`, `DELETE`, `PATCH`) require the header:

```http
X-Requested-With: XMLHttpRequest
```

When `APP_PASSWORD` is set, most `/api/*` routes also require HTTP Basic Auth (password only; username is ignored). The main UI (`GET /`) and `/static/*` assets load without credentials; the SPA prompts for the password on the first `401` response.

When `APP_PASSWORD` is **not** set, the web UI and API are unauthenticated. Do not expose the service to untrusted networks without setting `APP_PASSWORD` or placing it behind a reverse proxy with authentication.

Error responses use `{ "status": "error", "message": "..." }` with an appropriate HTTP status. Success responses use `{ "status": "success", ... }`.

---

## `GET /api/health`

Health check for load balancers and orchestrators.

**Auth:** Required when `APP_PASSWORD` is set (same as other `/api/*` routes).

**Response `200`:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"ok"` or `"error"` |
| `healthcheck.ok` | boolean | Service health |
| `healthcheck.configured` | boolean | Jellyfin URL, API key, and target path present |
| `healthcheck.groups` | number | Count of configured groupings |
| `healthcheck.env_overrides` | array&lt;string&gt; | Active runtime config overrides from environment variables |
| `server.uptime_seconds` | number | Process uptime |
| `server.started_at` | string | ISO 8601 UTC start time |
| `scheduler.running` | boolean | Whether the background scheduler is running |
| `scheduler.job_count` | number | Number of registered scheduler jobs |
| `scheduler.next_run_times` | array&lt;object&gt; | List of scheduled jobs with their next run time; each object has `id`, `name`, and optionally `next_run` |
| `jellyfin.reachable` | boolean or null | Whether the Jellyfin server responded to a lightweight ping; `null` if no server URL is set |

---

## `GET /api/config`

Return the current application configuration.

Sensitive keys are masked as `****` in the response (`api_key`, `trakt_client_id`, `tmdb_api_key`, `mal_client_id`). Environment variable overrides are applied before masking.

**Response `200`:** Full config object (groups, scheduler, paths, flags, etc.)

---

## `POST /api/config`

Replace the entire configuration with the JSON request body.

**Request body:** Config object (same shape as `GET /api/config`).

**Validation:**

- `groups` must be a list (max 200), unique non-empty names, valid `source_type` values.
- Cron expressions in `scheduler` and per-group schedules are validated.

**Response `200`:**

```json
{ "status": "success", "message": "", "config": { } }
```

**Errors:** `400` invalid groups or cron; `500` write or scheduler update failure.

---

## `POST /api/test-server`

Test connectivity to a Jellyfin server.

**Request body:**

| Field | Type | Required |
|-------|------|----------|
| `jellyfin_url` | string | yes |
| `api_key` | string | yes |

**Response `200`:** `{ "status": "success", "message": "Connected to Jellyfin successfully!" }`

**Errors:** `400` missing fields, blocked host (private/loopback IP), connection failure, or non-200 from Jellyfin.

---

## `GET /api/jellyfin/metadata`

Fetch aggregated metadata from Jellyfin (genres, studios, tags, actors) using dedicated list endpoints in parallel.

**Requires:** Jellyfin URL and API key in config.

**Response `200`:**

```json
{
  "status": "success",
  "metadata": {
    "genre": ["Action", "..."],
    "studio": ["..."],
    "tag": ["..."],
    "actor": ["..."]
  }
}
```

---

## `GET /api/jellyfin/users`

List Jellyfin users for User Recommendations groups.

**Response `200`:**

```json
{
  "status": "success",
  "users": [{ "id": "...", "name": "..." }]
}
```

---

## `POST /api/jellyfin/auto-detect-paths`

Detect media path translation between Jellyfin and the host filesystem by matching sample movie filenames.

**Requires:** Jellyfin URL and API key in config.

**Response `200`:**

```json
{
  "status": "success",
  "detected": {
    "media_path_in_jellyfin": "/data/movies",
    "media_path_on_host": "/media",
    "target_path": "/home/user/jellyfin-groupings-virtual",
    "target_path_in_jellyfin": "/home/user/jellyfin-groupings-virtual"
  }
}
```

Fields may be `null` if detection fails.

---

## `POST /api/sync`

Run a full sync for all configured groups (creates symlinks, libraries, collections as configured).

**Request body:** None

**Response `200`:**

```json
{
  "status": "success",
  "message": "Synchronization complete",
  "results": [{ "group": "Action", "links": 42 }]
}
```

**Errors:** `400` validation errors; `429` rate limit (wait before retrying); `500` sync failure.

---

## `POST /api/sync/preview_all`

Dry-run sync — returns what would be synced without writing symlinks or calling Jellyfin write APIs.

**Request body:** None

**Response `200`:** Same shape as `/api/sync`, with preview item lists where applicable.

---

## `POST /api/grouping/preview`

Preview items matched by a single grouping rule.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `genre`, `studio`, `tag`, `year`, `actor`, `general`, or `complex` |
| `value` | string | yes | Filter value or complex query string |
| `watch_state` | string | no | `unwatched` or `watched` |

**Response `200`:**

```json
{
  "status": "success",
  "count": 120,
  "preview_items": [{ "Name": "Title", "Year": 2020 }]
}
```

Returns up to 15 preview titles.

---

## `POST /api/upload_cover`

Save a base64-encoded cover image for a group.

**Request body:**

| Field | Type | Required |
|-------|------|----------|
| `group_name` | string | yes |
| `image` | string | yes — data URL, e.g. `data:image/png;base64,...` |

**Allowed MIME types:** `image/jpeg`, `image/png`, `image/webp`, `image/gif`.
Only these four types are accepted; unsupported types return a `400` error.

**Response `200`:** `{ "status": "success", "message": "Cover saved successfully" }`

**Errors:** `400` invalid format; `413` payload too large (~4 MB).

---

## `GET /api/cleanup`

List folders in the configured target path.

**Response `200`:**

```json
{
  "status": "success",
  "items": [{ "name": "Action", "is_configured": true }]
}
```

---

## `POST /api/cleanup`

Delete selected folders from the target path. When `auto_create_libraries` is enabled, also removes matching Jellyfin virtual libraries.

**Request body:**

```json
{ "folders": ["OldGroup", "TempGroup"] }
```

**Response `200`:** `{ "status": "success", "deleted": 2 }`

**Response `207`:** Partial success with `{ "status": "partial_success", "deleted": N, "errors": [...] }`

---

## `GET /api/browse`

Browse host directories for the path picker. Restricted to whitelisted roots (home, `/media`, `/mnt`).

**Query parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `path` | string | user home | Absolute directory path |

**Response `200`:**

```json
{
  "status": "success",
  "current": "/media",
  "parent": "/",
  "dirs": ["movies", "tv"]
}
```

**Errors:** `403` path outside allowed roots.

---

## `GET /api/test/results`

Return contents of test output log files (development test dashboard).

**Response `200`:**

```json
{
  "status": "success",
  "results": {
    "test_results.txt": "...",
    "current_test_out.txt": "...",
    "test_api_out.txt": "..."
  }
}
```

---

## Non-API routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Main SPA |
| `GET` | `/static/*` | Static assets |
