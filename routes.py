"""
routes.py – Flask Blueprint containing all HTTP route handlers.

Every route is registered on the ``bp`` Blueprint which is imported and
registered with the Flask application in ``app.py``.  Route handlers are
intentionally thin: they validate inputs, delegate to service functions in
other modules, and serialise results back to JSON.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests
from flask import Blueprint, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue

from config import load_config, save_config
from jellyfin import delete_virtual_folder, fetch_jellyfin_items, get_users
from scheduler import update_scheduler_jobs, validate_cron
from sync import get_cover_path, preview_group, run_sync

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)

# Max size for base64 encoded cover image (approx 4MB)
MAX_B64_SIZE = 4 * 1024 * 1024

# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------


@bp.before_request
def _check_csrf() -> ResponseReturnValue | None:
    """Require X-Requested-With header on state-changing requests."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        from flask import current_app
        if current_app.testing:
            return None
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return jsonify({"status": "error", "message": "CSRF validation failed"}), 403
    return None


# ---------------------------------------------------------------------------
# Security helpers for the filesystem browser
# ---------------------------------------------------------------------------

# Roots that the folder browser is allowed to expose.
_BROWSE_ROOTS: tuple[str, ...] = tuple(
    os.path.realpath(r)
    for r in (os.path.expanduser("~"), "/media", "/mnt")
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
) -> tuple[str, str] | tuple[ResponseReturnValue, int]:
    """Load and validate Jellyfin URL + API key from the active config.

    Returns:
        ``(url, api_key)`` on success, or a JSON error ``(response, status_code)``
        tuple when the config is missing or invalid.
    """
    config = load_config()
    if not isinstance(config, dict):
        return jsonify({"status": "error", "message": "Invalid configuration format"}), 500
    url = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key = str(config.get("api_key", ""))
    if not url or not api_key:
        return jsonify({"status": "error", "message": missing_msg}), 400
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
        return (
            jsonify({"status": "error", "message": "Request body must be a JSON object"}),
            400,
        )

    # Validate cron expressions
    cron_errors = []
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
    if cron_errors:
        return (
            jsonify({"status": "error", "message": "Invalid cron expression(s)", "errors": cron_errors}),
            400,
        )
    try:
        save_config(new_config)
    except OSError as exc:
        logger.exception("Failed to write config file")
        return (
            jsonify({"status": "error", "message": f"Config file write failed: {exc}"}),
            500,
        )

    # Update background jobs based on new config
    try:
        update_scheduler_jobs()
    except Exception:
        logger.exception("Failed to update scheduler jobs")

    return jsonify({"status": "success", "config": new_config})


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
        return (
            jsonify({"status": "error", "message": "Request body must be a JSON object"}),
            400,
        )
    url: str = str(data.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(data.get("api_key", ""))

    if not url or not api_key:
        return jsonify({"status": "error", "message": "URL and API Key are required"}), 400

    try:
        response = requests.get(
            f"{url}/System/Info",
            headers={"X-Emby-Token": api_key},
            timeout=5,
        )
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Connected to Jellyfin successfully!"})
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Server returned status {response.status_code}",
                }
            ),
            400,
        )
    except requests.exceptions.RequestException as exc:
        return jsonify({"status": "error", "message": f"Connection error: {exc!s}"}), 400
    except Exception as exc:
        logger.exception("Unexpected error during connection test")
        return jsonify({"status": "error", "message": f"Server error: {exc!s}"}), 500


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
    start_index = 0
    limit = 200

    while True:
        params: dict[str, str | int] = {
            "StartIndex": start_index,
            "Limit": limit,
        }
        if extra_params:
            params.update(extra_params)
        try:
            resp = requests.get(
                f"{base_url}/{endpoint}",
                headers={"X-Emby-Token": api_key},
                params=params,
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.RequestException:
            if items:
                break  # partial data is better than nothing
            raise

        data = resp.json()
        page_items = data.get("Items", [])
        items.extend(page_items)

        if len(page_items) < limit:
            break
        start_index += limit

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
    config_result = _get_jellyfin_config()
    if len(config_result) == 2 and isinstance(config_result[1], int):
        return config_result
    url, api_key = config_result

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
                except Exception:
                    logger.warning("Failed to process metadata key %r", key, exc_info=True)
                    result[key] = []
                    failed += 1

        if failed >= len(futures):
            return jsonify({"status": "error", "message": "Failed to fetch metadata from Jellyfin"}), 400

        return jsonify({"status": "success", "metadata": result})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


# ---------------------------------------------------------------------------
# Jellyfin users
# ---------------------------------------------------------------------------


@bp.route("/api/jellyfin/users", methods=["GET"])
def get_jellyfin_users() -> ResponseReturnValue:
    """Return a list of users from Jellyfin.

    Returns:
        JSON with ``status`` and a ``users`` object containing ``id`` and ``name``.
    """
    config_result = _get_jellyfin_config()
    if len(config_result) == 2 and isinstance(config_result[1], int):
        return config_result
    url, api_key = config_result

    try:
        users_list = get_users(url, api_key)
        return jsonify(
            {
                "status": "success",
                "users": [{"id": u.get("Id"), "name": u.get("Name")} for u in users_list],
            }
        )
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@bp.route("/api/upload_cover", methods=["POST"])
def upload_cover() -> ResponseReturnValue:
    """Save a base64-encoded cover image for a group.

    Expects a JSON body with ``group_name`` and ``image`` (data URL).
    Decodes and saves the image to a location determined by
    :func:`sync.get_cover_path`: it saves to
    ``target_base/.covers/[md5(group_name)].jpg`` when the target directory
    exists, otherwise it falls back to ``config/covers/[md5(group_name)].jpg``.
    The file name used is md5(group_name) + .jpg. Reference
    :func:`sync.get_cover_path` for the detailed storage precedence.

    Returns:
        JSON with ``status`` and ``message``.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    group_name = data.get("group_name")
    image_data = data.get("image")
    if not isinstance(group_name, str) or not isinstance(image_data, str):
        return jsonify({"status": "error", "message": "group_name and image must be strings"}), 400

    if not image_data.startswith("data:image/"):
        return jsonify({"status": "error", "message": "Invalid image format"}), 400

    try:
        _header, encoded = image_data.split(",", 1)

        if len(encoded) > MAX_B64_SIZE:
            return (
                jsonify({"status": "error", "message": "Payload too large"}),
                413,
            )

        decoded = base64.b64decode(encoded)

        # Determine cover storage path using the shared helper
        cfg = load_config()
        target_path = str(cfg.get("target_path", ""))

        cover_path = get_cover_path(group_name, target_path, check_exists=False)
        if cover_path is None:
            return jsonify(
                {"status": "error", "message": "Could not resolve cover storage path"}
            ), 500

        os.makedirs(os.path.dirname(cover_path), exist_ok=True)
        with open(cover_path, "wb") as f:
            f.write(decoded)

        return jsonify({"status": "success", "message": "Cover saved successfully"})
    except Exception as exc:
        logger.exception("Failed to save cover image")
        return jsonify({"status": "error", "message": f"Server error: {exc!s}"}), 500


def _run_sync_handler(dry_run: bool = False) -> ResponseReturnValue:
    """Run sync (or preview) and return a JSON response."""
    try:
        config: dict[str, Any] = load_config()
        sync_results = run_sync(config, dry_run=dry_run)
        if dry_run:
            return jsonify(
                {
                    "status": "success",
                    "message": "Preview generated successfully",
                    "results": sync_results,
                }
            )
        return jsonify(
            {
                "status": "success",
                "message": "Synchronization complete",
                "results": sync_results,
            }
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": f"{exc!s}"}), 400
    except (RuntimeError, OSError) as exc:
        prefix = "Sync preview failed" if dry_run else "Sync failed"
        return jsonify({"status": "error", "message": f"{prefix}: {exc!s}"}), 500


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
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    config_result = _get_jellyfin_config()
    if len(config_result) == 2 and isinstance(config_result[1], int):
        return config_result
    url, api_key = config_result

    # Validate and normalize "type"
    type_raw = data.get("type")
    if not isinstance(type_raw, str):
        return jsonify({"status": "error", "message": "Missing or invalid 'type'"}), 400

    type_name = type_raw.lower().strip()
    allowed_types = {"genre", "studio", "tag", "year", "actor", "general", "complex"}
    if not type_name or type_name not in allowed_types:
        return (
            jsonify({"status": "error", "message": f"Invalid metadata type: {type_raw}"}),
            400,
        )

    # Validate value
    val_raw = data.get("value")
    if not isinstance(val_raw, str):
        return jsonify({"status": "error", "message": "Value must be a string"}), 400

    val = val_raw.strip()
    if not val:
        return jsonify({"status": "error", "message": "Value cannot be empty"}), 400

    watch_state = data.get("watch_state", "").strip().lower()

    try:
        # Resolve items using the public sync API
        items, error, status_code = preview_group(type_name, val, url, api_key, watch_state)

        if error is not None:
            return jsonify({"status": "error", "message": error}), status_code

        # Return summary count and first few items
        results = [
            {"Name": i.get("Name", "Unknown"), "Year": i.get("ProductionYear", "")}
            for i in items[:15]
        ]

        return jsonify({"status": "success", "count": len(items), "preview_items": results})
    except (ValueError, RuntimeError, requests.exceptions.RequestException) as exc:
        logger.exception("Failed to generate grouping preview")
        return jsonify({"status": "error", "message": f"Preview failed: {exc!s}"}), 500
    except Exception as exc:
        logger.exception("Unexpected error in grouping preview")
        return jsonify({"status": "error", "message": f"Internal server error: {exc!s}"}), 500


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@bp.route("/api/cleanup", methods=["GET"])
def get_cleanup_items() -> ResponseReturnValue:
    """Return a list of logical folders in the target directory."""
    config: dict[str, Any] = load_config()
    target_base: str = str(config.get("target_path", ""))
    if not target_base or not os.path.exists(target_base):
        return jsonify({"status": "success", "items": []})

    configured_groups: set[str] = {str(g.get("name")) for g in config.get("groups", []) if g.get("name")}

    try:
        entries: list[dict[str, Any]] = []
        for name in os.listdir(target_base):
            path = os.path.join(target_base, name)
            if os.path.isdir(path) and not name.startswith("."):
                entries.append({
                    "name": name,
                    "is_configured": name in configured_groups
                })
        return jsonify({"status": "success", "items": sorted(entries, key=lambda x: str(x["name"]))})
    except OSError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@bp.route("/api/cleanup", methods=["POST"])
def perform_cleanup() -> ResponseReturnValue:
    """Delete the selected folders from the target directory."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    folders = data.get("folders", [])
    if not isinstance(folders, list):
        return jsonify({"status": "error", "message": "'folders' must be a list"}), 400

    config: dict[str, Any] = load_config()
    target_base: str = str(config.get("target_path", ""))
    if not target_base or not os.path.exists(target_base):
        return jsonify({"status": "error", "message": "Target path not found"}), 404

    deleted: int = 0
    errors: list[str] = []
    for name in folders:
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name == ".." or name == ".":
            errors.append(f"Invalid folder name: {name}")
            continue

        path = os.path.join(target_base, name)
        if os.path.exists(path) and os.path.isdir(path):
            try:
                import shutil
                shutil.rmtree(path)
                deleted += 1

                # Also delete from Jellyfin if configured
                if config.get("auto_create_libraries"):
                    url = str(config.get("jellyfin_url", "")).rstrip("/")
                    api_key = str(config.get("api_key", ""))
                    if url and api_key:
                        try:
                            delete_virtual_folder(url, api_key, name)
                        except Exception as e:
                            logger.warning("Failed to delete Jellyfin library '%s': %s", name, e)
            except OSError as exc:
                errors.append(f"Failed to delete {name}: {exc}")

    if errors:
        return jsonify({"status": "partial_success", "deleted": deleted, "errors": errors}), 207
    return jsonify({"status": "success", "deleted": deleted})


# ---------------------------------------------------------------------------
# Auto-detect paths
# ---------------------------------------------------------------------------


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
    config_result = _get_jellyfin_config(
        missing_msg="Server settings required for detection"
    )
    if len(config_result) == 2 and isinstance(config_result[1], int):
        return config_result
    url, api_key = config_result

    try:
        items = fetch_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
                "Limit": "10",
                "Fields": "Path",
            },
            timeout=10,
        )
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    if not items:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "No media found in Jellyfin to detect paths",
                }
            ),
            400,
        )

    # Walk limits: max 30 seconds, max 50 000 files scanned
    _WALK_TIMEOUT = 30
    _WALK_MAX_FILES = 50_000

    home_dir: str = os.path.expanduser("~")
    detected_j_root: str | None = None
    detected_h_root: str | None = None

    for item in items:
        j_path: str | None = item.get("Path")
        if not j_path:
            continue

        filename: str = os.path.basename(j_path)
        search_roots: list[str] = [home_dir, "/media", "/mnt"]

        match_found: str | None = None
        walk_start = time.time()
        files_scanned = 0
        for root in search_roots:
            if not os.path.isdir(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                # Skip mount points and remote filesystems
                if os.path.ismount(dirpath) and dirpath != root:
                    dirnames.clear()
                    continue
                # Timeout check
                if time.time() - walk_start > _WALK_TIMEOUT:
                    logger.warning("auto-detect timed out after %ds, %d files scanned", _WALK_TIMEOUT, files_scanned)
                    dirnames.clear()
                    break
                # File count limit
                files_scanned += len(filenames)
                if files_scanned > _WALK_MAX_FILES:
                    logger.warning("auto-detect hit file limit (%d), stopping scan", _WALK_MAX_FILES)
                    dirnames.clear()
                    break

                if filename in filenames:
                    match_found = os.path.join(dirpath, filename)
                    break
                # Prune traversal deeper than 6 path components
                if len(dirpath.split(os.sep)) > 6:
                    dirnames.clear()
            if match_found:
                break

        if match_found:
            j_parts: list[str] = j_path.split(os.sep)
            h_parts: list[str] = match_found.split(os.sep)

            # Count how many trailing path components are identical
            common_count: int = 0
            while (
                common_count < len(j_parts)
                and common_count < len(h_parts)
                and j_parts[-(common_count + 1)] == h_parts[-(common_count + 1)]
            ):
                common_count += 1

            if common_count > 0:
                detected_j_root = os.sep.join(j_parts[:-common_count]) or os.sep
                detected_h_root = os.sep.join(h_parts[:-common_count]) or os.sep
                break

    suggested_target: str = os.path.join(home_dir, "jellyfin-groupings-virtual")

    return jsonify(
        {
            "status": "success",
            "detected": {
                "media_path_in_jellyfin": detected_j_root,
                "media_path_on_host": detected_h_root,
                "target_path": suggested_target,
                "target_path_in_jellyfin": suggested_target,
            },
        }
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
    path: str = os.path.abspath(raw) if raw else os.path.expanduser("~")

    # Fall back to parent if the supplied path resolves to a file
    if not os.path.isdir(path):
        path = os.path.dirname(path)

    if not _path_is_allowed(path):
        return (
            jsonify({"status": "error", "message": "Access to this path is not permitted"}),
            403,
        )

    try:
        entries: list[str] = sorted(
            name
            for name in os.listdir(path)
            if os.path.isdir(os.path.join(path, name)) and not name.startswith(".")
        )
    except PermissionError:
        entries = []
    except OSError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    parent: str | None = os.path.dirname(path) if path != os.sep else None

    return jsonify(
        {
            "status": "success",
            "current": path,
            "parent": parent,
            "dirs": entries,
        }
    )


# ---------------------------------------------------------------------------
# Test Dashboard
# ---------------------------------------------------------------------------


@bp.route("/api/test/results", methods=["GET"])
def get_test_results() -> ResponseReturnValue:
    """Return the contents of the latest test output logs."""
    results = {}
    for filename in ["test_results.txt", "current_test_out.txt", "test_api_out.txt"]:
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    results[filename] = f.read()
            except Exception:
                results[filename] = "Error reading file."
        else:
            results[filename] = "No output found."

    return jsonify({"status": "success", "results": results})


@bp.route("/api/test/run", methods=["POST"])
def run_tests() -> ResponseReturnValue:
    """Trigger the test suite programmatically. Only available in debug mode."""
    from flask import current_app
    if not current_app.debug:
        return jsonify({"status": "error", "message": "Not available in production mode"}), 403
    import subprocess
    import sys
    try:
        subprocess.run([sys.executable, "run_tests_to_file.py"], check=False, timeout=130)
        return jsonify({"status": "success", "message": "Tests executed successfully."})
    except Exception as exc:
        logger.exception("Failed to run test suite")
        return jsonify({"status": "error", "message": str(exc)}), 500


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


@bp.route("/")
def index() -> ResponseReturnValue:
    """Serve the single-page frontend.

    Returns:
        The rendered ``templates/base.html`` Jinja2 template.
    """
    from flask import render_template
    return render_template("base.html")


@bp.route("/test")
def test_dashboard() -> ResponseReturnValue:
    """Serve the test dashboard frontend.

    Returns:
        The ``test.html`` file located next to ``app.py``.
    """
    return send_from_directory(".", "test.html")
