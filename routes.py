"""routes.py - Flask Blueprint containing all HTTP route handlers.

Every route is registered on the ``bp`` Blueprint which is imported and
registered with the Flask application in ``app.py``.  Route handlers are
intentionally thin: they validate inputs, delegate to service functions in
other modules, and serialise results back to JSON.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.exceptions import HTTPException

import network

if TYPE_CHECKING:
    from flask.typing import ResponseReturnValue

from config import load_config, save_config
from jellyfin import (
    _PAGE_LIMIT,
    RECURSIVE_TRUE,
    _paginate_jellyfin,
    delete_virtual_folder,
    fetch_jellyfin_items,
    get_users,
)
from scheduler import update_scheduler_jobs, validate_cron
from sync import _get_cover_path, preview_group, run_sync

logger = logging.getLogger(__name__)

__all__ = ["bp"]

bp = Blueprint("main", __name__)


@bp.errorhandler(400)
@bp.errorhandler(500)
def _handle_config_error(exc: Exception) -> ResponseReturnValue:
    """Translate blueprint HTTP exceptions into JSON error responses."""
    if isinstance(exc, HTTPException):
        if exc.code is None:
            raise exc
        return jsonify({"status": "error", "message": exc.description}), exc.code
    raise exc


def _error(message: str, status_code: int = 400, **extra: Any) -> ResponseReturnValue:
    """Return a JSON error response."""
    payload: dict[str, Any] = {"status": "error", "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code


def _success(message: str, status_code: int = 200, **extra: Any) -> ResponseReturnValue:
    """Return a JSON success response."""
    payload: dict[str, Any] = {"status": "success", "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code


# Max size for base64 encoded cover image (approx 4MB)
MAX_B64_SIZE = 4 * 1024 * 1024

# Auto-detect filesystem search limits
_AUTO_DETECT_TIMEOUT = 30
_AUTO_DETECT_MAX_FILES = 50_000
_AUTO_DETECT_MAX_DEPTH = 6

# Test result filenames
_TEST_RESULT_FILENAMES = ("test_results.txt", "current_test_out.txt", "test_api_out.txt")

# Allowed preview metadata types
_ALLOWED_PREVIEW_TYPES: frozenset[str] = frozenset(
    {"genre", "studio", "tag", "year", "actor", "general", "complex"},
)

# Default filesystem search roots for auto-detect
_DEFAULT_SEARCH_ROOTS: tuple[str, ...] = (
    str(Path.home()),
    "/media",
    "/mnt",
)

# Server connection-test timeout (seconds)
_TEST_SERVER_TIMEOUT: int = 5

# Auto-detect sample fetch limit
_AUTO_DETECT_SAMPLE_LIMIT: int = 10

# Auto-detect Jellyfin API timeout (seconds)
_AUTO_DETECT_JELLYFIN_TIMEOUT: int = 10

# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

_APP_PASSWORD: str = os.environ.get("APP_PASSWORD", "")


@bp.before_request
def _check_auth() -> ResponseReturnValue | None:
    """Require HTTP Basic Auth when APP_PASSWORD is set."""
    if not _APP_PASSWORD:
        return None
    # Allow unauthenticated access to the main UI and static assets
    if request.endpoint in ("main.index", "main.test_dashboard"):
        return None
    if request.path.startswith("/static/"):
        return None

    auth = request.authorization
    if auth and auth.password == _APP_PASSWORD:
        return None

    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Jellyfin Groupings"'},
    )


@bp.before_request
def _check_csrf() -> ResponseReturnValue | None:
    """Require X-Requested-With header on state-changing requests."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if current_app.testing:
            return None
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return _error("CSRF validation failed", 403)
    return None


# ---------------------------------------------------------------------------
# Security helpers for the filesystem browser
# ---------------------------------------------------------------------------

def _is_valid_folder_name(name: str) -> bool:
    """Return True if *name* is a safe, non-empty folder name without path separators."""
    return (
        isinstance(name, str)
        and bool(name)
        and name not in (".", "..")
        and "/" not in name
        and "\\" not in name
    )


# Roots that the folder browser is allowed to expose.
_BROWSE_ROOTS: tuple[str, ...] = tuple(
    os.path.realpath(r) for r in _DEFAULT_SEARCH_ROOTS
)


