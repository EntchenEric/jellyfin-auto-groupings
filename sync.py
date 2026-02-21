"""
sync.py – Core synchronisation logic for Jellyfin Groupings.

This module contains :func:`run_sync`, which drives the per-group loop
responsible for:

1. Fetching items from IMDb lists, Trakt lists, or directly from Jellyfin
   based on metadata filters (genre, actor, studio, tag).
2. Optionally translating Jellyfin-side media paths to equivalent host paths.
3. Cleaning and re-creating each group directory with numbered symlinks.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from anilist import fetch_anilist_list
from imdb import fetch_imdb_list
from jellyfin import SORT_MAP, fetch_jellyfin_items
from letterboxd import fetch_letterboxd_list
from mal import fetch_mal_list
from tmdb import fetch_tmdb_list
from trakt import fetch_trakt_list

# Source types that come from external lists (IMDb / Trakt / TMDb / AniList / MyAnimeList / Letterboxd) rather than
# from a Jellyfin metadata filter.
_LIST_SOURCES: frozenset[str] = frozenset(
    {"imdb_list", "trakt_list", "tmdb_list", "anilist_list", "mal_list", "letterboxd_list"}
)

# ``sort_order`` values that mean "keep the order from the external list"
# rather than applying a Jellyfin / in-memory sort.
_LIST_ORDER_VALUES: frozenset[str] = frozenset(
    {
        "imdb_list_order",
        "trakt_list_order",
        "tmdb_list_order",
        "anilist_list_order",
        "mal_list_order",
        "letterboxd_list_order",
    }
)


def _translate_path(
    jellyfin_path: str,
    jellyfin_root: str,
    host_root: str,
) -> str:
    """Translate a Jellyfin-side path to the equivalent host filesystem path.

    If *jellyfin_path* does not start with *jellyfin_root* the original path
    is returned unchanged.

    Args:
        jellyfin_path: Absolute path as reported by Jellyfin (e.g. inside a
            Docker container).
        jellyfin_root: The common prefix used by Jellyfin for media files.
        host_root: The corresponding prefix on the host running this service.

    Returns:
        The host-side absolute path.
    """
    if jellyfin_root and host_root and jellyfin_path.startswith(jellyfin_root):
        rel = os.path.relpath(jellyfin_path, jellyfin_root)
        return os.path.normpath(os.path.join(host_root, rel))
    return jellyfin_path


_LIBRARY_CACHE: dict[tuple[str, str], list[dict[str, Any]]] = {}


def _fetch_full_library(
    url: str,
    api_key: str,
    group_name: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch the full Jellyfin library once per run for matching.

    Args:
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        group_name: Human-readable group name (used for logging).

    Returns:
        A (raw_items, error) tuple.
    """
    cache_key = (url, api_key)
    if cache_key in _LIBRARY_CACHE:
        return _LIBRARY_CACHE[cache_key], None

    try:
        raw_items = fetch_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": "true",
                "Fields": "Path,ProviderIds",
                "IncludeItemTypes": "Movie,Series",
                "Limit": "10000",
            },
            timeout=60,
        )
        print(f"Jellyfin library: {len(raw_items)} items fetched for matching")
        _LIBRARY_CACHE[cache_key] = raw_items
        return raw_items, None
    except Exception as exc:
        print(f"Error fetching Jellyfin library for group {group_name!r}: {exc}")
        return [], str(exc)


