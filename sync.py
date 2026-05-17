"""sync.py - Core synchronisation logic for Jellyfin Groupings.

This module contains :func:`run_sync`, which drives the per-group loop
responsible for:

1. Fetching items from IMDb lists, Trakt lists, or directly from Jellyfin
   based on metadata filters (genre, actor, studio, tag).
2. Optionally translating Jellyfin-side media paths to equivalent host paths.
3. Cleaning and re-creating each group directory with numbered symlinks.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import threading
from datetime import datetime
from typing import Any, Callable

import requests

from anilist import fetch_anilist_list
from imdb import fetch_imdb_list
from jellyfin import (
    DEFAULT_ITEM_TYPES,
    RECURSIVE_TRUE,
    SORT_MAP,
    add_to_collection,
    add_virtual_folder,
    create_collection,
    fetch_all_jellyfin_items,
    fetch_jellyfin_items,
    find_collection_by_name,
    get_libraries,
    get_user_recent_items,
    set_collection_image,
    set_virtual_folder_image,
)
from letterboxd import fetch_letterboxd_list
from mal import fetch_mal_list
from tmdb import fetch_tmdb_list, get_tmdb_recommendations
from trakt import fetch_trakt_list

logger = logging.getLogger(__name__)

# Pre-compiled regex for splitting complex query logical operators.
_COMPLEX_QUERY_RE = re.compile(r"\s+(AND NOT|OR NOT|AND|OR)\s+", re.IGNORECASE)

# Source types that come from external lists (IMDb / Trakt / TMDb / AniList / MyAnimeList / Letterboxd) rather than
# from a Jellyfin metadata filter.
_LIST_SOURCES: frozenset[str] = frozenset(
    {"imdb_list", "trakt_list", "tmdb_list", "anilist_list", "mal_list", "letterboxd_list", "recommendations"}
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
        "recommendations_list_order",
    }
)

# Jellyfin API page size for full-library fetches
_FULL_LIBRARY_PAGE_SIZE: int = 500

# Maximum items to include in a dry-run preview
_MAX_PREVIEW_ITEMS: int = 100

# Minimum width for numbered symlink prefixes
_MIN_PREFIX_WIDTH: int = 4

# Jellyfin filter-parameter mapping for metadata group lookups
_METADATA_FILTER_MAP: dict[str, str] = {
    "genre": "Genres",
    "actor": "Person",
    "studio": "Studios",
    "tag": "Tags",
    "year": "years",
}

# Jellyfin Fields parameter for full-library fetches
_FULL_LIBRARY_FIELDS: str = (
    "Path,ProviderIds,Genres,Studios,Tags,People,ProductionYear,CommunityRating,UserData"
)

# Jellyfin API timeout for full-library fetches (seconds)
_FULL_LIBRARY_TIMEOUT: int = 30

# Jellyfin API timeout for metadata group fetches (seconds)
_METADATA_FETCH_TIMEOUT: int = 30


def _build_preview_item(item: dict[str, Any], file_name: str | None = None) -> dict[str, Any]:
    """Build a preview dict from a Jellyfin item."""
    preview: dict[str, Any] = {
        "Name": item.get("Name", "Unknown"),
        "Year": item.get("ProductionYear", ""),
    }
    if file_name is not None:
        preview["FileName"] = file_name
    return preview

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
    if jellyfin_root and host_root:
        try:
            normalized_root = os.path.normpath(jellyfin_root)
            normalized_path = os.path.normpath(jellyfin_path)
            if os.path.commonpath([normalized_path, normalized_root]) == normalized_root:
                rel = os.path.relpath(normalized_path, normalized_root)
                return os.path.normpath(os.path.join(host_root, rel))
        except ValueError:
            pass
    return jellyfin_path


def _get_cover_path(group_name: str, target_base: str, check_exists: bool = True) -> str | None:
    """Compute the expected cover image path for a group, resolving storage priority.

    Priority:
    1. Library-local .covers/ directory (new storage location).
    2. Internal config/covers/ directory (legacy storage location).

    Args:
        group_name: The human-readable name of the group.
        target_base: The root library directory where .covers/ resides.
        check_exists: If True, return None if the file doesn't exist on disk.
            If False, return the prioritized path regardless of existence (useful for saving).

    Returns:
        The absolute path to the cover image, or None if not found/possible.
    """
    safe_name = hashlib.md5(group_name.encode("utf-8"), usedforsecurity=False).hexdigest()

    # Priority 1: Library-local .covers/ directory (new storage location)
    lib_cover_path = os.path.join(target_base, ".covers", f"{safe_name}.jpg")

    # Priority 2: Internal config/covers/ directory (legacy storage location)
    legacy_cover_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config", "covers", f"{safe_name}.jpg"
    )

    if not check_exists:
        # If we are just resolving where to SAVE, we prefer the library-local path if target_base exists
        if target_base and os.path.isdir(target_base):
            return lib_cover_path
        return legacy_cover_path

    if os.path.exists(lib_cover_path):
        return lib_cover_path
    if os.path.exists(legacy_cover_path):
        return legacy_cover_path

    return None


_LIBRARY_CACHE: dict[tuple[str, str], list[dict[str, Any]]] = {}
_LIBRARY_CACHE_LOCK = threading.RLock()


def _filter_by_watch_state(
    items: list[dict[str, Any]], watch_state: str
) -> list[dict[str, Any]]:
    """Filter *items* by Jellyfin watch state.

    Args:
        items: Jellyfin item dicts (must contain ``UserData.Played``).
        watch_state: ``"unwatched"``, ``"watched"``, or any other value
            (which returns the list unchanged).

    Returns:
        The filtered list.
    """
    if watch_state == "unwatched":
        return [i for i in items if not i.get("UserData", {}).get("Played")]
    if watch_state == "watched":
        return [i for i in items if i.get("UserData", {}).get("Played")]
    return items


def _fetch_full_library(
    url: str,
    api_key: str,
    group_name: str,
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Fetch the full Jellyfin library once per run for matching.

    Args:
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        group_name: Human-readable group name (used for logging).

    Returns:
        A (raw_items, error, status_code) tuple.
    """
    cache_key = (url, api_key)
    with _LIBRARY_CACHE_LOCK:
        if cache_key in _LIBRARY_CACHE:
            return _LIBRARY_CACHE[cache_key].copy(), None, 200

    try:
        all_items = fetch_all_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": RECURSIVE_TRUE,
                "Fields": _FULL_LIBRARY_FIELDS,
                "IncludeItemTypes": DEFAULT_ITEM_TYPES,
            },
            limit=_FULL_LIBRARY_PAGE_SIZE,
            timeout=_FULL_LIBRARY_TIMEOUT,
            _fetch_page=fetch_jellyfin_items,
        )
        logger.info("Jellyfin library: %s items fetched for matching", len(all_items))
        with _LIBRARY_CACHE_LOCK:
            _LIBRARY_CACHE[cache_key] = all_items
        return all_items, None, 200
    except (RuntimeError, OSError, ValueError) as exc:
        logger.error("Infrastructure error fetching Jellyfin library for group %r: %s", group_name, exc)
        return [], f"Jellyfin connection error: {exc!s}", 500