def _path_is_allowed(path: str) -> bool:
    """Return ``True`` only if *path* is at or below one of the whitelisted roots.

    Args:
        path: Absolute filesystem path to check.

    Returns:
        ``True`` if access should be permitted, ``False`` otherwise.

    """
    real = os.path.realpath(path)
    return any(
        real == root or real.startswith(root + os.sep)
        for root in _BROWSE_ROOTS
    )


def _get_jellyfin_config(
    missing_msg: str = "Server settings not configured",
) -> tuple[str, str]:
    """Load and validate Jellyfin URL + API key from the active config.

    Raises:
        werkzeug.exceptions.HTTPException: 400 or 500 if the config is missing or invalid.

    Returns:
        ``(url, api_key)`` on success.

    """
    config = load_config()
    if not isinstance(config, dict):
        abort(500, description="Invalid configuration format")
    url = str(config.get("jellyfin_url") or "").rstrip("/")
    api_key = str(config.get("api_key") or "")
    if not url or not api_key:
        abort(400, description=missing_msg)
    return url, api_key


# ---------------------------------------------------------------------------
# Config routes
# ---------------------------------------------------------------------------


@bp.route("/api/config", methods=["GET"])
def get_config() -> ResponseReturnValue:
    """Return the current application configuration as JSON.

    Returns:
        JSON-serialised configuration dictionary.

    """
    return jsonify(load_config())


def _validate_cron_expressions(new_config: dict[str, Any]) -> list[str]:
    """Validate all cron expressions in *new_config*, returning a list of errors."""
    cron_errors: list[str] = []
    sched_cfg = new_config.get("scheduler", {})
    if sched_cfg.get("global_enabled"):
        global_sched = sched_cfg.get("global_schedule", "")
        err = validate_cron(global_sched)
        if err:
            cron_errors.append(f"Global schedule: {err}")
    cleanup_sched = sched_cfg.get("cleanup_schedule", "")
    if cleanup_sched and sched_cfg.get("cleanup_enabled", True):
        err = validate_cron(cleanup_sched)
        if err:
            cron_errors.append(f"Cleanup schedule: {err}")
    for group in new_config.get("groups", []):
        if group.get("schedule_enabled") and group.get("schedule"):
            err = validate_cron(group["schedule"])
            if err:
                cron_errors.append(f"Group '{group.get('name', 'unnamed')}': {err}")
    return cron_errors


@bp.route("/api/config", methods=["POST"])
def update_config() -> ResponseReturnValue:
    """Persist a new application configuration supplied in the request body.

    The entire configuration object is replaced with the POSTed JSON.

    Returns:
        JSON with ``status`` and the saved ``config``, or a 500 error if the
        config file could not be written.

    """
    new_config = request.get_json(silent=True)
    if not isinstance(new_config, dict):
        return _error("Request body must be a JSON object", 400)

    cron_errors = _validate_cron_expressions(new_config)
    if cron_errors:
        return _error("Invalid cron expression(s)", 400, errors=cron_errors)

    try:
        save_config(new_config)
    except OSError as exc:
        logger.exception("Failed to write config file")
        return _error(f"Config file write failed: {exc}", 500)

    try:
        update_scheduler_jobs()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        logger.exception("Failed to update scheduler jobs")
        return _error(
            f"Config saved but scheduler could not be updated: {exc!s}",
            500,
            config=new_config,
        )

    return _success("", config=new_config)


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------


@bp.route("/api/test-server", methods=["POST"])
def test_server() -> ResponseReturnValue:
    """Verify connectivity to a Jellyfin server.

    Expects a JSON body with ``jellyfin_url`` and ``api_key`` fields.

    Returns:
        JSON with ``status`` and a human-readable ``message``.

    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object", 400)
    url: str = str(data.get("jellyfin_url") or "").rstrip("/")
    api_key: str = str(data.get("api_key") or "")

    if not url or not api_key:
        return _error("URL and API Key are required", 400)

    try:
        response = network.get(
            f"{url}/System/Info",
            headers={"X-Emby-Token": api_key},
            timeout=_TEST_SERVER_TIMEOUT,
        )
        if response.status_code == 200:
            return _success("Connected to Jellyfin successfully!")
        return _error(f"Server returned status {response.status_code}", 400)
    except requests.exceptions.RequestException as exc:
        return _error(f"Connection error: {exc!s}", 400)


# ---------------------------------------------------------------------------
# Jellyfin metadata
# ---------------------------------------------------------------------------


def _fetch_jellyfin_endpoint(
    base_url: str,
    api_key: str,
    endpoint: str,
    *,
    timeout: int = 15,
    extra_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all items from a Jellyfin list endpoint (Genres, Studios, etc.).

    Handles paginated responses, collecting all items across all pages.
    If a request fails part-way through, already-fetched items are returned
    rather than raising (partial data is better than nothing for metadata).

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        endpoint: Name of the dedicated endpoint (e.g. ``Genres``, ``Studios``).
        timeout: HTTP request timeout per page.
        extra_params: Additional query-string parameters per request.

    Returns:
        A list of all item dictionaries from the endpoint.

    """
    items: list[dict[str, Any]] = []
    try:
        for page in _paginate_jellyfin(
            base_url, api_key, endpoint, extra_params, limit=_PAGE_LIMIT, timeout=timeout,
        ):
            items.extend(page)
    except RuntimeError:
        if items:
            return items
        raise
    return items