def _match_jellyfin_items_by_provider(
    external_ids: list[Any],
    provider_key: str,
    list_order_key: str,
    sort_order: str,
    url: str,
    api_key: str,
    group_name: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch all Jellyfin items and match them against a list of external IDs.

    Args:
        external_ids: List of IDs from the external provider (IMDb, TMDb, etc.).
        provider_key: The Jellyfin ProviderId key (e.g. "Imdb", "Tmdb").
        list_order_key: The sort_order value that triggers list-order sorting.
        sort_order: The group's requested sort_order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        group_name: Group name for logging.

    Returns:
        A (items, error) tuple.
    """
    raw_items, error = _fetch_full_library(url, api_key, group_name)
    if error is not None:
        return [], error

    case_insensitive = provider_key == "Imdb"

    # Index by provider ID for O(1) lookup
    jf_by_provider: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        val = item.get("ProviderIds", {}).get(provider_key)
        if val:
            key = str(val).lower() if case_insensitive else str(val)
            jf_by_provider[key] = item

    if sort_order == list_order_key:
        # Preserve the external list's ordering
        items = []
        for eid in external_ids:
            key = str(eid).lower() if case_insensitive else str(eid)
            if key in jf_by_provider:
                items.append(jf_by_provider[key])
    else:
        matched_ids = {str(eid).lower() if case_insensitive else str(eid) for eid in external_ids}
        items = [v for k, v in jf_by_provider.items() if k in matched_ids]

    return items, None




def _sort_items_in_memory(
    items: list[dict[str, Any]],
    sort_order: str,
) -> list[dict[str, Any]]:
    """Sort *items* in-memory using :data:`jellyfin.SORT_MAP`.

    Used for external-list sources (IMDb / Trakt) when a non-list-order sort
    is requested, because Jellyfin cannot sort them server-side.

    Args:
        items: The matched Jellyfin items to sort.
        sort_order: One of the keys in :data:`jellyfin.SORT_MAP`.

    Returns:
        A new list sorted according to *sort_order*.
    """
    if sort_order not in SORT_MAP:
        return items

    sort_key_str, sort_dir_str = SORT_MAP[sort_order]
    primary_key = sort_key_str.split(",")[0]
    reverse = sort_dir_str.split(",")[0] == "Descending"

    def _key(item: dict[str, Any]) -> tuple[int, Any]:
        """Sorting key – pushes items missing the field to the end.

        The *missing* component is set so that tuples for absent values are
        always larger than tuples for present values, regardless of whether
        the overall sort is ascending or descending.
        """
        value = item.get(primary_key)
        # For ascending (reverse=False): missing=1 > present=0  → end
        # For descending (reverse=True):  missing=0 < present=1 → end (smallest after reversal)
        missing = 0 if value is None else 1
        if not reverse:
            missing = 1 if value is None else 0
        return (missing, value or "")

    return sorted(items, key=_key)


def _fetch_items_for_imdb_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve Jellyfin items for an IMDb-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: IMDb list ID or URL.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.

    Returns:
        A ``(items, error)`` tuple.  On success *items* is the resolved list
        and *error* is ``None``; on failure *items* is ``[]`` and *error* is
        a descriptive string.
    """
    try:
        imdb_ids = fetch_imdb_list(source_value)
        print(f"IMDb list {source_value!r}: {len(imdb_ids)} IDs found")
    except Exception as exc:
        print(f"Error fetching IMDb list for group {group_name!r}: {exc}")
        return [], str(exc)

    if not imdb_ids:
        print(f"No IMDb IDs found for group {group_name!r}")
        return [], None

    return _match_jellyfin_items_by_provider(
        imdb_ids, "Imdb", "imdb_list_order", sort_order, url, api_key, group_name
    )


def _fetch_items_for_trakt_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    trakt_client_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve Jellyfin items for a Trakt-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: Trakt list URL or ``"username/slug"`` shorthand.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        trakt_client_id: Trakt API Client ID.

    Returns:
        A ``(items, error)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    if not trakt_client_id:
        msg = "Trakt Client ID not set — add trakt_client_id in Server Settings"
        print(f"No Trakt Client ID configured for group {group_name!r}")
        return [], msg

    try:
        trakt_ids = fetch_trakt_list(source_value, trakt_client_id)
        print(f"Trakt list {source_value!r}: {len(trakt_ids)} IMDb IDs found")
    except Exception as exc:
        print(f"Error fetching Trakt list for group {group_name!r}: {exc}")
        return [], str(exc)

    if not trakt_ids:
        print(f"No items found in Trakt list for group {group_name!r}")
        return [], None

    return _match_jellyfin_items_by_provider(
        trakt_ids, "Imdb", "trakt_list_order", sort_order, url, api_key, group_name
    )


def _fetch_items_for_tmdb_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    tmdb_api_key: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve Jellyfin items for a TMDb-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: TMDb list ID or URL.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        tmdb_api_key: TMDb API Key.

    Returns:
        A ``(items, error)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    if not tmdb_api_key:
        msg = "TMDb API Key not set — add tmdb_api_key in Server Settings"
        print(f"No TMDb API Key configured for group {group_name!r}")
        return [], msg

    try:
        tmdb_ids = fetch_tmdb_list(source_value, tmdb_api_key)
        print(f"TMDb list {source_value!r}: {len(tmdb_ids)} items found")
    except Exception as exc:
        print(f"Error fetching TMDb list for group {group_name!r}: {exc}")
        return [], str(exc)

    if not tmdb_ids:
        print(f"No items found in TMDb list for group {group_name!r}")
        return [], None

    return _match_jellyfin_items_by_provider(
        tmdb_ids, "Tmdb", "tmdb_list_order", sort_order, url, api_key, group_name
    )


def _fetch_items_for_anilist_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve Jellyfin items for an AniList-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: AniList username or ``"username/status"`` shorthand.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.

    Returns:
        A ``(items, error)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    username = source_value
    status = None
    if "/" in source_value:
        split_val = source_value.split("/", 1)
        username = split_val[0]
        status = split_val[1]

    try:
        anilist_ids = fetch_anilist_list(username, status)
        print(f"AniList user {username!r} (status={status!r}): {len(anilist_ids)} items found")
    except Exception as exc:
        print(f"Error fetching AniList items for group {group_name!r}: {exc}")
        return [], str(exc)

    if not anilist_ids:
        print(f"No items found for AniList user {username!r}")
        return [], None

    return _match_jellyfin_items_by_provider(
        anilist_ids, "AniList", "anilist_list_order", sort_order, url, api_key, group_name
    )


def _fetch_items_for_mal_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    mal_client_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve Jellyfin items for a MyAnimeList-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: MAL username or ``"username/status"`` shorthand.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        mal_client_id: MyAnimeList Client ID.

    Returns:
        A ``(items, error)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    if not mal_client_id:
        msg = "MyAnimeList Client ID not set — add mal_client_id in Server Settings"
        print(f"No MAL Client ID configured for group {group_name!r}")
        return [], msg

    username = source_value
    status = None
    if "/" in source_value:
        split_val = source_value.split("/", 1)
        username = split_val[0]
        status = split_val[1]

    try:
        mal_ids = fetch_mal_list(username, mal_client_id, status)
        print(f"MyAnimeList user {username!r} (status={status!r}): {len(mal_ids)} items found")
    except Exception as exc:
        print(f"Error fetching MyAnimeList items for group {group_name!r}: {exc}")
        return [], str(exc)

    if not mal_ids:
        print(f"No items found for MyAnimeList user {username!r}")
        return [], None

    return _match_jellyfin_items_by_provider(
        mal_ids, "Mal", "mal_list_order", sort_order, url, api_key, group_name
    )


def _fetch_items_for_letterboxd_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve Jellyfin items for a Letterboxd-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: Letterboxd list URL.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.

    Returns:
        A ``(items, error)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    try:
        external_ids = fetch_letterboxd_list(source_value)
        print(f"Letterboxd list {source_value!r}: {len(external_ids)} IDs found")
    except Exception as exc:
        print(f"Error fetching Letterboxd list for group {group_name!r}: {exc}")
        return [], str(exc)

    if not external_ids:
        print(f"No items found in Letterboxd list for group {group_name!r}")
        return [], None

    # Letterboxd IDs can be IMDb (tt...) or TMDb (numeric)
    imdb_ids = [eid for eid in external_ids if str(eid).startswith("tt")]
    tmdb_ids = [eid for eid in external_ids if not str(eid).startswith("tt")]

    # We need to fetch both and merge them if the list contains both
    all_matched_items: list[dict[str, Any]] = []
    
    # We'll use a simplified version of matching here since we have two types of IDs
    raw_items, error = _fetch_full_library(url, api_key, group_name)
    if error is not None:
        return [], error

    # Index by both Imdb and Tmdb
    items_by_imdb: dict[str, dict[str, Any]] = {}
    items_by_tmdb: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        pids = item.get("ProviderIds", {})
        imdb_v = pids.get("Imdb")
        if imdb_v:
            items_by_imdb[str(imdb_v).lower()] = item
        tmdb_v = pids.get("Tmdb")
        if tmdb_v:
            items_by_tmdb[str(tmdb_v)] = item

    if sort_order == "letterboxd_list_order":
        items = []
        for eid in external_ids:
            if str(eid).startswith("tt"):
                key = str(eid).lower()
                if key in items_by_imdb:
                    items.append(items_by_imdb[key])
            else:
                key = str(eid)
                if key in items_by_tmdb:
                    items.append(items_by_tmdb[key])
    else:
        # Just gather all that match
        seen_jf_ids = set()
        items = []
        for eid in external_ids:
            match = None
            if str(eid).startswith("tt"):
                match = items_by_imdb.get(str(eid).lower())
            else:
                match = items_by_tmdb.get(str(eid))
            
            if match and match["Id"] not in seen_jf_ids:
                items.append(match)
                seen_jf_ids.add(match["Id"])

    return items, None


def _fetch_items_for_metadata_group(
    group_name: str,
    source_type: str | None,
    source_value: str | None,
    sort_order: str,
    url: str,
    api_key: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve Jellyfin items for a metadata-filter–backed group.

    Handles ``genre``, ``actor``, ``studio``, ``tag``, and unfiltered
    (general) groups.  Sorting is applied server-side via Jellyfin query
    parameters.

    Args:
        group_name: Human-readable group name (used for logging).
        source_type: One of ``"genre"``, ``"actor"``, ``"studio"``,
            ``"tag"``, or ``None`` / any other value for unfiltered.
        source_value: The filter value (e.g. the genre name).
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.

    Returns:
        A ``(items, error)`` tuple.
    """
    params: dict[str, str] = {
        "Recursive": "true",
        "Fields": "Path",
        "IncludeItemTypes": "Movie,Series",
    }

    filter_map: dict[str, str] = {
        "genre": "Genres",
        "actor": "Person",
        "studio": "Studios",
        "tag": "Tags",
    }
    if source_type in filter_map and source_value:
        params[filter_map[source_type]] = source_value

    # Apply Jellyfin-side sorting
    if sort_order and sort_order in SORT_MAP and sort_order not in _LIST_ORDER_VALUES:
        sort_by, sort_order_dir = SORT_MAP[sort_order]
        params["SortBy"] = sort_by
        params["SortOrder"] = sort_order_dir

    try:
        items = fetch_jellyfin_items(url, api_key, params, timeout=30)
        print(f"Found {len(items)} potential items for group {group_name!r}")
        return items, None
    except Exception as exc:
        print(f"Error fetching items for group {group_name!r}: {exc}")
        return [], str(exc)


def _process_group(
    group: dict[str, Any],
    target_base: str,
    url: str,
    api_key: str,
    jellyfin_root: str,
    host_root: str,
    trakt_client_id: str,
    tmdb_api_key: str,
    mal_client_id: str,
) -> dict[str, Any]:
    """Process a single grouping: fetch items, then create symlinks.

    The group directory is wiped and re-created on each run to ensure it
    reflects the current list contents.

    Args:
        group: The group configuration dictionary from ``config.json``.
        target_base: Root directory under which group directories are created.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        jellyfin_root: Jellyfin-side media path prefix (for path translation).
        host_root: Host-side media path prefix (for path translation).
        trakt_client_id: Trakt API Client ID (may be empty).
        tmdb_api_key: TMDb API Key (may be empty).
        mal_client_id: MyAnimeList Client ID (may be empty).

    Returns:
        A result dict with keys ``"group"``, ``"links"`` and optionally
        ``"error"``.
    """
    group_name: str = group.get("name", "unnamed").strip()
    if not group_name:
        return {"group": "(unnamed)", "links": 0, "error": "Empty group name"}

    group_dir: str = os.path.join(target_base, group_name)
    sort_order: str = group.get("sort_order", "") or ""
    source_type: str | None = group.get("source_type")
    source_value: str | None = group.get("source_value")

    print(f"Processing group: {group_name!r} -> {group_dir}  (sort_order={sort_order!r})")

    # Clean up and recreate the group directory
    if os.path.exists(group_dir):
        print(f"Cleaning existing directory: {group_dir}")
        shutil.rmtree(group_dir)
    os.makedirs(group_dir, exist_ok=True)

    # --- Resolve items ---
    error: str | None = None

    if source_type == "imdb_list":
        items, error = _fetch_items_for_imdb_group(
            group_name, source_value or "", sort_order, url, api_key
        )
    elif source_type == "trakt_list":
        items, error = _fetch_items_for_trakt_group(
            group_name, source_value or "", sort_order, url, api_key, trakt_client_id
        )
    elif source_type == "tmdb_list":
        items, error = _fetch_items_for_tmdb_group(
            group_name, source_value or "", sort_order, url, api_key, tmdb_api_key
        )
    elif source_type == "anilist_list":
        items, error = _fetch_items_for_anilist_group(
            group_name, source_value or "", sort_order, url, api_key
        )
    elif source_type == "mal_list":
        items, error = _fetch_items_for_mal_group(
            group_name, source_value or "", sort_order, url, api_key, mal_client_id
        )
    elif source_type == "letterboxd_list":
        items, error = _fetch_items_for_letterboxd_group(
            group_name, source_value or "", sort_order, url, api_key
        )
    else:
        items, error = _fetch_items_for_metadata_group(
            group_name, source_type, source_value, sort_order, url, api_key
        )

    if error is not None:
        return {"group": group_name, "links": 0, "error": error}

    if not items:
        return {"group": group_name, "links": 0}

    # Apply in-memory sort for external-list sources when a non-list-order
    # sort is requested (Jellyfin cannot sort external lists for us).
    if (
        source_type in _LIST_SOURCES
        and sort_order
        and sort_order not in _LIST_ORDER_VALUES
        and sort_order in SORT_MAP
    ):
        items = _sort_items_in_memory(items, sort_order)

    # --- Create symlinks ---
    use_prefix: bool = bool(sort_order)  # numbered prefix ↔ any sort order
    width: int = max(len(str(len(items))) if items else 4, 4)
    links_created: int = 0

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue

        source_path: str | None = item.get("Path")
        if not source_path or not isinstance(source_path, str):
            print(f"Item {item.get('Id')} has no valid Path — skipping")
            continue

        host_path = _translate_path(source_path, jellyfin_root, host_root)
        if host_path != source_path:
            print(f"Translated path: {source_path} -> {host_path}")

        if not os.path.exists(host_path):
            print(f"Skipping (path not found on host): {host_path}")
            continue

        file_name: str = os.path.basename(host_path)
        if use_prefix:
            file_name = f"{str(idx).zfill(width)} - {file_name}"

        dest_path: str = os.path.join(group_dir, file_name)
        try:
            os.symlink(host_path, dest_path)
            print(f"Created symlink: {dest_path} -> {host_path}")
            links_created += 1
        except OSError as exc:
            print(f"Error creating symlink {dest_path}: {exc}")

    print(f"Created {links_created} symlinks for {group_name!r}")
    return {"group": group_name, "links": links_created}


def run_sync(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the full synchronisation process for all configured groups.

    Iterates over every group in *config* and delegates to
    :func:`_process_group`.  Results are collected and returned for the
    caller (typically a Flask route handler) to serialise.

    Args:
        config: The application configuration dict as returned by
            :func:`config.load_config`.

    Returns:
        A list of per-group result dicts, each containing at minimum
        ``"group"`` and ``"links"`` keys, and optionally ``"error"``.

    Raises:
        ValueError: If the required config keys are missing or the target
            directory cannot be created.
    """
    url: str = str(config.get("jellyfin_url", "")).rstrip("/")
    api_key: str = str(config.get("api_key", ""))
    target_base: str = str(config.get("target_path", ""))
    groups: list[dict[str, Any]] = config.get("groups", [])

    jellyfin_root: str = str(
        config.get("media_path_in_jellyfin") or config.get("jellyfin_root", "")
    ).strip()
    host_root: str = str(
        config.get("media_path_on_host") or config.get("host_root", "")
    ).strip()
    trakt_client_id: str = str(config.get("trakt_client_id", "")).strip()
    tmdb_api_key: str = str(config.get("tmdb_api_key", "")).strip()
    mal_client_id: str = str(config.get("mal_client_id", "")).strip()

    if not url or not api_key or not target_base:
        raise ValueError("Server settings or target path not configured")

    if not os.path.exists(target_base):
        os.makedirs(target_base, exist_ok=True)

    print(f"Starting sync to: {target_base}")
    if jellyfin_root and host_root:
        print(f"Path translation active: {jellyfin_root} -> {host_root}")

    _LIBRARY_CACHE.clear()

    results: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            print(f"Skipping invalid group entry: {group}")
            continue
        result = _process_group(
            group,
            target_base,
            url,
            api_key,
            jellyfin_root,
            host_root,
            trakt_client_id,
            tmdb_api_key,
            mal_client_id,
        )
        results.append(result)

    _LIBRARY_CACHE.clear()
    return results
