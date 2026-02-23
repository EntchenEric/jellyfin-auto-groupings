"""
routes.py – Flask Blueprint containing all HTTP route handlers.

Every route is registered on the ``bp`` Blueprint which is imported and
registered with the Flask application in ``app.py``.  Route handlers are
intentionally thin: they validate inputs, delegate to service functions in
other modules, and serialise results back to JSON.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from collections import Counter
from typing import Any
 
import requests
from flask import Blueprint, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue

from config import load_config, save_config
from jellyfin import fetch_jellyfin_items
from scheduler import update_scheduler_jobs
from sync import get_cover_path, parse_complex_query, preview_group, run_sync

bp = Blueprint("main", __name__)

# Max size for base64 encoded cover image (approx 4MB)
MAX_B64_SIZE = 4 * 1024 * 1024

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
    try:
        save_config(new_config)
    except OSError as exc:
        logging.exception("Failed to write config file")
        return (
            jsonify({"status": "error", "message": f"Config file write failed: {exc}"}),
            500,
        )

    # Update background jobs based on new config
    try:
        update_scheduler_jobs()
    except Exception:
        logging.exception("Failed to update scheduler jobs")

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
            params={"api_key": api_key},
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
        logging.exception("Unexpected error during connection test")
        return jsonify({"status": "error", "message": f"Server error: {exc!s}"}), 500


# ---------------------------------------------------------------------------
# Jellyfin metadata
# ---------------------------------------------------------------------------


@bp.route("/api/jellyfin/metadata", methods=["GET"])
def get_jellyfin_metadata() -> ResponseReturnValue:
    """Return aggregated metadata (genres, studios, tags, actors) from Jellyfin.

    Fetches all Movies and Series from the configured Jellyfin instance and
    counts occurrences of each metadata field, returning sorted lists.

    Returns:
        JSON with ``status`` and a ``metadata`` object containing ``genre``,
        ``studio``, ``tag``, and ``actor`` lists (sorted by frequency).
    """
    config: dict[str, Any] = load_config()
    if not isinstance(config, dict):
        return jsonify({"status": "error", "message": "Invalid configuration format"}), 500

    url: str = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(config.get("api_key", ""))

    if not url or not api_key:
        return jsonify({"status": "error", "message": "Server settings not configured"}), 400

    try:
        items = fetch_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series",
                "Fields": "Genres,Studios,Tags,People",
            },
            timeout=30,
        )

        genres_counts: Counter[str] = Counter()
        studios_counts: Counter[str] = Counter()
        tags_counts: Counter[str] = Counter()
        people_counts: Counter[str] = Counter()

        for item in items:
            for g in item.get("Genres", []):
                genres_counts[g] += 1
            for s in item.get("Studios", []):
                s_name: str | None = s.get("Name")
                if s_name:
                    studios_counts[s_name] += 1
            for t in item.get("Tags", []):
                tags_counts[t] += 1
            for p in item.get("People", []):
                if p.get("Type") == "Actor":
                    p_name: str | None = p.get("Name")
                    if p_name:
                        people_counts[p_name] += 1

        return jsonify(
            {
                "status": "success",
                "metadata": {
                    "genre": [x[0] for x in genres_counts.most_common()],
                    "studio": [x[0] for x in studios_counts.most_common()],
                    "tag": [x[0] for x in tags_counts.most_common()],
                    "actor": [x[0] for x in people_counts.most_common()],
                },
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
        # get_cover_path with check_exists=False never returns None
            
        os.makedirs(os.path.dirname(cover_path), exist_ok=True)
        with open(cover_path, "wb") as f:
            f.write(decoded)

        return jsonify({"status": "success", "message": "Cover saved successfully"})
    except Exception as exc:
        logging.exception("Failed to save cover image")
        return jsonify({"status": "error", "message": f"Server error: {exc!s}"}), 500


@bp.route("/api/sync", methods=["POST"])
def sync_groupings() -> ResponseReturnValue:
    """Trigger a full synchronisation of all configured groupings.

    Reads the current configuration, delegates to :func:`sync.run_sync`, and
    returns per-group results.

    Returns:
        JSON with ``status``, a human-readable ``message``, and a ``results``
        list (one entry per group).
    """
    try:
        config: dict[str, Any] = load_config()
        sync_results = run_sync(config)
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
        return jsonify({"status": "error", "message": f"Sync failed: {exc!s}"}), 500


@bp.route("/api/sync/preview_all", methods=["POST"])
def preview_all_sync() -> ResponseReturnValue:
    """Preview a full synchronisation of all configured groupings without creating symlinks.

    Reads the current configuration, delegates to :func:`sync.run_sync` with dry_run=True,
    and returns per-group preview results.

    Returns:
        JSON with ``status``, a human-readable ``message``, and a ``results``
        list containing preview items.
    """
    try:
        config: dict[str, Any] = load_config()
        sync_results = run_sync(config, dry_run=True)
        return jsonify(
            {
                "status": "success",
                "message": "Preview generated successfully",
                "results": sync_results,
            }
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": f"{exc!s}"}), 400
    except (RuntimeError, OSError) as exc:
        return jsonify({"status": "error", "message": f"Sync preview failed: {exc!s}"}), 500


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

    config: dict[str, Any] = load_config()
    url: str = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(config.get("api_key", ""))

    if not url or not api_key:
        return jsonify({"status": "error", "message": "Server settings not configured"}), 400

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

    try:
        # Resolve items using the public sync API
        items, error, status_code = preview_group(type_name, val, url, api_key)

        if error is not None:
            return jsonify({"status": "error", "message": error}), status_code

        # Return summary count and first few items
        results = [
            {"Name": i.get("Name", "Unknown"), "Year": i.get("ProductionYear", "")}
            for i in items[:15]
        ]

        return jsonify({"status": "success", "count": len(items), "preview_items": results})
    except (ValueError, RuntimeError, requests.exceptions.RequestException) as exc:
        logging.exception("Failed to generate grouping preview")
        return jsonify({"status": "error", "message": f"Preview failed: {exc!s}"}), 500
    except Exception as exc:
        logging.exception("Unexpected error in grouping preview")
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
    config: dict[str, Any] = load_config()
    url: str = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(config.get("api_key", ""))

    if not url or not api_key:
        return (
            jsonify({"status": "error", "message": "Server settings required for detection"}),
            400,
        )

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
        for root in search_roots:
            for dirpath, dirnames, filenames in os.walk(root):
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
# Static files
# ---------------------------------------------------------------------------


@bp.route("/")
def index() -> ResponseReturnValue:
    """Serve the single-page frontend.

    Returns:
        The ``index.html`` file located next to ``app.py``.
    """
    return send_from_directory(".", "index.html")