@bp.route("/api/jellyfin/metadata", methods=["GET"])
def get_jellyfin_metadata() -> ResponseReturnValue:
    """Return aggregated metadata (genres, studios, tags, actors) from Jellyfin.

    Uses Jellyfin's dedicated ``/Genres``, ``/Studios``, ``/Persons``, and
    ``/Tags`` endpoints fetched in parallel, which is orders of magnitude
    faster than scanning all items recursively.

    Returns:
        JSON with ``status`` and a ``metadata`` object containing ``genre``,
        ``studio``, ``tag``, and ``actor`` lists.

    """
    url, api_key = _get_jellyfin_config()

    result: dict[str, list[str]] = {}
    failed = 0

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures: dict[str, Any] = {
                "genre": pool.submit(_fetch_jellyfin_endpoint, url, api_key, "Genres"),
                "studio": pool.submit(_fetch_jellyfin_endpoint, url, api_key, "Studios"),
                "actor": pool.submit(
                    _fetch_jellyfin_endpoint,
                    url,
                    api_key,
                    "Persons",
                    extra_params={"PersonTypes": "Actor"},
                ),
                "tag": pool.submit(_fetch_jellyfin_endpoint, url, api_key, "Tags"),
            }
            for key, future in futures.items():
                try:
                    items = future.result()
                    result[key] = [
                        item.get("Name", "") for item in items if item.get("Name")
                    ]
                except (RuntimeError, ValueError):
                    logger.warning("Failed to process metadata key %r", key, exc_info=True)
                    result[key] = []
                    failed += 1

        if failed >= len(futures):
            return _error("Failed to fetch metadata from Jellyfin", 400)

        return _success("", metadata=result)
    except (RuntimeError, OSError) as exc:
        logger.exception("Unexpected error fetching Jellyfin metadata")
        return _error(str(exc), 500)


# ---------------------------------------------------------------------------
# Jellyfin users
# ---------------------------------------------------------------------------


@bp.route("/api/jellyfin/users", methods=["GET"])
def get_jellyfin_users() -> ResponseReturnValue:
    """Return a list of users from Jellyfin.

    Returns:
        JSON with ``status`` and a ``users`` object containing ``id`` and ``name``.

    """
    url, api_key = _get_jellyfin_config()

    try:
        users_list = get_users(url, api_key)
        return _success(
            "",
            users=[{"id": u.get("Id"), "name": u.get("Name")} for u in users_list],
        )
    except RuntimeError as exc:
        return _error(str(exc), 400)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@bp.route("/api/upload_cover", methods=["POST"])