def _match_jellyfin_items_by_provider(
    external_ids: list[Any],
    provider_key: str,
    list_order_key: str,
    sort_order: str,
    url: str,
    api_key: str,
    group_name: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Fetch all Jellyfin items and match them against a list of external IDs.

    Args:
        external_ids: List of IDs from the external provider (IMDb, TMDb, etc.).
        provider_key: The Jellyfin ProviderId key (e.g. "Imdb", "Tmdb").
        list_order_key: The sort_order value that triggers list-order sorting.
        sort_order: The group's requested sort_order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        group_name: Group name for logging.
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A (items, error, status_code) tuple.
    """
    raw_items, error, status_code = _fetch_full_library(url, api_key, group_name)
    if error is not None:
        return [], error, status_code

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

    items = _filter_by_watch_state(items, watch_state)

    return items, None, 200


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
        """Sorting key - pushes items missing the field to the end.

        The *missing* component is set so that tuples for absent values are
        always larger than tuples for present values, regardless of whether
        the overall sort is ascending or descending.
        """
        value = item.get(primary_key)
        # For ascending (reverse=False): missing=1 > present=0  → end
        # For descending (reverse=True):  missing=0 < present=1 → end (smallest after reversal)
        missing = (1 if value is None else 0) if not reverse else (0 if value is None else 1)
        return (missing, value or "")

    return sorted(items, key=_key, reverse=reverse)


def _fetch_and_resolve(
    group_name: str,
    fetch_fn: Callable[[], list[Any]],
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str,
    provider_key: str,
    list_order_key: str,
    source_label: str,
    log_msg_fn: Callable[[int], str],
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Fetch external IDs via *fetch_fn*, then match against the Jellyfin library.

    Args:
        group_name: Human-readable group name.
        fetch_fn: Callable that returns a list of external IDs.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional filter for watch state.
        provider_key: The Jellyfin ProviderId key.
        list_order_key: The sort_order value that triggers list-order sorting.
        source_label: Label used in error messages (e.g. ``"IMDb"``).
        log_msg_fn: Callable that receives the item count and returns the
            fully-formatted log message.

    Returns:
        A ``(items, error, status_code)`` tuple.
    """
    try:
        external_ids = fetch_fn()
        logger.info(log_msg_fn(len(external_ids)))
    except (requests.exceptions.RequestException, RuntimeError, ValueError) as exc:
        logger.error("Error fetching %s list for group %r: %s", source_label, group_name, exc)
        return [], f"{source_label} fetch error: {exc!s}", 400

    if not external_ids:
        logger.info("No items found in %s list for group %r", source_label, group_name)
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        external_ids, provider_key, list_order_key, sort_order, url, api_key, group_name, watch_state
    )


