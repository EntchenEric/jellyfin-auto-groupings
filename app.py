from __future__ import annotations

import json
import os
import re
import requests
from collections import Counter
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue

app = Flask(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "jellyfin_url": "",
        "api_key": "",
        "target_path": "",
        "media_path_in_jellyfin": "",
        "media_path_on_host": "",
        "trakt_client_id": "",
        "groups": [],
    }
    if not os.path.exists(CONFIG_FILE):
        save_config(defaults)
        return defaults
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg: dict[str, Any] = json.load(f)
            # Ensure new keys are present for backwards compatibility
            for k, v in defaults.items():
                cfg.setdefault(k, v)
            # Migrate old key names to new ones
            migrated = False
            if cfg.get("jellyfin_root") and not cfg.get("media_path_in_jellyfin"):
                cfg["media_path_in_jellyfin"] = cfg["jellyfin_root"]
                migrated = True
            if cfg.get("host_root") and not cfg.get("media_path_on_host"):
                cfg["media_path_on_host"] = cfg["host_root"]
                migrated = True
            if migrated:
                cfg.pop("jellyfin_root", None)
                cfg.pop("host_root", None)
                save_config(cfg)
            return cfg
    except Exception:
        return defaults


def save_config(config: dict[str, Any]) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


# ---------------------------------------------------------------------------
# IMDb list scraping
# ---------------------------------------------------------------------------

def fetch_imdb_list(list_id: str) -> list[str]:
    """
    Fetch an IMDb list page and return a list of IMDb IDs (tt\\d+) in list order.
    list_id can be a full URL or just the list ID (e.g. ls000024390).
    """
    # Normalise: strip URL to plain ID
    list_id = list_id.strip()
    # Accept full URLs like https://www.imdb.com/list/ls000024390/
    match = re.search(r"ls\d+", list_id)
    if match:
        list_id = match.group(0)

    if not list_id.startswith("ls"):
        raise ValueError(f"Invalid IMDb list ID: {list_id!r}. Expected format: ls000024390")

    headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    # IMDb exports a JSON blob embedded in the page – we parse that first,
    # then fall back to raw regex over the HTML.
    ids: list[str] = []
    page: int = 1
    while True:
        url = (
            f"https://www.imdb.com/list/{list_id}/"
            f"?sort=list_order,asc&st_dt=&mode=detail&page={page}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch IMDb list page {page}: {e}")

        html: str = resp.text

        # Look for title IDs in the canonical anchor href pattern:
        # href="/title/tt1234567/"
        found: list[str] = re.findall(r'href="/title/(tt\d+)/', html)
        # De-duplicate while preserving order
        seen: set[str] = set(ids)
        for tt in found:
            if tt not in seen:
                ids.append(tt)
                seen.add(tt)

        # Check if there is a next page
        if not re.search(r'class="[^"]*next-page[^"]*"', html) and not re.search(
            r'rel="next"', html
        ):
            break

        page += 1
        if page > 20:  # Safety guard: max 20 pages (~2 000 items)
            break

    return ids


# ---------------------------------------------------------------------------
# Trakt list fetching
# ---------------------------------------------------------------------------

