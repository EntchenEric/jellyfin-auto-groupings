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
import re
import shutil
import hashlib
import logging
import requests
from datetime import datetime
from typing import Any

from anilist import fetch_anilist_list
from imdb import fetch_imdb_list
from jellyfin import SORT_MAP, add_virtual_folder, fetch_jellyfin_items, get_libraries, get_user_recent_items, set_virtual_folder_image
from letterboxd import fetch_letterboxd_list
from mal import fetch_mal_list
from tmdb import fetch_tmdb_list, get_tmdb_recommendations
from trakt import fetch_trakt_list

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
                rel = os.path.relpath(jellyfin_path, jellyfin_root)
                return os.path.normpath(os.path.join(host_root, rel))
        except ValueError:
            pass
    return jellyfin_path


def get_cover_path(group_name: str, target_base: str, check_exists: bool = True) -> str | None:
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
    if cache_key in _LIBRARY_CACHE:
        return _LIBRARY_CACHE[cache_key], None, 200

    try:
        raw_items = fetch_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": "true",
                "Fields": "Path,ProviderIds,Genres,Studios,Tags,People,ProductionYear,CommunityRating,UserData",
                "IncludeItemTypes": "Movie,Series",
                "Limit": "10000",
            },
            timeout=60,
        )
        print(f"Jellyfin library: {len(raw_items)} items fetched for matching")
        _LIBRARY_CACHE[cache_key] = raw_items
        return raw_items, None, 200
    except requests.exceptions.RequestException as exc:
        print(f"Infrastructure error fetching Jellyfin library for group {group_name!r}: {exc!s}")
        return [], f"Jellyfin connection error: {exc!s}", 500
    except Exception as exc:
        logging.exception("Unexpected error fetching Jellyfin library for group %r", group_name)
        return [], f"Internal error: {exc!s}", 500  # noqa: BLE001


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

    if watch_state == "unwatched":
        items = [i for i in items if not i.get("UserData", {}).get("Played")]
    elif watch_state == "watched":
        items = [i for i in items if i.get("UserData", {}).get("Played")]

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
        """Sorting key – pushes items missing the field to the end.

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


def _fetch_items_for_imdb_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for an IMDb-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: IMDb list ID or URL.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A ``(items, error, status_code)`` tuple.  On success *items* is the resolved list
        and *error* is ``None``; on failure *items* is ``[]`` and *error* is
        a descriptive string.
    """
    try:
        imdb_ids = fetch_imdb_list(source_value)
        print(f"IMDb list {source_value!r}: {len(imdb_ids)} IDs found")
    except Exception as exc:
        print(f"Error fetching IMDb list for group {group_name!r}: {exc!s}")
        return [], f"IMDb fetch error: {exc!s}", 400

    if not imdb_ids:
        print(f"No IMDb IDs found for group {group_name!r}")
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        imdb_ids, "Imdb", "imdb_list_order", sort_order, url, api_key, group_name, watch_state
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
    """Resolve Jellyfin items for a Trakt-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: Trakt list URL or ``"username/slug"`` shorthand.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        trakt_client_id: Trakt API Client ID.

    Returns:
        A ``(items, error, status_code)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    if not trakt_client_id:
        msg = "Trakt Client ID not set — add trakt_client_id in Server Settings"
        print(f"No Trakt Client ID configured for group {group_name!r}")
        return [], msg, 400

    try:
        trakt_ids = fetch_trakt_list(source_value, trakt_client_id)
        print(f"Trakt list {source_value!r}: {len(trakt_ids)} IMDb IDs found")
    except Exception as exc:
        print(f"Error fetching Trakt list for group {group_name!r}: {exc!s}")
        return [], f"Trakt fetch error: {exc!s}", 400

    if not trakt_ids:
        print(f"No items found in Trakt list for group {group_name!r}")
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        trakt_ids, "Imdb", "trakt_list_order", sort_order, url, api_key, group_name, watch_state
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
    """Resolve Jellyfin items for a TMDb-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: TMDb list ID or URL.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        tmdb_api_key: TMDb API Key.

    Returns:
        A ``(items, error, status_code)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    if not tmdb_api_key:
        msg = "TMDb API Key not set — add tmdb_api_key in Server Settings"
        print(f"No TMDb API Key configured for group {group_name!r}")
        return [], msg, 400

    try:
        tmdb_ids = fetch_tmdb_list(source_value, tmdb_api_key)
        print(f"TMDb list {source_value!r}: {len(tmdb_ids)} items found")
    except Exception as exc:
        print(f"Error fetching TMDb list for group {group_name!r}: {exc!s}")
        return [], f"TMDb fetch error: {exc!s}", 400

    if not tmdb_ids:
        print(f"No items found in TMDb list for group {group_name!r}")
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        tmdb_ids, "Tmdb", "tmdb_list_order", sort_order, url, api_key, group_name, watch_state
    )