def upload_cover() -> ResponseReturnValue:
    """Save a base64-encoded cover image for a group.

    Expects a JSON body with ``group_name`` and ``image`` (data URL).
    Decodes and saves the image to a location determined by
    :func:`sync._get_cover_path`: it saves to
    ``target_base/.covers/[md5(group_name)].jpg`` when the target directory
    exists, otherwise it falls back to ``config/covers/[md5(group_name)].jpg``.
    The file name used is md5(group_name) + .jpg. Reference
    :func:`sync._get_cover_path` for the detailed storage precedence.

    Returns:
        JSON with ``status`` and ``message``.

    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    group_name = data.get("group_name")
    image_data = data.get("image")
    if not isinstance(group_name, str) or not isinstance(image_data, str):
        return _error("group_name and image must be strings", 400)

    if not image_data.startswith("data:image/"):
        return _error("Invalid image format", 400)

    try:
        _header, encoded = image_data.split(",", 1)

        if len(encoded) > MAX_B64_SIZE:
            return _error("Payload too large", 413)

        decoded = base64.b64decode(encoded)

        # Determine cover storage path using the shared helper
        cfg = load_config()
        target_path = str(cfg.get("target_path", ""))

        cover_path = _get_cover_path(group_name, target_path, check_exists=False)
        if cover_path is None:
            return _error("Could not resolve cover storage path", 500)

        Path(cover_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(cover_path).open("wb") as f:
            f.write(decoded)

        return _success("Cover saved successfully")
    except (ValueError, binascii.Error):
        return _error("Malformed image data", 400)
    except (OSError, RuntimeError) as exc:
        logger.exception("Failed to save cover image")
        return _error(f"Server error: {exc!s}", 500)


def _run_sync_handler(dry_run: bool = False) -> ResponseReturnValue:
    """Run sync (or preview) and return a JSON response."""
    try:
        config: dict[str, Any] = load_config()
        sync_results = run_sync(config, dry_run=dry_run)
        if dry_run:
            return _success(
                "Preview generated successfully",
                results=sync_results,
            )
        return _success(
            "Synchronization complete",
            results=sync_results,
        )
    except ValueError as exc:
        return _error(f"{exc!s}", 400)
    except (RuntimeError, OSError) as exc:
        prefix = "Sync preview failed" if dry_run else "Sync failed"
        return _error(f"{prefix}: {exc!s}", 500)


@bp.route("/api/sync", methods=["POST"])
def sync_groupings() -> ResponseReturnValue:
    """Trigger a full synchronisation of all configured groupings.

    Reads the current configuration, delegates to :func:`sync.run_sync`, and
    returns per-group results.
    """
    return _run_sync_handler(dry_run=False)


@bp.route("/api/sync/preview_all", methods=["POST"])
def preview_all_sync() -> ResponseReturnValue:
    """Preview a full synchronisation of all configured groupings without creating symlinks.

    Reads the current configuration, delegates to :func:`sync.run_sync` with dry_run=True,
    and returns per-group preview results.
    """
    return _run_sync_handler(dry_run=True)


@bp.route("/api/grouping/preview", methods=["POST"])
def preview_grouping() -> ResponseReturnValue:
    """Preview what items a grouping rule would include.

    Accepts a JSON body with 'type' and 'value'. If the 'value' contains
    logical operators (AND, OR, etc.), it is parsed as a complex query.
    Otherwise, it is treated as a simple metadata filter.

    Returns:
        JSON with 'status', 'count' of matched items, and 'preview_items'
        (a list of the first 15 matched titles).

    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    url, api_key = _get_jellyfin_config()

    # Validate and normalize "type"
    type_raw = data.get("type")
    if not isinstance(type_raw, str):
        return _error("Missing or invalid 'type'", 400)

    type_name = type_raw.lower().strip()
    if not type_name or type_name not in _ALLOWED_PREVIEW_TYPES:
        return _error(f"Invalid metadata type: {type_raw}", 400)

    # Validate value
    val_raw = data.get("value")
    if not isinstance(val_raw, str):
        return _error("Value must be a string", 400)

    val = val_raw.strip()
    if not val:
        return _error("Value cannot be empty", 400)

    watch_state = (data.get("watch_state") or "").strip().lower()

    try:
        # Resolve items using the public sync API
        items, error, status_code = preview_group(type_name, val, url, api_key, watch_state)

        if error is not None:
            return _error(error, status_code)

        # Return summary count and first few items
        results = [
            {"Name": i.get("Name", "Unknown"), "Year": i.get("ProductionYear", "")}
            for i in items[:15]
        ]

        return _success("", count=len(items), preview_items=results)
    except (ValueError, RuntimeError) as exc:
        logger.exception("Failed to generate grouping preview")
        return _error(f"Preview failed: {exc!s}", 500)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@bp.route("/api/cleanup", methods=["GET"])
def get_cleanup_items() -> ResponseReturnValue:
    """Return a list of logical folders in the target directory."""
    config: dict[str, Any] = load_config()
    target_base: str = str(config.get("target_path") or "")
    if not target_base or not Path(target_base).exists():
        return _success("", items=[])

    configured_groups: set[str] = {str(g.get("name")) for g in config.get("groups", []) if g.get("name")}

    try:
        entries = [
            {"name": entry.name, "is_configured": entry.name in configured_groups}
            for entry in Path(target_base).iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        ]
        return _success("", items=sorted(entries, key=lambda x: str(x["name"])))
    except OSError as exc:
        return _error(str(exc), 500)