def fetch_trakt_list(list_url: str, client_id: str) -> list[str]:
    """
    Fetch a Trakt list and return a list of IMDb IDs (tt\\d+) in list order.
    list_url can be a full URL like https://trakt.tv/users/jane/lists/my-list
    or a shorthand \"username/list-slug\".
    """
    if not client_id:
        raise ValueError(
            "A Trakt API Client ID (trakt_client_id) is required to fetch Trakt lists."
        )

    list_url = list_url.strip()

    # Parse: accept full URL or "user/list-slug" shorthand
    # https://trakt.tv/users/{user}/lists/{slug}
    match = re.search(r"trakt\.tv/users/([^/]+)/lists/([^/?#]+)", list_url)
    username: str
    list_slug: str
    if match:
        username = match.group(1)
        list_slug = match.group(2)
    elif "/" in list_url and not list_url.startswith("http"):
        # "username/list-slug" shorthand
        parts = list_url.split("/", 1)
        username, list_slug = parts[0], parts[1]
    else:
        raise ValueError(
            f"Invalid Trakt list URL: {list_url!r}. "
            "Expected format: https://trakt.tv/users/username/lists/list-slug"
        )

    headers: dict[str, str] = {
        "trakt-api-key": client_id,
        "trakt-api-version": "2",
        "Content-Type": "application/json",
    }

    ids: list[str] = []
    page: int = 1
    while True:
        url = (
            f"https://api.trakt.tv/users/{username}/lists/{list_slug}/items"
            f"?page={page}&limit=1000"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch Trakt list page {page}: {e}")

        items: list[dict[str, Any]] = resp.json()
        if not items:
            break

        for entry in items:
            # Each entry has a "type" and then a key matching the type
            item_type: str | None = entry.get("type")  # "movie" or "show"
            media: dict[str, Any] = entry.get(item_type, {}) if item_type else {}
            imdb_id: str | None = media.get("ids", {}).get("imdb")
            if imdb_id and imdb_id not in ids:
                ids.append(imdb_id)

        # Check for more pages
        total_pages: int = int(resp.headers.get("X-Pagination-Page-Count", 1))
        if page >= total_pages:
            break
        page += 1
        if page > 50:  # Safety guard: max 50 pages (50 000 items)
            break

    return ids


# ---------------------------------------------------------------------------
# Jellyfin sort helpers
# ---------------------------------------------------------------------------

# Maps our internal sort_order keys to Jellyfin API SortBy / SortOrder params.
# "imdb_list_order", "trakt_list_order", and "" are handled separately (no Jellyfin sort).
SORT_MAP: dict[str, tuple[str, str]] = {
    "CommunityRating": ("CommunityRating", "Descending"),
    "ProductionYear": ("ProductionYear,SortName", "Descending,Ascending"),
    "SortName": ("SortName", "Ascending"),
    "DateCreated": ("DateCreated", "Descending"),
    "Random": ("Random", "Ascending"),
}


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def get_config() -> ResponseReturnValue:
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def update_config() -> ResponseReturnValue:
    new_config: dict[str, Any] = request.json  # type: ignore[assignment]
    save_config(new_config)
    return jsonify({"status": "success", "config": new_config})


@app.route("/api/test-server", methods=["POST"])
def test_server() -> ResponseReturnValue:
    data: dict[str, Any] = request.json  # type: ignore[assignment]
    url: str = str(data.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(data.get("api_key", ""))

    if not url or not api_key:
        return jsonify({"status": "error", "message": "URL and API Key are required"}), 400

    test_url = f"{url}/System/Info"
    try:
        response = requests.get(test_url, params={"api_key": api_key}, timeout=5)
        if response.status_code == 200:
            return jsonify({"status": "success", "message": "Connected to Jellyfin successfully!"})
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Server returned status {response.status_code}",
                    }
                ),
                400,
            )
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/jellyfin/metadata", methods=["GET"])
def get_jellyfin_metadata() -> ResponseReturnValue:
    config: dict[str, Any] = load_config()
    if not isinstance(config, dict):
        return jsonify({"status": "error", "message": "Invalid configuration format"}), 500

    url: str = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(config.get("api_key", ""))

    if not url or not api_key:
        return jsonify({"status": "error", "message": "Server settings not configured"}), 400

    query_params: dict[str, str] = {
        "api_key": api_key,
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Series",
        "Fields": "Genres,Studios,Tags,People",
    }
    items_url = f"{url}/Items"

    try:
        response = requests.get(items_url, params=query_params, timeout=30)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        items: list[dict[str, Any]] = data.get("Items", [])

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
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/sync", methods=["POST"])
def sync_groupings() -> ResponseReturnValue:
    import shutil

    config: dict[str, Any] = load_config()
    url: str = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(config.get("api_key", ""))
    target_base: str = str(config.get("target_path", ""))
    groups: list[dict[str, Any]] = config.get("groups", [])

    # Path translation: map media paths as Jellyfin sees them to host paths
    j_root: str = str(config.get("media_path_in_jellyfin") or config.get("jellyfin_root", "")).strip()
    h_root: str = str(config.get("media_path_on_host") or config.get("host_root", "")).strip()

    if not url or not api_key or not target_base:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Server settings or target path not configured",
                }
            ),
            400,
        )

    if not os.path.exists(target_base):
        try:
            os.makedirs(target_base, exist_ok=True)
        except Exception as e:
            return (
                jsonify(
                    {"status": "error", "message": f"Could not create target path: {str(e)}"}
                ),
                400,
            )

    sync_results: list[dict[str, Any]] = []

    try:
        print(f"Starting sync to: {target_base}")
        if j_root and h_root:
            print(f"Path translation active: {j_root} -> {h_root}")

        for group in groups:
            if not isinstance(group, dict):
                print(f"Skipping invalid group entry: {group}")
                continue

            group_name: str = group.get("name", "unnamed").strip()
            if not group_name:
                continue

            group_dir: str = os.path.join(target_base, group_name)
            sort_order: str = group.get("sort_order", "") or ""
            print(f"Processing group: {group_name} -> {group_dir}  (sort_order={sort_order!r})")

            # 1. Clean up existing symlinks in this group folder
            if os.path.exists(group_dir):
                print(f"Cleaning existing directory: {group_dir}")
                shutil.rmtree(group_dir)
            os.makedirs(group_dir, exist_ok=True)

            # 2. Resolve source items
            source_type: str | None = group.get("source_type")
            source_value: str | None = group.get("source_value")

            items: list[dict[str, Any]] = []

            if source_type == "imdb_list":
                # --- IMDb list path ---
                try:
                    imdb_ids: list[str] = fetch_imdb_list(source_value or "")
                    print(f"IMDb list {source_value!r}: {len(imdb_ids)} IDs found on page")
                except Exception as e:
                    print(f"Error fetching IMDb list for group {group_name}: {e}")
                    sync_results.append({"group": group_name, "links": 0, "error": str(e)})
                    continue

                if not imdb_ids:
                    print(f"No IMDb IDs found for group {group_name}")
                    sync_results.append({"group": group_name, "links": 0})
                    continue

                # Fetch all Movies+Series from Jellyfin with their provider IDs
                params: dict[str, str] = {
                    "api_key": api_key,
                    "Recursive": "true",
                    "Fields": "Path,ProviderIds",
                    "IncludeItemTypes": "Movie,Series",
                    "Limit": "10000",
                }
                try:
                    response = requests.get(f"{url}/Items", params=params, timeout=60)
                    response.raise_for_status()
                    all_jf_items: dict[str, dict[str, Any]] = {
                        item.get("ProviderIds", {}).get("Imdb", "").lower(): item
                        for item in response.json().get("Items", [])
                        if item.get("ProviderIds", {}).get("Imdb")
                    }
                    print(f"Jellyfin library: {len(all_jf_items)} items with IMDb IDs")
                except Exception as e:
                    print(f"Error fetching Jellyfin library for group {group_name}: {e}")
                    sync_results.append({"group": group_name, "links": 0, "error": str(e)})
                    continue

                # Match IMDb list to Jellyfin items, preserving list order
                if sort_order == "imdb_list_order":
                    # preserve the order from the IMDb list page
                    for tt in imdb_ids:
                        jf_item = all_jf_items.get(tt.lower())
                        if jf_item:
                            items.append(jf_item)
                else:
                    # Collect matched items first, then Jellyfin-sort below
                    matched_ids: set[str] = set(imdb_ids)
                    items = [v for k, v in all_jf_items.items() if k in matched_ids]

            elif source_type == "trakt_list":
                # --- Trakt list path ---
                trakt_client_id: str = str(config.get("trakt_client_id", "")).strip()
                if not trakt_client_id:
                    print(f"No Trakt Client ID configured for group {group_name}")
                    sync_results.append(
                        {
                            "group": group_name,
                            "links": 0,
                            "error": "Trakt Client ID not set — add trakt_client_id in Server Settings",
                        }
                    )
                    continue

                try:
                    trakt_ids: list[str] = fetch_trakt_list(source_value or "", trakt_client_id)
                    print(f"Trakt list {source_value!r}: {len(trakt_ids)} IMDb IDs found")
                except Exception as e:
                    print(f"Error fetching Trakt list for group {group_name}: {e}")
                    sync_results.append({"group": group_name, "links": 0, "error": str(e)})
                    continue

                if not trakt_ids:
                    print(f"No items found in Trakt list for group {group_name}")
                    sync_results.append({"group": group_name, "links": 0})
                    continue

                # Fetch all Movies+Series from Jellyfin with their provider IDs
                params = {
                    "api_key": api_key,
                    "Recursive": "true",
                    "Fields": "Path,ProviderIds",
                    "IncludeItemTypes": "Movie,Series",
                    "Limit": "10000",
                }
                try:
                    response = requests.get(f"{url}/Items", params=params, timeout=60)
                    response.raise_for_status()
                    all_jf_items = {
                        item.get("ProviderIds", {}).get("Imdb", "").lower(): item
                        for item in response.json().get("Items", [])
                        if item.get("ProviderIds", {}).get("Imdb")
                    }
                    print(f"Jellyfin library: {len(all_jf_items)} items with IMDb IDs")
                except Exception as e:
                    print(f"Error fetching Jellyfin library for group {group_name}: {e}")
                    sync_results.append({"group": group_name, "links": 0, "error": str(e)})
                    continue

                # Match Trakt list to Jellyfin items, preserving list order
                if sort_order == "trakt_list_order":
                    for tt in trakt_ids:
                        jf_item = all_jf_items.get(tt.lower())
                        if jf_item:
                            items.append(jf_item)
                else:
                    matched_ids = set(trakt_ids)
                    items = [v for k, v in all_jf_items.items() if k in matched_ids]

            else:
                # --- Jellyfin metadata path (genre, actor, studio, tag, general) ---
                params = {
                    "api_key": api_key,
                    "Recursive": "true",
                    "Fields": "Path",
                    "IncludeItemTypes": "Movie,Series",
                }

                if source_type == "genre":
                    params["Genres"] = source_value or ""
                elif source_type == "actor":
                    params["Person"] = source_value or ""
                elif source_type == "studio":
                    params["Studios"] = source_value or ""
                elif source_type == "tag":
                    params["Tags"] = source_value or ""

                # Apply Jellyfin-side sorting if requested
                if sort_order and sort_order in SORT_MAP and sort_order != "imdb_list_order":
                    sort_by, sort_order_dir = SORT_MAP[sort_order]
                    params["SortBy"] = sort_by
                    params["SortOrder"] = sort_order_dir

                try:
                    response = requests.get(f"{url}/Items", params=params, timeout=30)
                    response.raise_for_status()
                    items = response.json().get("Items", [])
                    print(f"Found {len(items)} potential items for group {group_name}")
                except Exception as e:
                    print(f"Error fetching items for group {group_name}: {e}")

            # For external list sources (IMDb/Trakt), if a Jellyfin sort is requested
            # (not list order), apply an in-memory sort on the already-matched items.
            list_sources: tuple[str, str] = ("imdb_list", "trakt_list")
            list_order_values: tuple[str, str] = ("imdb_list_order", "trakt_list_order")
            if (
                source_type in list_sources
                and sort_order
                and sort_order not in list_order_values
                and sort_order in SORT_MAP
            ):
                sort_key: str
                sort_dir: str
                sort_key, sort_dir = SORT_MAP[sort_order]
                primary_key: str = sort_key.split(",")[0]
                reverse: bool = sort_dir.split(",")[0] == "Descending"

                def _key(item: dict[str, Any]) -> tuple[int, Any]:
                    v = item.get(primary_key)
                    if v is None:
                        return (1, "")
                    return (0, v)

                items.sort(key=_key, reverse=reverse)

            # 3. Create symlinks
            use_prefix: bool = bool(sort_order)  # any non-empty sort_order → prefix filenames
            links_created: int = 0
            width: int = max(len(str(len(items))) if items else 4, 4)

            for idx, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                source_path: str | None = item.get("Path")
                if not source_path or not isinstance(source_path, str):
                    print(f"Item {item.get('Id')} has no valid Path")
                    continue

                item_j_path: str = source_path
                item_h_path: str = source_path

                if j_root and h_root and item_j_path.startswith(j_root):
                    rel: str = os.path.relpath(item_j_path, j_root)
                    item_h_path = os.path.normpath(os.path.join(h_root, rel))
                    print(f"Translated path: {item_j_path} -> {item_h_path}")

                if not os.path.exists(item_h_path):
                    print(f"Skipping (path not found on host): {item_h_path}")
                    continue

                file_name: str = os.path.basename(item_h_path)

                if use_prefix:
                    file_name = f"{str(idx).zfill(width)} - {file_name}"

                dest_path: str = os.path.join(group_dir, file_name)

                try:
                    os.symlink(item_j_path, dest_path)
                    print(f"Created symlink: {dest_path} -> {item_j_path}")
                    links_created += 1
                except OSError as e:
                    print(f"Error creating symlink {dest_path}: {e}")

            print(f"Created {links_created} symlinks for {group_name}")
            sync_results.append({"group": group_name, "links": links_created})

        return jsonify(
            {
                "status": "success",
                "message": "Synchronization complete",
                "results": sync_results,
            }
        )

    except Exception as e:
        return jsonify({"status": "error", "message": f"Sync failed: {str(e)}"}), 500