def _fetch_items_for_imdb_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for an IMDb-list-backed group."""
    return _fetch_and_resolve(
        group_name,
        lambda: fetch_imdb_list(source_value),
        sort_order,
        url,
        api_key,
        watch_state,
        "Imdb",
        "imdb_list_order",
        "IMDb",
        lambda count: f"IMDb list {source_value!r}: {count} IDs found",
    )


def _fetch_items_for_trakt_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    trakt_client_id: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a Trakt-list-backed group."""
    if not trakt_client_id:
        msg = "Trakt Client ID not set — add trakt_client_id in Server Settings"
        logger.info("No Trakt Client ID configured for group %r", group_name)
        return [], msg, 400

    return _fetch_and_resolve(
        group_name,
        lambda: fetch_trakt_list(source_value, trakt_client_id),
        sort_order,
        url,
        api_key,
        watch_state,
        "Imdb",
        "trakt_list_order",
        "Trakt",
        lambda count: f"Trakt list {source_value!r}: {count} IMDb IDs found",
    )


def _fetch_items_for_tmdb_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    tmdb_api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a TMDb-list-backed group."""
    if not tmdb_api_key:
        msg = "TMDb API Key not set — add tmdb_api_key in Server Settings"
        logger.info("No TMDb API Key configured for group %r", group_name)
        return [], msg, 400

    return _fetch_and_resolve(
        group_name,
        lambda: fetch_tmdb_list(source_value, tmdb_api_key),
        sort_order,
        url,
        api_key,
        watch_state,
        "Tmdb",
        "tmdb_list_order",
        "TMDb",
        lambda count: f"TMDb list {source_value!r}: {count} items found",
    )


def _fetch_items_for_anilist_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for an AniList-list-backed group."""
    username = source_value
    status = None
    if "/" in source_value:
        username, status = source_value.split("/", 1)

    return _fetch_and_resolve(
        group_name,
        lambda: fetch_anilist_list(username, status),
        sort_order,
        url,
        api_key,
        watch_state,
        "AniList",
        "anilist_list_order",
        "AniList",
        lambda count: f"AniList user {username!r} (status={status!r}): {count} items found",
    )


def _fetch_items_for_mal_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    mal_client_id: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a MyAnimeList-list-backed group."""
    if not mal_client_id:
        msg = "MyAnimeList Client ID not set — add mal_client_id in Server Settings"
        logger.info("No MAL Client ID configured for group %r", group_name)
        return [], msg, 400

    username = source_value
    status = None
    if "/" in source_value:
        username, status = source_value.split("/", 1)

    return _fetch_and_resolve(
        group_name,
        lambda: fetch_mal_list(username, mal_client_id, status),
        sort_order,
        url,
        api_key,
        watch_state,
        "Mal",
        "mal_list_order",
        "MAL",
        lambda count: f"MyAnimeList user {username!r} (status={status!r}): {count} items found",
    )


def _fetch_items_for_letterboxd_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a Letterboxd-list-backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: Letterboxd list URL.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A ``(items, error, status_code)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    try:
        external_ids = fetch_letterboxd_list(source_value)
        logger.info("Letterboxd list %r: %s IDs found", source_value, len(external_ids))
    except (requests.exceptions.RequestException, RuntimeError, ValueError) as exc:
        logger.error("Error fetching Letterboxd items for group %r: %s", group_name, exc)
        return [], f"Letterboxd fetch error: {exc!s}", 400

    if not external_ids:
        logger.info("No items found in Letterboxd list for group %r", group_name)
        return [], None, 200

    # Letterboxd IDs can be IMDb (tt...) or TMDb (numeric)
    # Filter them properly
    raw_items, error, status_code = _fetch_full_library(url, api_key, group_name)
    if error is not None:
        return [], error, status_code

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

    items = []
    if sort_order == "letterboxd_list_order":
        for eid in external_ids:
            match = None
            if str(eid).startswith("tt"):
                match = items_by_imdb.get(str(eid).lower())
            else:
                match = items_by_tmdb.get(str(eid))
            if match:
                items.append(match)
    else:
        seen_jf_ids = set()
        for eid in external_ids:
            match = None
            if str(eid).startswith("tt"):
                match = items_by_imdb.get(str(eid).lower())
            else:
                match = items_by_tmdb.get(str(eid))
            if match and match["Id"] not in seen_jf_ids:
                items.append(match)
                seen_jf_ids.add(match["Id"])

    items = _filter_by_watch_state(items, watch_state)

    return items, None, 200


def _fetch_items_for_recommendations_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    tmdb_api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a User Recommendations group.

    Args:
        group_name: Human-readable group name.
        source_value: Jellyfin User ID.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        tmdb_api_key: TMDb API Key.
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A ``(items, error, status_code)`` tuple.
    """
    if not tmdb_api_key:
        msg = "TMDb API Key not set — add tmdb_api_key in Server Settings"
        logger.info("No TMDb API Key configured for recommendations group %r", group_name)
        return [], msg, 400

    if not source_value:
        return [], "User ID must be selected for recommendations", 400

    user_id = source_value
    try:
        # Fetch user's recent items from Jellyfin
        recent_items = get_user_recent_items(url, api_key, user_id, limit=20)

        # Extract TMDb IDs and Media Type
        tmdb_requests = []
        for item in recent_items:
            tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
            item_type = item.get("Type")
            if tmdb_id and item_type in ("Movie", "Series"):
                media_type = "movie" if item_type == "Movie" else "tv"
                tmdb_requests.append((str(tmdb_id), media_type))

        if not tmdb_requests:
            logger.info("No TMDb IDs found in recent items for user %r", user_id)
            return [], None, 200

        # Fetch recommendations based on these items
        tmdb_ids = get_tmdb_recommendations(tmdb_requests, tmdb_api_key)
        logger.info("TMDb recommendations: %s items found", len(tmdb_ids))
    except (requests.exceptions.RequestException, RuntimeError, ValueError) as exc:
        logger.error("Error fetching recommendations for group %r: %s", group_name, exc)
        return [], f"Recommendations fetch error: {exc!s}", 400

    if not tmdb_ids:
        logger.info("No items found in TMDb recommendations for group %r", group_name)
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        tmdb_ids, "Tmdb", "recommendations_list_order", sort_order, url, api_key, group_name, watch_state
    )