def _fetch_items_for_anilist_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for an AniList-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: AniList username or ``"username/status"`` shorthand.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A ``(items, error, status_code)`` tuple (same semantics as
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
        print(f"Error fetching AniList items for group {group_name!r}: {exc!s}")
        return [], f"AniList fetch error: {exc!s}", 400

    if not anilist_ids:
        print(f"No items found for AniList user {username!r}")
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        anilist_ids, "AniList", "anilist_list_order", sort_order, url, api_key, group_name, watch_state
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
    """Resolve Jellyfin items for a MyAnimeList-list–backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: MAL username or ``"username/status"`` shorthand.
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        mal_client_id: MyAnimeList Client ID.

    Returns:
        A ``(items, error, status_code)`` tuple (same semantics as
        :func:`_fetch_items_for_imdb_group`).
    """
    if not mal_client_id:
        msg = "MyAnimeList Client ID not set — add mal_client_id in Server Settings"
        print(f"No MAL Client ID configured for group {group_name!r}")
        return [], msg, 400

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
        print(f"Error fetching MyAnimeList items for group {group_name!r}: {exc!s}")
        return [], f"MAL fetch error: {exc!s}", 400

    if not mal_ids:
        print(f"No items found for MyAnimeList user {username!r}")
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        mal_ids, "Mal", "mal_list_order", sort_order, url, api_key, group_name, watch_state
    )