def _delete_folder(
    name: str,
    target_base: str,
    auto_create_libraries: bool,
    url: str,
    api_key: str,
) -> tuple[bool, str | None]:
    """Delete a single folder and optionally its Jellyfin library.

    Returns:
        ``(deleted, error_message)`` where *deleted* is True if the folder
        was removed successfully.
    """
    path = Path(target_base) / name
    if not path.exists() or not path.is_dir():
        return False, None
    try:
        shutil.rmtree(path)
        if auto_create_libraries and url and api_key:
            try:
                delete_virtual_folder(url, api_key, name)
            except (RuntimeError, OSError) as e:
                logger.warning("Failed to delete Jellyfin library '%s': %s", name, e)
    except OSError as exc:
        return False, f"Failed to delete {name}: {exc}"
    else:
        return True, None


@bp.route("/api/cleanup", methods=["POST"])
def perform_cleanup() -> ResponseReturnValue:
    """Delete the selected folders from the target directory."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    folders = data.get("folders", [])
    if not isinstance(folders, list):
        return _error("'folders' must be a list", 400)

    config: dict[str, Any] = load_config()
    target_base: str = str(config.get("target_path") or "")
    if not target_base or not Path(target_base).exists():
        return _error("Target path not found", 404)

    auto_create_libraries: bool = bool(config.get("auto_create_libraries"))
    url: str = str(config.get("jellyfin_url") or "").rstrip("/")
    api_key: str = str(config.get("api_key") or "")

    deleted: int = 0
    errors: list[str] = []
    for name in folders:
        if not _is_valid_folder_name(name):
            errors.append(f"Invalid folder name: {name}")
            continue
        removed, err = _delete_folder(name, target_base, auto_create_libraries, url, api_key)
        if removed:
            deleted += 1
        elif err:
            errors.append(err)

    if errors:
        return jsonify({"status": "partial_success", "deleted": deleted, "errors": errors}), 207
    return _success("", deleted=deleted)


# ---------------------------------------------------------------------------
# Auto-detect paths
# ---------------------------------------------------------------------------


def _search_local_filesystem(
    filename: str,
    search_roots: list[str],
    *,
    timeout: int = _AUTO_DETECT_TIMEOUT,
    max_files: int = _AUTO_DETECT_MAX_FILES,
) -> str | None:
    """Walk *search_roots* looking for *filename*.

    Prunes mount points (except the root itself), enforces a *timeout* and
    *max_files* cap, and stops at _AUTO_DETECT_MAX_DEPTH path-component depth.

    Returns the absolute path of the first match found, or ``None``.
    """
    walk_start = time.monotonic()
    files_scanned = 0
    for root in search_roots:
        if not Path(root).is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if os.path.ismount(dirpath) and dirpath != root:
                dirnames.clear()
                continue
            if time.monotonic() - walk_start > timeout:
                logger.warning(
                    "auto-detect timed out after %ds, %d files scanned",
                    timeout,
                    files_scanned,
                )
                dirnames.clear()
                break
            files_scanned += len(filenames)
            if files_scanned > max_files:
                logger.warning(
                    "auto-detect hit file limit (%d), stopping scan",
                    max_files,
                )
                dirnames.clear()
                break
            if filename in filenames:
                return str(Path(dirpath) / filename)
            if len(Path(dirpath).parts) > _AUTO_DETECT_MAX_DEPTH:
                dirnames.clear()
    return None


def _compute_common_root(jellyfin_path: str, host_path: str) -> tuple[str | None, str | None]:
    """Infer the common root prefixes from a Jellyfin path and its host match.

    Counts matching trailing path components and returns the inferred
    ``(jellyfin_root, host_root)`` pair.
    """
    j_parts = Path(jellyfin_path).parts
    h_parts = Path(host_path).parts
    common_count = 0
    while (
        common_count < len(j_parts)
        and common_count < len(h_parts)
        and j_parts[-(common_count + 1)] == h_parts[-(common_count + 1)]
    ):
        common_count += 1

    if common_count > 0:
        j_slice = j_parts[:-common_count]
        h_slice = h_parts[:-common_count]
        j_root = str(Path(*j_slice)) if j_slice else os.sep
        h_root = str(Path(*h_slice)) if h_slice else os.sep
        return j_root, h_root
    return None, None


@bp.route("/api/jellyfin/auto-detect-paths", methods=["POST"])
def auto_detect_paths() -> ResponseReturnValue:
    """Attempt to automatically detect Jellyfin and host media root paths.

    Fetches a sample of movie paths from Jellyfin and then searches the local
    filesystem (home directory, ``/media``, ``/mnt``) for the matching files.
    The common path prefix between the Jellyfin path and the local path is
    returned as the suggested ``media_path_in_jellyfin`` /
    ``media_path_on_host`` pair.

    Returns:
        JSON with ``status`` and a ``detected`` object containing
        ``media_path_in_jellyfin``, ``media_path_on_host``, and
        ``target_path``.

    """
    url, api_key = _get_jellyfin_config(
        missing_msg="Server settings required for detection",
    )

    try:
        items = fetch_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": RECURSIVE_TRUE,
                "IncludeItemTypes": "Movie",
                "Limit": str(_AUTO_DETECT_SAMPLE_LIMIT),
                "Fields": "Path",
            },
            timeout=_AUTO_DETECT_JELLYFIN_TIMEOUT,
        )
    except RuntimeError as exc:
        return _error(str(exc), 400)

    if not items:
        return _error("No media found in Jellyfin to detect paths", 400)

    home_dir = str(Path.home())
    detected_j_root: str | None = None
    detected_h_root: str | None = None

    for item in items:
        j_path = item.get("Path")
        if not j_path:
            continue

        match_found = _search_local_filesystem(
            Path(j_path).name,
            list(_DEFAULT_SEARCH_ROOTS),
        )
        if match_found:
            detected_j_root, detected_h_root = _compute_common_root(j_path, match_found)
            if detected_j_root:
                break

    suggested_target = str(Path(home_dir) / "jellyfin-groupings-virtual")

    return _success(
        "",
        detected={
            "media_path_in_jellyfin": detected_j_root,
            "media_path_on_host": detected_h_root,
            "target_path": suggested_target,
            "target_path_in_jellyfin": suggested_target,
        },
    )


# ---------------------------------------------------------------------------
# Filesystem browser
# ---------------------------------------------------------------------------


@bp.route("/api/browse", methods=["GET"])
def browse_directory() -> ResponseReturnValue:
    """Return the immediate (non-hidden) subdirectories of a given path.

    Used by the frontend folder picker to navigate the host filesystem.
    Access is restricted to paths under the whitelisted roots (home directory,
    ``/media``, ``/mnt``).

    Query Parameters:
        path (str): Absolute path to list.  Defaults to the user's home
            directory.

    Returns:
        JSON with ``status``, ``current`` path, nullable ``parent`` path, and
        ``dirs`` (sorted list of subdirectory names).

    """
    raw: str = request.args.get("path", "")
    path: str = str(Path(raw).resolve()) if raw else str(Path.home())

    # Fall back to parent if the supplied path resolves to a file
    if not Path(path).is_dir():
        path = str(Path(path).parent)

    if not _path_is_allowed(path):
        return _error("Access to this path is not permitted", 403)

    try:
        entries: list[str] = sorted(
            entry.name
            for entry in Path(path).iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )
    except PermissionError:
        entries = []
    except OSError as exc:
        return _error(str(exc), 400)

    parent: str | None = str(Path(path).parent) if path != os.sep else None

    return _success("", current=path, parent=parent, dirs=entries)


# ---------------------------------------------------------------------------
# Test Dashboard
# ---------------------------------------------------------------------------


@bp.route("/api/test/results", methods=["GET"])
def get_test_results() -> ResponseReturnValue:
    """Return the contents of the latest test output logs."""
    results = {}
    for filename in _TEST_RESULT_FILENAMES:
        if Path(filename).exists():
            try:
                with Path(filename).open(encoding="utf-8") as f:
                    results[filename] = f.read()
            except (OSError, UnicodeDecodeError):
                results[filename] = "Error reading file."
        else:
            results[filename] = "No output found."

    return _success("", results=results)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


@bp.route("/")
def index() -> ResponseReturnValue:
    """Serve the single-page frontend.

    Returns:
        The rendered ``templates/base.html`` Jinja2 template.

    """
    return render_template("base.html")


@bp.route("/test")
def test_dashboard() -> ResponseReturnValue:
    """Serve the test dashboard frontend.

    Returns:
        The ``test.html`` file located next to ``app.py``.

    """
    return send_from_directory(".", "test.html")