def _match_condition(item: dict[str, Any], r_type: str, r_val: str) -> bool:
    """Check if a Jellyfin item matches a single rule condition.

    Args:
        item: The Jellyfin item dictionary.
        r_type: The rule type (genre, actor, studio, tag, year).
        r_val: The normalized rule value to match against.

    Returns:
        True if the item matches the condition, False otherwise.
    """
    if not r_type or not r_val:
        return False

    try:
        if r_type == "genre":
            return any(r_val == str(g).strip().lower() for g in (item.get("Genres") or []))
        if r_type == "actor":
            return any(
                r_val == str(p.get("Name", "")).strip().lower()
                for p in (item.get("People") or [])
                if isinstance(p, dict) and p.get("Type") == "Actor"
            )
        if r_type == "studio":
            return any(
                r_val == str(s.get("Name", "")).strip().lower()
                for s in (item.get("Studios") or [])
                if isinstance(s, dict)
            )
        if r_type == "tag":
            return any(r_val == str(t).strip().lower() for t in (item.get("Tags") or []))
        if r_type == "year":
            val = item.get("ProductionYear")
            if val is not None:
                return str(val).strip().lower() == r_val
    except (AttributeError, TypeError, ValueError):
        pass

    return False


def _eval_item(item: dict[str, Any], rules: list[dict[str, Any]]) -> bool:
    """Evaluate a stacked list of rules against a single Jellyfin item.

    Args:
        item: The Jellyfin item dictionary.
        rules: List of parsed rules.

    Returns:
        True if the item passes the entire rule set, False otherwise.
    """
    if not rules:
        return True

    first_rule = rules[0]
    # Treat the first rule as initializing the boolean state
    result = _match_condition(item, first_rule["type"], first_rule["value"])

    # If the very first rule is NOT, we invert it (so we start with everything else)
    if first_rule["operator"].endswith("NOT"):
        result = not result

    for rule in rules[1:]:
        op = rule["operator"]
        matched = _match_condition(item, rule["type"], rule["value"])

        if op == "AND":
            result = result and matched
        elif op == "OR":
            result = result or matched
        elif op in ("AND NOT", "NOT"):
            result = result and not matched
        elif op == "OR NOT":
            result = result or not matched

    return result