def _fetch_items_for_letterboxd_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a Letterboxd-list–backed group.

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
        print(f"Letterboxd list {source_value!r}: {len(external_ids)} IDs found")
    except Exception as exc:
        print(f"Error fetching Letterboxd items for group {group_name!r}: {exc!s}")
        return [], f"Letterboxd fetch error: {exc!s}", 400

    if not external_ids:
        print(f"No items found in Letterboxd list for group {group_name!r}")
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

    if watch_state == "unwatched":
        items = [i for i in items if not i.get("UserData", {}).get("Played")]
    elif watch_state == "watched":
        items = [i for i in items if i.get("UserData", {}).get("Played")]

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
        print(f"No TMDb API Key configured for recommendations group {group_name!r}")
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
            print(f"No TMDb IDs found in recent items for user {user_id!r}")
            return [], None, 200

        # Fetch recommendations based on these items
        tmdb_ids = get_tmdb_recommendations(tmdb_requests, tmdb_api_key)
        print(f"TMDb recommendations: {len(tmdb_ids)} items found")
    except Exception as exc:
        print(f"Error fetching recommendations for group {group_name!r}: {exc!s}")
        return [], f"Recommendations fetch error: {exc!s}", 400

    if not tmdb_ids:
        print(f"No items found in TMDb recommendations for group {group_name!r}")
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
        elif r_type == "actor":
            return any(
                r_val == str(p.get("Name", "")).strip().lower() 
                for p in (item.get("People") or []) 
                if isinstance(p, dict) and p.get("Type") == "Actor"
            )
        elif r_type == "studio":
            return any(
                r_val == str(s.get("Name", "")).strip().lower() 
                for s in (item.get("Studios") or []) 
                if isinstance(s, dict)
            )
        elif r_type == "tag":
            return any(r_val == str(t).strip().lower() for t in (item.get("Tags") or []))
        elif r_type == "year":
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
            print(f"DEBUG: Skipping malformed rule {r}: {exc}")
            continue

    if not valid_rules:
        return [], None, 200

    filtered = [item for item in raw_items if _eval_item(item, valid_rules)]
    
    if watch_state == "unwatched":
        filtered = [i for i in filtered if not i.get("UserData", {}).get("Played")]
    elif watch_state == "watched":
        filtered = [i for i in filtered if i.get("UserData", {}).get("Played")]

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
        watch_state: Optional filter for watch state ("unwatched", "watched").

    Returns:
        A ``(items, error, status_code)`` tuple.
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
        "year": "years",
    }
    if source_type in filter_map and source_value:
        params[filter_map[source_type]] = source_value

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
        items = fetch_jellyfin_items(url, api_key, params, timeout=30)
        print(f"Found {len(items)} potential items for group {group_name!r}")
        return items, None, 200
    except requests.exceptions.RequestException as exc:
        print(f"Infrastructure error fetching items for group {group_name!r}: {exc!s}")
        return [], f"Jellyfin connection error: {exc!s}", 500
    except Exception as exc:
        logging.exception("Unexpected error fetching items for group %r", group_name)
        return [], f"Internal error: {exc!s}", 500  # noqa: BLE001

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
    # Simple regex to split the logical logic
    pattern = re.compile(r'\s+(AND NOT|OR NOT|AND|OR)\s+', re.IGNORECASE)
    parts = pattern.split(query.strip())
    
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
        op = parts[i].upper().replace('  ', ' ')
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
    if re.search(r"\s+(AND NOT|OR NOT|AND|OR)\s+", val, re.IGNORECASE):
        rules = parse_complex_query(val, type_name)
        return _fetch_items_for_complex_group("preview", rules, "", url, api_key, watch_state)
    else:
        return _fetch_items_for_metadata_group("preview", type_name, val, "", url, api_key, watch_state)




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
    group_name: str = group.get("name", "unnamed").strip()
    if not group_name:
        return {"group": "(unnamed)", "links": 0, "error": "Empty group name"}

    group_dir: str = os.path.join(target_base, group_name)
    sort_order: str = group.get("sort_order", "") or ""
    source_type: str | None = group.get("source_type")
    source_value: str | None = group.get("source_value")

    print(f"Processing group: {group_name!r} -> {group_dir}  (sort_order={sort_order!r})")

    # Clean up and recreate the group directory
    if not dry_run:
        if os.path.exists(group_dir):
            print(f"Cleaning existing directory: {group_dir}")
            shutil.rmtree(group_dir)
        os.makedirs(group_dir, exist_ok=True)

        # Check if there is an auto-generated cover to copy
        source_cover = get_cover_path(group_name, target_base)

        if source_cover:
            poster_dest = os.path.join(group_dir, "poster.jpg")
            try:
                shutil.copy2(source_cover, poster_dest)
                print(f"Copied cover image from {source_cover} to {poster_dest}")
            except OSError as exc:
                print(f"Failed to copy cover image: {exc}")

    # --- Resolve items ---
    error: str | None = None
    status_code: int = 200
    watch_state: str = group.get("watch_state", "")

    if source_type == "imdb_list":
        items, error, status_code = _fetch_items_for_imdb_group(
            group_name, source_value or "", sort_order, url, api_key, watch_state
        )
    elif source_type == "trakt_list":
        items, error, status_code = _fetch_items_for_trakt_group(
            group_name, source_value or "", sort_order, url, api_key, trakt_client_id, watch_state
        )
    elif source_type == "tmdb_list":
        items, error, status_code = _fetch_items_for_tmdb_group(
            group_name, source_value or "", sort_order, url, api_key, tmdb_api_key, watch_state
        )
    elif source_type == "anilist_list":
        items, error, status_code = _fetch_items_for_anilist_group(
            group_name, source_value or "", sort_order, url, api_key, watch_state
        )
    elif source_type == "mal_list":
        items, error, status_code = _fetch_items_for_mal_group(
            group_name, source_value or "", sort_order, url, api_key, mal_client_id, watch_state
        )
    elif source_type == "letterboxd_list":
        items, error, status_code = _fetch_items_for_letterboxd_group(
            group_name, source_value or "", sort_order, url, api_key, watch_state
        )
    elif source_type == "recommendations":
        items, error, status_code = _fetch_items_for_recommendations_group(
            group_name, source_value or "", sort_order, url, api_key, tmdb_api_key, watch_state
        )
    elif isinstance(group.get("rules"), list) and group["rules"]:
        rules_list = group["rules"]
        items, error, status_code = _fetch_items_for_complex_group(
            group_name, rules_list, sort_order, url, api_key, watch_state
        )
    else:
        val_str = str(source_value or "")
        
        # Determine if it's a complex textual rule that needs local parsing
        if source_type in ["genre", "actor", "studio", "tag", "year"] and re.search(r'\s+(AND NOT|OR NOT|AND|OR)\s+', val_str, re.IGNORECASE):
            rules = parse_complex_query(val_str, str(source_type))
            items, error, status_code = _fetch_items_for_complex_group(
                group_name, rules, sort_order, url, api_key, watch_state
            )
        else:
            items, error, status_code = _fetch_items_for_metadata_group(
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

    # --- Create symlinks ---
    use_prefix: bool = bool(sort_order)  # numbered prefix ↔ any sort order
    width: int = max(len(str(len(items))) if items else 4, 4)
    links_created: int = 0
    preview_items = []

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
        if dry_run:
            if len(preview_items) < 100:
                preview_items.append({"Name": item.get("Name", "Unknown"), "Year": item.get("ProductionYear", ""), "FileName": file_name})
            links_created += 1
        else:
            try:
                os.symlink(host_path, dest_path)
                print(f"Created symlink: {dest_path} -> {host_path}")
                links_created += 1
            except OSError as exc:
                print(f"Error creating symlink {dest_path}: {exc}")

    if dry_run:
        print(f"Would create {links_created} symlinks for {group_name!r}")
    else:
        print(f"Created {links_created} symlinks for {group_name!r}")
    result: dict[str, Any] = {"group": group_name, "links": links_created}
    if dry_run:
        result["items"] = preview_items
    
    # --- Automatic Library Creation ---
    if (
        not dry_run
        and auto_create_libraries
        and links_created > 0
    ):
        if existing_libraries is not None and group_name not in existing_libraries:
            print(f"Creating Jellyfin library for grouping: {group_name!r}")
            # Resolve the path as Jellyfin sees it
            if target_path_in_jellyfin:
                lib_path = os.path.join(target_path_in_jellyfin, group_name)
            else:
                lib_path = group_dir
                
            try:
                add_virtual_folder(url, api_key, group_name, [lib_path], collection_type="mixed")
                print(f"Successfully created library {group_name!r} with path {lib_path!r}")
                existing_libraries.append(group_name) # Prevent double creation in same run
            except Exception as exc:
                print(f"Failed to create Jellyfin library {group_name!r}: {exc}")
                result["library_error"] = str(exc)

    # --- Automatic Library Cover ---
    if not dry_run and auto_set_library_covers:
        if source_cover and os.path.exists(source_cover):
            print(f"Setting cover image for library {group_name!r} via API")
            set_virtual_folder_image(url, api_key, group_name, source_cover)

    return result



def _is_in_season(start_str: Any, end_str: Any) -> bool:
    """Check if the current date is within the seasonal window [start, end).
    Dates are in 'MM-DD' format.
    """
    if not isinstance(start_str, str) or not isinstance(end_str, str):
        return True
    
    try:
        now = datetime.now()
        current_md = now.strftime("%m-%d")
        
        # We know they are strings now
        s: str = start_str
        e: str = end_str
        
        if s <= e:
            # Simple case: window stays within one calendar year (e.g., 06-01 to 08-31)
            return s <= current_md < e
        else:
            # Over-year case: window spans across Jan 1st (e.g., 12-01 to 01-01)
            return current_md >= s or current_md < e
    except (ValueError, TypeError):
        return True

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
    auto_create_libraries: bool = bool(config.get("auto_create_libraries", False))
    auto_set_library_covers: bool = bool(config.get("auto_set_library_covers", False))
    target_path_in_jellyfin: str = str(config.get("target_path_in_jellyfin", "")).strip()

    if not url or not api_key or not target_base:
        raise ValueError("Server settings or target path not configured")

    if not dry_run and not os.path.exists(target_base):
        os.makedirs(target_base, exist_ok=True)

    print(f"Starting sync to: {target_base}")
    if jellyfin_root and host_root:
        print(f"Path translation active: {jellyfin_root} -> {host_root}")

    existing_libraries: list[str] = []
    if auto_create_libraries:
        try:
            existing_libraries = get_libraries(url, api_key)
            print(f"Found {len(existing_libraries)} existing virtual folders in Jellyfin")
        except Exception as exc:
            print(f"Warning: Could not fetch existing libraries: {exc}")
            # We'll continue, but library creation might fail or try to recreate existing ones
            auto_create_libraries = False 

    _LIBRARY_CACHE.clear()

    results: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            print(f"Skipping invalid group entry: {group}")
            continue
        
        name = group.get("name", "").strip()
        if group_names is not None:
            if not name or name not in group_names:
                continue

        # --- Seasonal Check ---
        if group.get("seasonal_enabled"):
            start = group.get("seasonal_start")
            end = group.get("seasonal_end")
            if not _is_in_season(start, end):
                if not dry_run and name:
                    group_dir = os.path.join(target_base, name)
                    if os.path.isdir(group_dir):
                        print(f"Seasonal group {name!r} is out of season. Deleting directory: {group_dir}")
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

    _LIBRARY_CACHE.clear()
    return results


def run_cleanup_broken_symlinks(config: dict[str, Any]) -> int:
    """Scan the target directory for broken symlinks and remove them.

    Args:
        config: The application configuration dict.

    Returns:
        The number of broken symlinks deleted.
    """
    target_base: str = str(config.get("target_path", ""))
    
    if not target_base or not os.path.isdir(target_base):
        print(f"Cleanup aborted: invalid target base path '{target_base}'")
        return 0

    deleted_count = 0
    
    for root, dirs, files in os.walk(target_base):
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path) and not os.path.exists(path):
                # The symlink is broken
                try:
                    os.unlink(path)
                    print(f"Deleted broken symlink: {path}")
                    deleted_count += 1
                except OSError as exc:
                    print(f"Error deleting broken symlink {path}: {exc}")
                    
    return deleted_count