@app.route("/api/jellyfin/auto-detect-paths", methods=["POST"])
def auto_detect_paths() -> ResponseReturnValue:
    config: dict[str, Any] = load_config()
    url: str = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(config.get("api_key", ""))

    if not url or not api_key:
        return (
            jsonify({"status": "error", "message": "Server settings required for detection"}),
            400,
        )

    query_params: dict[str, str] = {
        "api_key": api_key,
        "Recursive": "true",
        "IncludeItemTypes": "Movie",
        "Limit": "10",
        "Fields": "Path",
    }
    items_url = f"{url}/Items"

    try:
        response = requests.get(items_url, params=query_params, timeout=10)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        items: list[dict[str, Any]] = data.get("Items", [])

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
                    if len(dirpath.split(os.sep)) > 6:
                        dirnames.clear()
                if match_found:
                    break

            if match_found:
                j_parts: list[str] = j_path.split(os.sep)
                h_parts: list[str] = match_found.split(os.sep)

                common_count: int = 0
                while (
                    common_count < len(j_parts)
                    and common_count < len(h_parts)
                    and j_parts[-(common_count + 1)] == h_parts[-(common_count + 1)]
                ):
                    common_count += 1

                if common_count > 0:
                    j_root_parts: list[str] = j_parts[:-common_count]
                    h_root_parts: list[str] = h_parts[:-common_count]
                    detected_j_root = os.sep.join(j_root_parts) or os.sep
                    detected_h_root = os.sep.join(h_root_parts) or os.sep
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
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# Roots that the folder browser is allowed to expose.
_BROWSE_ROOTS: tuple[str, ...] = tuple(
    os.path.realpath(r)
    for r in (os.path.expanduser("~"), "/media", "/mnt")
)


def _path_is_allowed(p: str) -> bool:
    """Return True only if *p* is at or below one of the whitelisted roots."""
    real = os.path.realpath(p)
    return any(
        real == root or real.startswith(root + os.sep)
        for root in _BROWSE_ROOTS
    )


@app.route("/api/browse", methods=["GET"])
def browse_directory() -> ResponseReturnValue:
    """Return the subdirectories of a given path for the folder picker."""
    raw: str = request.args.get("path", "")
    path: str = os.path.abspath(raw) if raw else os.path.expanduser("~")

    # Fall back to parent if the supplied path is a file, not a directory
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
    except OSError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    parent: str | None = os.path.dirname(path) if path != os.sep else None

    return jsonify(
        {
            "status": "success",
            "current": path,
            "parent": parent,
            "dirs": entries,
        }
    )


@app.route("/")
def index() -> ResponseReturnValue:
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    if not os.path.exists(CONFIG_FILE):
        save_config(
            {
                "jellyfin_url": "",
                "api_key": "",
                "target_path": "",
                "media_path_in_jellyfin": "",
                "media_path_on_host": "",
                "trakt_client_id": "",
                "groups": [],
            }
        )

    app.run(host="0.0.0.0", debug=True, port=5000)