def _fetch_items_for_complex_group(
    group_name: str,
    rules: list[dict[str, Any]],
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items by evaluating a stacked list of rules.

    Args:
        group_name: Human-readable group name.
        rules: List of rule dicts (operator, type, value).
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A ``(items, error, status_code)`` tuple.
    """
    raw_items, error, status_code = _fetch_full_library(url, api_key, group_name)
    if error is not None:
        return [], error, status_code

    if not rules:
        return [], None, 200

    valid_rules: list[dict[str, str]] = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        try:
            r_t = str(r.get("type", "")).strip().lower()
            r_v = str(r.get("value", "")).strip().lower()
            r_o = str(r.get("operator", "AND")).strip().upper()
            if r_t and r_v:
                valid_rules.append({"operator": r_o, "type": r_t, "value": r_v})
        except (TypeError, ValueError, AttributeError) as exc:
            logger.debug("Skipping malformed rule %s: %s", r, exc)
            continue

    if not valid_rules:
        return [], None, 200

    filtered = [item for item in raw_items if _eval_item(item, valid_rules)]

    filtered = _filter_by_watch_state(filtered, watch_state)

    # In-memory sorting because this is local filtering
    sorted_items = _sort_items_in_memory(filtered, sort_order)

    return sorted_items, None, 200


def _fetch_items_for_metadata_group(
    group_name: str,
    source_type: str | None,
    source_value: str | None,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a metadata-filter-backed group.

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
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A ``(items, error, status_code)`` tuple.
    """
    params: dict[str, str] = {
        "Recursive": RECURSIVE_TRUE,
        "Fields": "Path",
        "IncludeItemTypes": DEFAULT_ITEM_TYPES,
    }

    if source_type in _METADATA_FILTER_MAP and source_value:
        params[_METADATA_FILTER_MAP[source_type]] = source_value

    if watch_state == "unwatched":
        params["Filters"] = "IsUnplayed"
    elif watch_state == "watched":
        params["Filters"] = "IsPlayed"

    # Apply Jellyfin-side sorting
    if sort_order and sort_order in SORT_MAP and sort_order not in _LIST_ORDER_VALUES:
        sort_by, sort_order_dir = SORT_MAP[sort_order]
        params["SortBy"] = sort_by
        params["SortOrder"] = sort_order_dir

    try:
        items = fetch_jellyfin_items(url, api_key, params, timeout=_METADATA_FETCH_TIMEOUT)
        logger.info("Found %s potential items for group %r", len(items), group_name)
        return items, None, 200
    except (RuntimeError, OSError, ValueError) as exc:
        logger.error("Infrastructure error fetching items for group %r: %s", group_name, exc)
        return [], f"Jellyfin connection error: {exc!s}", 500


def parse_complex_query(query: str, default_type: str) -> list[dict[str, Any]]:
    """Parse a complex textual rule query into a list of structured rules.

    The query can contain logical operators like AND, OR, AND NOT, OR NOT.
    Each part of the query is assigned the *default_type* unless a specific
    type prefix (e.g., "actor:Tom Hanks") is provided.

    Args:
        query: The textual query string (e.g., "Action AND NOT Comedy").
        default_type: The metadata type to apply to each value (e.g., "genre").

    Returns:
        A list of rule dictionaries suitable for _fetch_items_for_complex_group.
    """
    parts = _COMPLEX_QUERY_RE.split(query.strip())

    rules = []

    def _parse_item(item_str: str) -> tuple[str, str]:
        if ":" in item_str:
            t, v = item_str.split(":", 1)
            t = t.strip().lower()
            if t in {"genre", "actor", "studio", "tag", "year"}:
                return t, v.strip()
        return default_type, item_str.strip()

    t0, v0 = _parse_item(parts[0])
    rules.append({
        "operator": "AND",
        "type": t0,
        "value": v0
    })

    for i in range(1, len(parts), 2):
        op = " ".join(parts[i].upper().split())
        ti, vi = _parse_item(parts[i+1])
        rules.append({
            "operator": op,
            "type": ti,
            "value": vi
        })

    return rules


def preview_group(
    type_name: str,
    val: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve items for a grouping preview.

    If the *val* contains logical operators (AND, OR, etc.), it is parsed as a
    complex query. Otherwise, it is treated as a simple metadata filter.

    Args:
        type_name: The metadata type (genre, actor, studio, tag, year).
        val: The filter value or complex query string.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.

    Returns:
        A ``(items, error, status_code)`` tuple.
    """
    if _COMPLEX_QUERY_RE.search(val):
        rules = parse_complex_query(val, type_name)
        return _fetch_items_for_complex_group("preview", rules, "", url, api_key, watch_state)
    return _fetch_items_for_metadata_group("preview", type_name, val, "", url, api_key, watch_state)


def _process_collection_group(
    group_name: str,
    items: list[dict[str, Any]],
    url: str,
    api_key: str,
    target_base: str,
    dry_run: bool,
    auto_set_library_covers: bool,
) -> dict[str, Any]:
    """Sync items into a Jellyfin Collection (Boxset) instead of creating symlinks.

    Finds or creates a collection named *group_name*, then adds all resolved
    item IDs to it.  Jellyfin ignores duplicate additions, so we do not need
    to diff against the existing membership.
    """
    item_ids = [item["Id"] for item in items if isinstance(item, dict) and item.get("Id")]
    if not item_ids:
        return {"group": group_name, "links": 0, "error": "No item IDs to add to collection"}

    if dry_run:
        preview_items = [
            _build_preview_item(item)
            for item in items[:_MAX_PREVIEW_ITEMS]
        ]
        return {"group": group_name, "links": len(item_ids), "items": preview_items}

    try:
        collection_id = find_collection_by_name(url, api_key, group_name)
        if collection_id:
            logger.info("Found existing collection %r (id=%s)", group_name, collection_id)
        else:
            collection_id = create_collection(url, api_key, group_name, item_ids)
            logger.info("Created collection %r (id=%s)", group_name, collection_id)

        add_to_collection(url, api_key, collection_id, item_ids)
        logger.info("Added %s items to collection %r", len(item_ids), group_name)
    except (RuntimeError, OSError) as exc:
        return {"group": group_name, "links": 0, "error": str(exc)}

    result: dict[str, Any] = {"group": group_name, "links": len(item_ids)}

    if auto_set_library_covers:
        source_cover = _get_cover_path(group_name, target_base)
        if source_cover and os.path.exists(source_cover):
            try:
                set_collection_image(url, api_key, collection_id, source_cover)
            except OSError as exc:
                logger.error("Failed to set collection image for %r: %s", group_name, exc)

    return result


def _auto_create_library(
    result: dict[str, Any],
    group_name: str,
    group_dir: str,
    url: str,
    api_key: str,
    dry_run: bool,
    auto_create_libraries: bool,
    links_created: int,
    existing_libraries: list[str] | None,
    target_path_in_jellyfin: str,
) -> dict[str, Any]:
    """Create a Jellyfin library for the group if configured.

    Mutates *existing_libraries* to prevent double creation in the same run.
    """
    if not dry_run and auto_create_libraries and links_created > 0 and existing_libraries is not None and group_name not in existing_libraries:
        logger.info("Creating Jellyfin library for grouping: %r", group_name)
        lib_path = os.path.join(target_path_in_jellyfin, group_name) if target_path_in_jellyfin else group_dir

        try:
            add_virtual_folder(url, api_key, group_name, [lib_path], collection_type="mixed")
            logger.info("Successfully created library %r with path %r", group_name, lib_path)
            existing_libraries.append(group_name)
        except (RuntimeError, OSError) as exc:
            logger.error("Failed to create Jellyfin library %r: %s", group_name, exc)
            result["library_error"] = str(exc)
    return result


def _auto_set_library_cover(
    group_name: str,
    source_cover: str | None,
    url: str,
    api_key: str,
    dry_run: bool,
    auto_set_library_covers: bool,
) -> None:
    """Set the library cover image via API if configured."""
    if not dry_run and auto_set_library_covers and source_cover and os.path.exists(source_cover):
        logger.info("Setting cover image for library %r via API", group_name)
        set_virtual_folder_image(url, api_key, group_name, source_cover)


def _create_group_symlinks(
    items: list[dict[str, Any]],
    group_dir: str,
    group_name: str,
    jellyfin_root: str,
    host_root: str,
    sort_order: str,
    dry_run: bool,
) -> tuple[int, list[dict[str, Any]]]:
    """Create symlinks (or preview items) for *items* inside *group_dir*.

    Returns:
        A tuple of ``(links_created, preview_items)``.
    """
    use_prefix: bool = bool(sort_order)
    width: int = max(len(str(len(items))) if items else _MIN_PREFIX_WIDTH, _MIN_PREFIX_WIDTH)
    links_created: int = 0
    preview_items: list[dict[str, Any]] = []

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue

        source_path: str | None = item.get("Path")
        if not source_path or not isinstance(source_path, str):
            logger.info("Item %s has no valid Path — skipping", item.get('Id'))
            continue

        host_path = _translate_path(source_path, jellyfin_root, host_root)
        if host_path != source_path:
            logger.info("Translated path: %s -> %s", source_path, host_path)

        if not os.path.exists(host_path):
            logger.info("Skipping (path not found on host): %s", host_path)
            continue

        file_name: str = os.path.basename(host_path)
        if use_prefix:
            file_name = f"{str(idx).zfill(width)} - {file_name}"

        dest_path: str = os.path.join(group_dir, file_name)
        if dry_run:
            if len(preview_items) < _MAX_PREVIEW_ITEMS:
                preview_items.append(_build_preview_item(item, file_name))
            links_created += 1
        else:
            try:
                os.symlink(host_path, dest_path)
                logger.info("Created symlink: %s -> %s", dest_path, host_path)
                links_created += 1
            except OSError as exc:
                logger.error("Error creating symlink %s: %s", dest_path, exc)

    if dry_run:
        logger.info("Would create %s symlinks for %r", links_created, group_name)
    else:
        logger.info("Created %s symlinks for %r", links_created, group_name)

    return links_created, preview_items


def _prepare_group_directory(
    group_dir: str,
    group_name: str,
    target_base: str,
    dry_run: bool,
) -> str | dict[str, Any]:
    """Clean up and recreate the group directory, copying a cover image if available.

    Returns:
        The path to the source cover image, or an error dict on failure.
    """
    source_cover: str | None = None
    if not dry_run:
        try:
            if os.path.exists(group_dir):
                logger.info("Cleaning existing directory: %s", group_dir)
                shutil.rmtree(group_dir)
            os.makedirs(group_dir, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to prepare group directory %r: %s", group_dir, exc)
            return {"group": group_name, "links": 0, "error": f"Directory error: {exc!s}"}

        source_cover = _get_cover_path(group_name, target_base)
        if source_cover:
            poster_dest = os.path.join(group_dir, "poster.jpg")
            try:
                shutil.copy2(source_cover, poster_dest)
                logger.info("Copied cover image from %s to %s", source_cover, poster_dest)
            except OSError as exc:
                logger.error("Failed to copy cover image: %s", exc)

    return source_cover or ""


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
    dry_run: bool = False,
    auto_create_libraries: bool = False,
    auto_set_library_covers: bool = False,
    existing_libraries: list[str] | None = None,
    target_path_in_jellyfin: str = "",
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
        dry_run: If True, do not create directories or symlinks; return matches.

    Returns:
        A result dict with keys ``"group"``, ``"links"``, optionally ``"error"``,
        and ``"items"`` (the first 100 matches) if *dry_run* is True.
    """
    group_name: str = (group.get("name") or "").strip()
    if not group_name:
        return {"group": "(unnamed)", "links": 0, "error": "Empty group name"}

    group_dir: str = os.path.join(target_base, group_name)
    sort_order: str = group.get("sort_order", "") or ""
    source_type: str | None = group.get("source_type")
    source_value: str | None = group.get("source_value")

    logger.info("Processing group: %r -> %s  (sort_order=%r)", group_name, group_dir, sort_order)

    source_cover = _prepare_group_directory(group_dir, group_name, target_base, dry_run)
    if isinstance(source_cover, dict):
        return source_cover

    # --- Resolve items ---
    error: str | None = None
    watch_state: str = group.get("watch_state", "")

    # Table-driven dispatch for external-list sources
    _source_dispatch: dict[str, Callable[[], tuple[list[dict[str, Any]], str | None, int]]] = {
        "imdb_list": lambda: _fetch_items_for_imdb_group(
            group_name, source_value or "", sort_order, url, api_key, watch_state
        ),
        "trakt_list": lambda: _fetch_items_for_trakt_group(
            group_name, source_value or "", sort_order, url, api_key, trakt_client_id, watch_state
        ),
        "tmdb_list": lambda: _fetch_items_for_tmdb_group(
            group_name, source_value or "", sort_order, url, api_key, tmdb_api_key, watch_state
        ),
        "anilist_list": lambda: _fetch_items_for_anilist_group(
            group_name, source_value or "", sort_order, url, api_key, watch_state
        ),
        "mal_list": lambda: _fetch_items_for_mal_group(
            group_name, source_value or "", sort_order, url, api_key, mal_client_id, watch_state
        ),
        "letterboxd_list": lambda: _fetch_items_for_letterboxd_group(
            group_name, source_value or "", sort_order, url, api_key, watch_state
        ),
        "recommendations": lambda: _fetch_items_for_recommendations_group(
            group_name, source_value or "", sort_order, url, api_key, tmdb_api_key, watch_state
        ),
    }

    if source_type in _source_dispatch:
        items, error, _status_code = _source_dispatch[source_type]()
    elif isinstance(group.get("rules"), list) and group["rules"]:
        rules_list = group["rules"]
        items, error, _status_code = _fetch_items_for_complex_group(
            group_name, rules_list, sort_order, url, api_key, watch_state
        )
    else:
        val_str = str(source_value or "")

        # Determine if it's a complex textual rule that needs local parsing
        if source_type in ["genre", "actor", "studio", "tag", "year"] and _COMPLEX_QUERY_RE.search(val_str):
            rules = parse_complex_query(val_str, str(source_type))
            items, error, _status_code = _fetch_items_for_complex_group(
                group_name, rules, sort_order, url, api_key, watch_state
            )
        else:
            items, error, _status_code = _fetch_items_for_metadata_group(
                group_name, source_type, source_value, sort_order, url, api_key, watch_state
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

    # --- Collection (Boxset) path ---
    if group.get("create_as_collection"):
        return _process_collection_group(
            group_name,
            items,
            url,
            api_key,
            target_base,
            dry_run,
            auto_set_library_covers,
        )

    # --- Create symlinks ---
    links_created, preview_items = _create_group_symlinks(
        items, group_dir, group_name, jellyfin_root, host_root, sort_order, dry_run
    )
    result: dict[str, Any] = {"group": group_name, "links": links_created}
    if dry_run:
        result["items"] = preview_items

    result = _auto_create_library(
        result, group_name, group_dir, url, api_key,
        dry_run, auto_create_libraries, links_created, existing_libraries, target_path_in_jellyfin,
    )
    _auto_set_library_cover(
        group_name, source_cover, url, api_key, dry_run, auto_set_library_covers,
    )

    return result


def _is_in_season(start_str: Any, end_str: Any) -> bool:
    """Check if the current date is within the seasonal window [start, end).
    Dates are in 'MM-DD' format.
    """
    if not isinstance(start_str, str) or not isinstance(end_str, str):
        return True

    now = datetime.now()
    current_md = now.strftime("%m-%d")

    s: str = start_str
    e: str = end_str

    if s <= e:
        # Simple case: window stays within one calendar year (e.g., 06-01 to 08-31)
        return s <= current_md < e
    # Over-year case: window spans across Jan 1st (e.g., 12-01 to 01-01)
    return current_md >= s or current_md < e


def run_sync(
    config: dict[str, Any], dry_run: bool = False, group_names: list[str] | None = None
) -> list[dict[str, Any]]:
    """Run the synchronisation process for configured groups.

    Iterates over groups in *config* and delegates to :func:`_process_group`.
    If *group_names* is provided, only groups with matching names are synced.
    Results are collected and returned for the caller (typically a Flask route
    handler) to serialise.

    Args:
        config: The application configuration dict as returned by
            :func:`config.load_config`.
        dry_run: Whether to perform a dry run (default: False).
        group_names: Optional list of group names to include. If None, all
            groups are included.

    Returns:
        A list of per-group result dicts, each containing at minimum
        ``"group"`` and ``"links"`` keys, and optionally ``"error"``
        and ``"items"`` (in dry run).

    Raises:
        ValueError: If the required config keys are missing or the target
            directory cannot be created.
    """
    url: str = str(config.get("jellyfin_url") or "").rstrip("/")
    api_key: str = str(config.get("api_key") or "")
    target_base: str = str(config.get("target_path") or "")
    groups: list[dict[str, Any]] = config.get("groups", [])

    jellyfin_root: str = str(
        config.get("media_path_in_jellyfin") or config.get("jellyfin_root", "")
    ).strip()
    host_root: str = str(
        config.get("media_path_on_host") or config.get("host_root", "")
    ).strip()
    trakt_client_id: str = str(config.get("trakt_client_id") or "").strip()
    tmdb_api_key: str = str(config.get("tmdb_api_key") or "").strip()
    mal_client_id: str = str(config.get("mal_client_id") or "").strip()
    auto_create_libraries: bool = bool(config.get("auto_create_libraries", False))
    auto_set_library_covers: bool = bool(config.get("auto_set_library_covers", False))
    target_path_in_jellyfin: str = str(config.get("target_path_in_jellyfin") or "").strip()

    if not url or not api_key or not target_base:
        raise ValueError("Server settings or target path not configured")

    if not dry_run:
        os.makedirs(target_base, exist_ok=True)

    logger.info("Starting sync to: %s", target_base)
    if jellyfin_root and host_root:
        logger.info("Path translation active: %s -> %s", jellyfin_root, host_root)

    existing_libraries: list[str] = []
    if auto_create_libraries:
        try:
            existing_libraries = get_libraries(url, api_key)
            logger.info("Found %s existing virtual folders in Jellyfin", len(existing_libraries))
        except (RuntimeError, OSError) as exc:
            logger.warning("Warning: Could not fetch existing libraries: %s", exc)
            # We'll continue, but library creation might fail or try to recreate existing ones
            auto_create_libraries = False

    with _LIBRARY_CACHE_LOCK:
        _LIBRARY_CACHE.clear()

    results: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            logger.info("Skipping invalid group entry: %s", group)
            continue

        name = (group.get("name") or "").strip()
        if group_names is not None and (not name or name not in group_names):
            continue

        # --- Seasonal Check ---
        if group.get("seasonal_enabled"):
            start = group.get("seasonal_start")
            end = group.get("seasonal_end")
            if not _is_in_season(start, end):
                if not dry_run and name:
                    group_dir = os.path.join(target_base, name)
                    if os.path.isdir(group_dir):
                        logger.info("Seasonal group %r is out of season. Deleting directory: %s", name, group_dir)
                        shutil.rmtree(group_dir)
                results.append({"group": name or "(unnamed)", "links": 0, "status": "out_of_season"})
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
            dry_run=dry_run,
            auto_create_libraries=auto_create_libraries,
            auto_set_library_covers=auto_set_library_covers,
            existing_libraries=existing_libraries,
            target_path_in_jellyfin=target_path_in_jellyfin,
        )
        results.append(result)

    with _LIBRARY_CACHE_LOCK:
        _LIBRARY_CACHE.clear()
    return results


def run_cleanup_broken_symlinks(config: dict[str, Any]) -> int:
    """Scan the target directory for broken symlinks and remove them.

    Args:
        config: The application configuration dict.

    Returns:
        The number of broken symlinks deleted.
    """
    target_base: str = str(config.get("target_path") or "")

    if not target_base or not os.path.isdir(target_base):
        logger.info("Cleanup aborted: invalid target base path '%s'", target_base)
        return 0

    deleted_count = 0

    for root, _dirs, files in os.walk(target_base):
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path) and not os.path.exists(path):
                # The symlink is broken
                try:
                    os.unlink(path)
                    logger.info("Deleted broken symlink: %s", path)
                    deleted_count += 1
                except OSError as exc:
                    logger.error("Error deleting broken symlink %s: %s", path, exc)

    return deleted_count
