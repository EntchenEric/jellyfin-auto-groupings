"""sync.py - Core synchronisation logic for Jellyfin Groupings.

This module contains :func:`run_sync`, which drives the per-group loop
responsible for:

1. Fetching items from IMDb lists, Trakt lists, or directly from Jellyfin
   based on metadata filters (genre, actor, studio, tag).
2. Optionally translating Jellyfin-side media paths to equivalent host paths.
3. Cleaning and re-creating each group directory with numbered symlinks.
"""

from __future__ import annotations

import calendar
import contextlib
import hashlib
import logging
import math
import random
import re
import shutil
import threading
import time
from datetime import UTC, datetime
from functools import cmp_to_key
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import requests

from _common import COMPLEX_QUERY_SOURCE_TYPES as _COMPLEX_QUERY_SOURCE_TYPES
from _common import LIST_SOURCE_TYPES as _LIST_SOURCE_TYPES
from _common import normalize_group_relpath
from anilist import fetch_anilist_list
from imdb import fetch_imdb_list
from jellyfin import (
    DEFAULT_ITEM_TYPES,
    ITEM_TYPE_FILTERS,
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

__all__ = [
    "clear_library_cache",
    "get_cover_path",
    "parse_complex_query",
    "preview_group",
    "run_cleanup_broken_symlinks",
    "run_sync",
]

# Pre-compiled regex for detecting and locating complex query logical
# operators.  Both lookarounds require whitespace (or a string boundary) on
# each side, so a genre such as ``"Andor"`` is never split on its ``and``.
# The two-word forms come first so ``"AND NOT"`` is tokenised as one operator
# instead of an ``AND`` followed by a bare ``NOT``.  A bare ``NOT`` is *not*
# an operator here: tags such as ``"Not Safe For Work"`` are real values, and
# only a leading ``NOT`` (handled by :func:`parse_complex_query`) is a negation.
_COMPLEX_QUERY_RE = re.compile(
    r"(?<!\S)(AND NOT|OR NOT|AND|OR)(?!\S)",
    re.IGNORECASE,
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
    },
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

# Jellyfin Fields parameter for full-library fetches.
#
# ``People`` is deliberately absent: Jellyfin expands the full cast for every
# item, which on a mid-sized library turns a 5-second page into a 75-second one
# and blows past _FULL_LIBRARY_TIMEOUT, so *every* complex query fails. Only
# actor rules need it, so it is requested on demand via _FULL_LIBRARY_FIELDS_
# WITH_PEOPLE.
_FULL_LIBRARY_FIELDS: str = (
    "Path,ProviderIds,Genres,Studios,Tags,ProductionYear,CommunityRating,UserData"
)

# Field list for the rare fetches that must evaluate actor rules.
_FULL_LIBRARY_FIELDS_WITH_PEOPLE: str = _FULL_LIBRARY_FIELDS + ",People"

# Jellyfin API timeout for full-library fetches (seconds)
_FULL_LIBRARY_TIMEOUT: int = 30

# Timeout for the People-bearing variant. Jellyfin expands every item's cast
# for these, which is inherently slow (measured ~75 s per 500-item page on a
# ~4400-title library), so actor rules get a longer budget instead of failing.
_FULL_LIBRARY_PEOPLE_TIMEOUT: int = 180

# Smaller pages for the People-bearing fetch: the per-page cost scales with the
# page size, so fewer items per request keeps each one inside the timeout.
_FULL_LIBRARY_PEOPLE_PAGE_SIZE: int = 100

# Jellyfin API timeout for metadata group fetches (seconds)
_METADATA_FETCH_TIMEOUT: int = 30

# TTL for the full-library cache (seconds).  The cache is shared across
# all groups in a single run_sync() call and persists across calls within
# this window, avoiding redundant paginated fetches when the scheduler
# triggers multiple syncs in quick succession.
_LIBRARY_CACHE_TTL: int = 300  # 5 minutes


def _build_preview_item(
    item: dict[str, Any],
    file_name: str | None = None,
) -> dict[str, Any]:
    """Build a preview dict from a Jellyfin item.

    Args:
        item: A Jellyfin item dictionary.
        file_name: Optional file name to include in the preview.

    Returns:
        A preview dictionary with ``Name`` and ``Year`` keys, and
        optionally ``FileName``.

    """
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
            normalized_root = Path(jellyfin_root).resolve()
            normalized_path = Path(jellyfin_path).resolve()
            if normalized_path.is_relative_to(normalized_root):
                rel = normalized_path.relative_to(normalized_root)
                return str(Path(host_root) / rel)
        except (ValueError, RuntimeError, OSError) as exc:
            logger.debug(
                "Path translation failed for %r (root=%r, host=%r): %s",
                jellyfin_path,
                jellyfin_root,
                host_root,
                exc,
            )
    return jellyfin_path


def get_cover_path(
    group_name: str,
    target_base: str,
    check_exists: bool = True,
    ext: str = "jpg",
) -> str | None:
    """Compute the expected cover image path for a group, resolving storage priority.

    Resolution order:
    1. Library-local ``.covers/`` directory under *target_base* (new storage location).
    2. Internal ``config/covers/`` directory (legacy storage location).

    Args:
        group_name: The human-readable name of the group.
        target_base: The root library directory where ``.covers/`` resides.
        check_exists: If True, return None if the file doesn't exist on disk.
            If False, return the prioritized path regardless of disk presence
            (useful for saving new covers — prefers the library-local path
            when *target_base* is a directory, falling back to the legacy
            config location otherwise).
        ext: File extension to use (default ``jpg``).

    Returns:
        The absolute path to the cover image, or None if not found/possible.

    """
    safe_name = hashlib.md5(
        group_name.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()

    # Priority 1: Library-local .covers/ directory (new storage location)
    lib_cover_path = str(Path(target_base) / ".covers" / f"{safe_name}.{ext}")

    # Priority 2: Internal config/covers/ directory (legacy storage location)
    legacy_cover_path = str(
        Path(__file__).resolve().parent / "config" / "covers" / f"{safe_name}.{ext}",
    )

    if not check_exists:
        # Resolving where to SAVE: prefer library-local if target_base exists
        if target_base and Path(target_base).is_dir():
            return lib_cover_path
        return legacy_cover_path

    if Path(lib_cover_path).exists():
        return lib_cover_path
    if Path(legacy_cover_path).exists():
        return legacy_cover_path

    return None


#: Keyed by ``(url, api_key, include_people)`` — the People-bearing fetch is a
#: superset of the lean one and must not be served from the same entry.
_LIBRARY_CACHE: dict[tuple[str, str, bool], tuple[float, list[dict[str, Any]]]] = {}
_LIBRARY_CACHE_LOCK = threading.RLock()


def clear_library_cache() -> None:
    """Clear the cached Jellyfin library data.

    Called by routes when the configuration changes to prevent stale
    cached data from being used after a server URL or API key update.
    """
    with _LIBRARY_CACHE_LOCK:
        _LIBRARY_CACHE.clear()
    logger.debug("Jellyfin library cache cleared")


def _is_cache_fresh(entry: tuple[float, list[dict[str, Any]]]) -> bool:
    """Check whether a cache entry is still within its TTL window.

    Args:
        entry: A cache entry ``(timestamp, items)`` tuple.

    Returns:
        ``True`` if the entry is still fresh, ``False`` otherwise.

    """
    return (time.monotonic() - entry[0]) < _LIBRARY_CACHE_TTL


def _filter_by_watch_state(
    items: list[dict[str, Any]],
    watch_state: str,
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
        return [i for i in items if not (i.get("UserData") or {}).get("Played")]
    if watch_state == "watched":
        return [i for i in items if (i.get("UserData") or {}).get("Played")]
    return items


def _filter_by_item_type(
    items: list[dict[str, Any]],
    item_type: str,
) -> list[dict[str, Any]]:
    """Restrict *items* to movies or series.

    Used on the locally-evaluated paths (complex rules, external lists),
    where the Jellyfin-side ``IncludeItemTypes`` parameter is not available
    because the full library was fetched in one go.

    Args:
        items: Jellyfin item dicts (must contain ``Type``).
        item_type: ``"movies"``, ``"series"``, or any other value (which
            returns the list unchanged).

    Returns:
        The filtered list.

    """
    wanted = ITEM_TYPE_FILTERS.get(item_type)
    if not wanted:
        return items
    return [i for i in items if i.get("Type") == wanted]


def _fetch_full_library(
    url: str,
    api_key: str,
    group_name: str,
    *,
    include_people: bool = False,
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Fetch the full Jellyfin library, cached with a TTL.

    Uses double-checked locking with a reentrant lock to avoid redundant
    fetches when multiple groups share the same Jellyfin server.  The
    cache entry includes a monotonic timestamp so that repeated
    ``run_sync()`` calls (e.g. from the scheduler) can reuse the data
    within the TTL window without re-fetching.

    The cache is explicitly invalidated by :func:`clear_library_cache`
    (called when the server URL or API key changes) or when the TTL
    expires.

    Args:
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        group_name: Human-readable group name (used for logging).
        include_people: Also request the ``People`` field.  Only actor
            rules need it, and it is expensive enough to time the request
            out on a mid-sized library, so it is off by default.  Cached
            separately from the lean variant.

    Returns:
        A (raw_items, error, status_code) tuple.

    """
    cache_key = (url, api_key, include_people)
    with _LIBRARY_CACHE_LOCK:
        if cache_key in _LIBRARY_CACHE:
            entry = _LIBRARY_CACHE[cache_key]
            if _is_cache_fresh(entry):
                return entry[1].copy(), None, 200
            # TTL expired — remove stale entry so it gets re-fetched
            del _LIBRARY_CACHE[cache_key]

    fields = (
        _FULL_LIBRARY_FIELDS_WITH_PEOPLE if include_people else _FULL_LIBRARY_FIELDS
    )
    try:
        all_items = fetch_all_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": RECURSIVE_TRUE,
                "Fields": fields,
                "IncludeItemTypes": DEFAULT_ITEM_TYPES,
            },
            limit=(
                _FULL_LIBRARY_PEOPLE_PAGE_SIZE
                if include_people
                else _FULL_LIBRARY_PAGE_SIZE
            ),
            timeout=(
                _FULL_LIBRARY_PEOPLE_TIMEOUT
                if include_people
                else _FULL_LIBRARY_TIMEOUT
            ),
            _fetch_page=fetch_jellyfin_items,
        )
        logger.info("Jellyfin library: %s items fetched for matching", len(all_items))
        with _LIBRARY_CACHE_LOCK:
            # Double-check: another thread may have populated the cache while we fetched.
            # Only store if the key is missing OR the existing entry is stale (TTL expired)
            # to avoid replacing a fresh entry from another thread.
            if cache_key not in _LIBRARY_CACHE or not _is_cache_fresh(
                _LIBRARY_CACHE[cache_key]
            ):
                _LIBRARY_CACHE[cache_key] = (time.monotonic(), all_items)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.exception(
            "Infrastructure error fetching Jellyfin library for group %r",
            group_name,
        )
        return [], f"Jellyfin connection error: {exc!s}", 500
    else:
        return all_items, None, 200


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
        matched_ids: set[str] = {
            str(eid).lower() if case_insensitive else str(eid) for eid in external_ids
        }
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

    Sorting is defensive because these dicts come straight from a Jellyfin
    response, where a field can be missing, ``None``, a number, or a string
    for the same logical attribute (``CommunityRating`` is a float for rated
    titles and ``None`` otherwise; ``ProductionYear`` arrives as ``2001`` or
    ``"2001.0"`` depending on the server version).  A raw ``sorted()`` on the
    mixed values raises ``TypeError: '<' not supported between instances of
    'float' and 'str'`` and aborts the whole group, so:

    * ``Random`` shuffles instead of sorting — it is a documented sort option
      and a key lookup on it used to return the list unchanged.
    * values are normalised to a ``(kind, comparable)`` pair so numbers and
      numeric strings sort numerically and are never compared to text.  When
      a field holds both, the numeric values come first in *either*
      direction; only the ordering inside each group is reversed.
    * text compares case-insensitively, matching how Jellyfin orders
      ``SortName`` (``Banana`` before ``apple``) instead of raw codepoints.
    * items missing the field always sort last, in either direction.
    * tie-break keys from ``SORT_MAP`` (``"ProductionYear,SortName"``) are
      applied, so two titles from the same year come out in name order
      instead of whatever order Jellyfin happened to page them in.

    Args:
        items: The matched Jellyfin items to sort.
        sort_order: One of the keys in :data:`jellyfin.SORT_MAP`.

    Returns:
        A new list sorted according to *sort_order*.

    """
    if sort_order not in SORT_MAP:
        return items

    if sort_order == "Random":
        # ``SORT_MAP["Random"]`` is a Jellyfin server-side directive; there is
        # no "random" key in an item dict, so the generic path below would sort
        # on a missing field and hand back the input order unchanged.
        shuffled = list(items)
        random.shuffle(shuffled)
        return shuffled

    sort_key_str, sort_dir_str = SORT_MAP[sort_order]
    sort_keys = [key.strip() for key in sort_key_str.split(",") if key.strip()]
    sort_dirs = [d.strip() for d in sort_dir_str.split(",")]

    def _is_missing(value: Any) -> bool:
        """Return whether *value* carries no usable sort information.

        ``None`` is the obvious case, but Jellyfin also emits empty strings for
        optional fields, and sorting those as the empty string would place
        them before every real value instead of after them.

        Non-finite numbers count as missing too.  ``float("nan")`` and
        ``float("inf")`` parse successfully, but NaN compares false against
        everything, so a single NaN would make the comparator return ``1`` in
        both directions and corrupt the ordering of every real value around it.

        Args:
            value: The raw field value.

        """
        if value is None:
            return True
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return True
            try:
                return not math.isfinite(float(text))
            except ValueError:
                return False
        if isinstance(value, float):
            return not math.isfinite(value)
        return False

    def _comparable(value: Any) -> tuple[int, Any]:
        """Normalise a raw Jellyfin value into a mutually comparable pair.

        Args:
            value: The raw field value from the item dict.

        Returns:
            ``(0, float)`` for numeric values (including numeric strings such
            as ``"2001.0"`` or ``"7.5"``), ``(1, str)`` for everything else.
            The leading integer keeps the two kinds from ever being compared.
            Non-finite values never reach this function; :func:`_is_missing`
            filters them out first.

        """
        if isinstance(value, bool):
            # ``bool`` is an ``int`` subclass; True/False are not ratings.
            return (1, str(value).casefold())
        if isinstance(value, (int, float)):
            return (0, float(value))
        text = str(value).strip()
        try:
            return (0, float(text))
        except ValueError:
            return (1, text.casefold())

    def _make_cmp(key: str, descending: bool) -> Callable[[dict, dict], int]:
        """Build a comparator for one entry of ``SORT_MAP``.

        A comparator is used instead of a key function because the direction
        must reverse the values but *not* the placement of items that are
        missing the field — a key function combined with ``reverse=True``
        would flip those to the front and bury the real entries.

        Args:
            key: The Jellyfin field name to compare on.
            descending: Whether present values compare in reverse order.

        Returns:
            A ``cmp``-style callable for :func:`functools.cmp_to_key`.

        """

        def _compare(left: dict[str, Any], right: dict[str, Any]) -> int:
            left_value = left.get(key)
            right_value = right.get(key)
            left_missing = _is_missing(left_value)
            right_missing = _is_missing(right_value)
            if left_missing or right_missing:
                if left_missing and right_missing:
                    return 0
                # Missing values always sort last, in both directions.
                return 1 if left_missing else -1

            left_kind, left_cmp = _comparable(left_value)
            right_kind, right_cmp = _comparable(right_value)
            if left_kind != right_kind:
                # Numeric values first; the kind order is not reversed so a
                # descending sort cannot promote unratable text to the top.
                return -1 if left_kind < right_kind else 1
            if left_cmp == right_cmp:
                return 0
            result = -1 if left_cmp < right_cmp else 1
            return -result if descending else result

        return _compare

    # Apply the least significant key first, then the next one; ``sorted`` is
    # stable, so each pass preserves the order established by the previous
    # one. Sorting on a combined tuple cannot do this, because the two keys
    # may have opposite directions (year descending, name ascending).
    result = list(items)
    for index in range(len(sort_keys) - 1, -1, -1):
        direction = sort_dirs[index] if index < len(sort_dirs) else sort_dirs[0]
        result = sorted(
            result,
            key=cmp_to_key(_make_cmp(sort_keys[index], direction == "Descending")),
        )
    return result


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
        logger.exception(
            "Error fetching %s list for group %r",
            source_label,
            group_name,
        )
        return [], f"{source_label} fetch error: {exc!s}", 400

    if not external_ids:
        logger.info("No items found in %s list for group %r", source_label, group_name)
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        external_ids,
        provider_key,
        list_order_key,
        sort_order,
        url,
        api_key,
        group_name,
        watch_state,
    )


def _fetch_items_for_imdb_group(
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for an IMDb-list-backed group.

    Args:
        group_name: The group name (for logging).
        source_value: The IMDb list URL.
        sort_order: The requested sort order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional watch-state filter.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
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
    """Resolve Jellyfin items for a Trakt-list-backed group.

    Args:
        group_name: The group name (for logging).
        source_value: The Trakt list URL.
        sort_order: The requested sort order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        trakt_client_id: Trakt API client ID.
        watch_state: Optional watch-state filter.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
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
    """Resolve Jellyfin items for a TMDb-list-backed group.

    Args:
        group_name: The group name (for logging).
        source_value: The TMDb list ID or URL.
        sort_order: The requested sort order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        tmdb_api_key: TMDb API key.
        watch_state: Optional watch-state filter.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
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
    anilist_api_url: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for an AniList-list-backed group.

    Args:
        group_name: The group name (for logging).
        source_value: The AniList username and optional status.
        sort_order: The requested sort order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional watch-state filter.
        anilist_api_url: Optional custom AniList API URL.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
    username = source_value
    status = None
    if "/" in source_value:
        username, status = source_value.split("/", 1)

    return _fetch_and_resolve(
        group_name,
        lambda: fetch_anilist_list(username, status, api_url=anilist_api_url),
        sort_order,
        url,
        api_key,
        watch_state,
        "AniList",
        "anilist_list_order",
        "AniList",
        lambda count: (
            f"AniList user {username!r} (status={status!r}): {count} items found"
        ),
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
    """Resolve Jellyfin items for a MyAnimeList-list-backed group.

    Args:
        group_name: The group name (for logging).
        source_value: The MAL username and optional status.
        sort_order: The requested sort order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        mal_client_id: MyAnimeList client ID.
        watch_state: Optional watch-state filter.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
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
        lambda count: (
            f"MyAnimeList user {username!r} (status={status!r}): {count} items found"
        ),
    )


def _match_letterboxd_id(
    eid: str,
    items_by_imdb: dict[str, dict[str, Any]],
    items_by_tmdb: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the Jellyfin item matching a single Letterboxd external ID.

    Args:
        eid: The external ID (``tt...`` for IMDb, numeric for TMDb).
        items_by_imdb: Items indexed by lowercase IMDb ID.
        items_by_tmdb: Items indexed by TMDb ID.

    Returns:
        The matching Jellyfin item, or ``None``.

    """
    if str(eid).startswith("tt"):
        return items_by_imdb.get(str(eid).lower())
    return items_by_tmdb.get(str(eid))


def _fetch_items_for_letterboxd_group(
    group_name: str,
    source_value: str,
    _sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items for a Letterboxd-list-backed group.

    Args:
        group_name: Human-readable group name (used for logging).
        source_value: Letterboxd list URL.
        _sort_order: Requested sort order key (accepted for consistent
                     interface with other ``_fetch_items_for_*_group``
                     functions; list order is preserved automatically).
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
        logger.exception("Error fetching Letterboxd items for group %r", group_name)
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

    items = _build_letterboxd_items(
        external_ids,
        items_by_imdb,
        items_by_tmdb,
    )
    items = _filter_by_watch_state(items, watch_state)

    return items, None, 200


def _build_letterboxd_items(
    external_ids: list[str],
    items_by_imdb: dict[str, dict[str, Any]],
    items_by_tmdb: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map external Letterboxd IDs to Jellyfin items, preserving list order.

    The external list order is preserved.
    Duplicates (the same Jellyfin item matched via both IMDb and TMDb ID)
    are skipped to avoid duplicate symlinks.

    Args:
        external_ids: Ordered list of external IDs from Letterboxd.
        items_by_imdb: Items indexed by IMDb ID.
        items_by_tmdb: Items indexed by TMDb ID.

    Returns:
        Ordered list of matching Jellyfin items.

    """
    items: list[dict[str, Any]] = []
    seen_jf_ids: set[str] = set()
    for eid in external_ids:
        match = _match_letterboxd_id(eid, items_by_imdb, items_by_tmdb)
        if not match:
            continue
        if match["Id"] not in seen_jf_ids:
            items.append(match)
            seen_jf_ids.add(match["Id"])
    return items


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
        logger.info(
            "No TMDb API Key configured for recommendations group %r",
            group_name,
        )
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
        logger.exception("Error fetching recommendations for group %r", group_name)
        return [], f"Recommendations fetch error: {exc!s}", 400

    if not tmdb_ids:
        logger.info("No items found in TMDb recommendations for group %r", group_name)
        return [], None, 200

    return _match_jellyfin_items_by_provider(
        tmdb_ids,
        "Tmdb",
        "recommendations_list_order",
        sort_order,
        url,
        api_key,
        group_name,
        watch_state,
    )


def _match_year(value: Any, rule_value: str) -> bool:
    """Match a production year, supporting range comparisons.

    Accepts a plain year (``2001``) as well as ``<``, ``<=``, ``>`` and
    ``>=`` prefixes (``>2000``), so a group can select a period without
    listing every year in it.

    Args:
        value: The item's ``ProductionYear`` (may be ``None``).
        rule_value: The year expression from the rule. ``None`` is treated as
            "no match" so a partially filled rule in ``config.json`` cannot
            abort a whole sync; other scalars are compared by their string
            form so a numeric rule value still matches its year.

    Returns:
        ``True`` if the year satisfies the expression.

    """
    if value is None or rule_value is None:
        return False

    expr = str(rule_value).strip()
    if not expr:
        return False
    for prefix in (">=", "<=", ">", "<"):
        if expr.startswith(prefix):
            year = _coerce_year_int(value)
            if year is None:
                return False
            # Parse the limit with _parse_year_int so float-formatted limits
            # (e.g. ">2001.0" or ">=2001.0") are tolerated, mirroring the
            # exact-comparison path below.  A bare ``int()`` would reject
            # these and silently return no matches.
            limit = _parse_year_int(expr[len(prefix) :].strip())
            if limit is None:
                return False
            if prefix == ">=":
                return year >= limit
            if prefix == "<=":
                return year <= limit
            if prefix == ">":
                return year > limit
            return year < limit

    # Plain (exact) comparison.  Normalise numeric/string year values (e.g.
    # ``2001.0`` or ``"2001.0"`` from some API responses) so they still match
    # ``"2001"`` instead of comparing raw strings and returning False.
    coerced = _coerce_year_int(value)
    if coerced is not None:
        return coerced == _parse_year_int(expr)
    return str(value).strip() == expr


def _coerce_year_int(value: Any) -> int | None:
    """Coerce a year value to an int, tolerating float/string forms.

    Some API responses report ``ProductionYear`` as a float (``2001.0``)
    or as a string (``"2001.0"``).  This helper normalises all of those to
    a plain ``int`` so range and exact comparisons behave consistently.

    Args:
        value: The raw year value (int, float, or str).

    Returns:
        The year as an ``int``, or ``None`` if *value* cannot be coerced.

    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Guard against non-finite floats (``inf``/``nan``) and reject
        # fractional years (e.g. ``2001.5``) which are malformed.  A corrupt
        # API response could otherwise silently truncate a fractional year
        # to a whole one and match the wrong rule.  ``float.is_integer()``
        # is safe for all floats (including ``inf``/``nan``, which return
        # ``False``), so no exception handling is needed here.
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError:
            pass
        # Tolerate a trailing ``.0`` (e.g. ``"2001.0"``) from float
        # serialisation, but reject genuinely fractional years (e.g.
        # ``"2001.5"``) rather than silently truncating them.
        try:
            f = float(stripped)
        except (ValueError, OverflowError):
            return None
        if f.is_integer():
            return int(f)
        return None
    return None


def _parse_year_int(expr: str) -> int | None:
    """Parse a plain year expression into an int, or ``None`` if invalid.

    Tolerates float-formatted expressions (e.g. ``"2001.0"``) so that a
    plain comparison is symmetric with :func:`_coerce_year_int`, which
    already normalises float-formatted *values*.  This mirrors the
    ``"2001.0"`` serialisation some API responses use.

    Args:
        expr: The stripped year expression (e.g. ``"2001"``).

    Returns:
        The integer year, or ``None`` if *expr* is not a valid integer.

    """
    try:
        return int(expr)
    except (TypeError, ValueError):
        pass
    # Tolerate a trailing ``.0`` (e.g. ``"2001.0"``) from float
    # serialisation, mirroring _coerce_year_int.  ``OverflowError`` covers
    # non-finite or oversized expressions (e.g. ``"inf"``, ``"1e309"``)
    # that ``float()`` cannot convert.  A genuinely fractional expression
    # (e.g. ``"2001.5"``) is rejected rather than silently truncated to a
    # whole year, so a rule like ``>2001.5`` never matches ``2001``.
    try:
        f = float(expr)
    except (TypeError, ValueError, OverflowError):
        return None
    if f.is_integer():
        return int(f)
    return None


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
            return any(
                r_val == str(g).strip().lower() for g in (item.get("Genres") or [])
            )
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
            return any(
                r_val == str(t).strip().lower() for t in (item.get("Tags") or [])
            )
        if r_type == "year":
            return _match_year(item.get("ProductionYear"), r_val)
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

    # Evaluate the first rule directly — a bare NOT at position 0 is
    # treated as "invert this condition" (e.g. ``NOT genre:Comedy``).
    first_rule = rules[0]
    result = _match_condition(item, first_rule["type"], first_rule["value"])
    if first_rule["operator"].endswith("NOT"):
        result = not result

    for rule in rules[1:]:
        op = rule["operator"]
        matched = _match_condition(item, rule["type"], rule["value"])

        match op:
            case "AND":
                result = result and matched
            case "OR":
                result = result or matched
            case "AND NOT" | "NOT":
                result = result and not matched
            case "OR NOT":
                result = result or not matched
            case _:
                # Unknown operator — treat as AND for graceful degradation
                logger.debug(
                    "Unknown operator %r in rule evaluation, treating as AND",
                    op,
                )
                result = result and matched

    return result


def _fetch_items_for_complex_group(
    group_name: str,
    rules: list[dict[str, Any]],
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str = "",
    item_type: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve Jellyfin items by evaluating a stacked list of rules.

    Args:
        group_name: Human-readable group name.
        rules: List of rule dicts (operator, type, value).
        sort_order: Requested sort order key.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional filter for watch state ("unwatched", "watched").
        item_type: Optional restriction to ``"movies"`` or ``"series"``.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
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

    # Only actor rules read item["People"], and requesting that field is slow
    # enough to time the fetch out, so pay for it only when it is used.
    needs_people = any(r["type"] == "actor" for r in valid_rules)

    raw_items, error, status_code = _fetch_full_library(
        url,
        api_key,
        group_name,
        include_people=needs_people,
    )
    if error is not None:
        return [], error, status_code

    filtered = [item for item in raw_items if _eval_item(item, valid_rules)]

    filtered = _filter_by_item_type(filtered, item_type)
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
    item_type: str = "",
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
        item_type: Optional restriction to ``"movies"`` or ``"series"``.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
    params: dict[str, str] = {
        "Recursive": RECURSIVE_TRUE,
        "Fields": "Path",
        "IncludeItemTypes": ITEM_TYPE_FILTERS.get(item_type, DEFAULT_ITEM_TYPES),
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
        items = fetch_jellyfin_items(
            url,
            api_key,
            params,
            timeout=_METADATA_FETCH_TIMEOUT,
        )
        logger.info("Found %s potential items for group %r", len(items), group_name)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.exception("Infrastructure error fetching items for group %r", group_name)
        return [], f"Jellyfin connection error: {exc!s}", 500
    else:
        return items, None, 200


def _split_complex_query(text: str) -> list[tuple[bool, str]]:
    """Split *text* into ``(is_operator, value)`` tokens.

    Only standalone operator words are recognised, so a value that merely
    contains one (``"Andor"``, ``"Coronation"``) is never split.

    Args:
        text: The stripped query string.

    Returns:
        A list of tokens in source order. Operator tokens carry the
        upper-cased operator name; text tokens carry the stripped fragment.

    """
    tokens: list[tuple[bool, str]] = []
    position = 0
    for match in _COMPLEX_QUERY_RE.finditer(text):
        fragment = text[position : match.start()].strip()
        if fragment:
            tokens.append((False, fragment))
        tokens.append((True, match.group(1).upper()))
        position = match.end()
    tail = text[position:].strip()
    if tail:
        tokens.append((False, tail))
    return tokens


def _merge_operators(pending: str, new: str) -> str:
    """Resolve two operators written back to back with no operand between them.

    ``"Action AND AND Comedy"`` and ``"Action AND NOT OR Comedy"`` are typos
    rather than meaningful expressions. The operator nearest the following
    condition wins, because that is the one the user wrote last for it — except
    that a ``NOT`` is never discarded, since dropping it would invert the
    filter the user asked for.

    Args:
        pending: The operator seen first.
        new: The operator seen immediately after it.

    Returns:
        The operator to apply to the next condition.

    """
    logger.debug("Collapsing stacked operators %r and %r", pending, new)
    if new.endswith("NOT"):
        return new
    if pending.endswith("NOT"):
        # "NOT OR" is the user's way of writing "OR NOT".
        return f"{new} NOT"
    return new


def _detect_bare_not(val: str) -> tuple[bool, str]:
    """Check whether *val* starts with a bare ``NOT`` word.

    Args:
        val: The text fragment to inspect.

    Returns:
        An ``(is_not, remainder)`` tuple. *remainder* is the text after the
        ``NOT `` prefix, or an empty string when *val* is just ``"NOT"``.

    """
    upper_val = val.upper()
    if upper_val == "NOT":
        return True, ""
    if upper_val.startswith("NOT "):
        return True, val[3:].strip()
    return False, val


def parse_complex_query(query: str, default_type: str) -> list[dict[str, Any]]:
    """Parse a complex textual rule query into a list of structured rules.

    The query can contain logical operators like AND, OR, AND NOT, OR NOT.
    Each part of the query is assigned the *default_type* unless a specific
    type prefix (e.g., "actor:Tom Hanks") is provided.

    A bare ``NOT`` (or ``AND NOT``) at position 0 is treated as a negation
    of the first condition (e.g. ``NOT Comedy`` negates ``genre:Comedy``).

    Only standalone operator words are recognised, so ``"Andor"`` stays a
    single value. A leading, dangling, or stacked operator never becomes a
    filter value of its own: a dangling operator is dropped, and stacked
    operators collapse to the one nearest the following condition. Rules with
    an empty value are never emitted, because they would match nothing while
    looking like a real filter in the UI.

    Args:
        query: The textual query string (e.g., "Action AND NOT Comedy").
        default_type: The metadata type to apply to each value (e.g., "genre").

    Returns:
        A list of rule dictionaries suitable for _fetch_items_for_complex_group.
        An empty or whitespace-only query returns an empty list.

    """
    if not isinstance(query, str):
        return []

    stripped = query.strip()
    if not stripped:
        return []

    def _parse_item(item_str: str) -> tuple[str, str]:
        """Parse a single query fragment into ``(type, value)``.

        Args:
            item_str: A query fragment like ``"genre:Action"``.

        Returns:
            A ``(type, value)`` tuple, or the default type if unparseable.

        """
        if ":" in item_str:
            t, v = item_str.split(":", 1)
            t = t.strip().lower()
            if t in {"genre", "actor", "studio", "tag", "year"}:
                return t, v.strip()
        return default_type, item_str.strip()

    rules: list[dict[str, Any]] = []
    pending: str | None = None
    negate_next = False
    for is_operator, token in _split_complex_query(stripped):
        if is_operator:
            pending = token if pending is None else _merge_operators(pending, token)
            # "AND NOT" / "OR NOT" negate their operand; keep the base
            # operator aside so the negation is applied exactly once.
            negate_next = pending.endswith("NOT")
            if negate_next:
                pending = pending.split()[0]
            continue

        base = pending or "AND"
        pending = None

        # "NOT Comedy" negates its operand, and stacked NOTs cancel out, so
        # "NOT NOT Comedy" is simply Comedy.
        negated = negate_next
        negate_next = False
        value = token
        while True:
            is_not, remainder = _detect_bare_not(value)
            if not is_not:
                break
            negated = not negated
            value = remainder
        if not value:
            # A lone or trailing NOT negates the *next* condition.
            negate_next = negated
            continue

        item_type, item_value = _parse_item(value)
        if not item_value:
            continue
        rules.append(
            {
                "operator": f"{base} NOT" if negated else base,
                "type": item_type,
                "value": item_value,
            },
        )

    return rules


def preview_group(
    type_name: str,
    val: str,
    url: str,
    api_key: str,
    watch_state: str = "",
    trakt_client_id: str = "",
    tmdb_api_key: str = "",
    mal_client_id: str = "",
    anilist_api_url: str | None = None,
    item_type: str = "",
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve items for a grouping preview.

    Handles both metadata-based sources (genre, actor, studio, tag, year)
    and external list sources (imdb_list, trakt_list, tmdb_list, etc.).
    For metadata types, if *val* contains logical operators (AND, OR, etc.),
    it is parsed as a complex query.

    Args:
        type_name: The source type (genre, actor, studio, tag, year,
            imdb_list, trakt_list, tmdb_list, anilist_list, mal_list,
            letterboxd_list, recommendations).
        val: The filter value or external list URL/ID.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional watch-state filter (watched, unwatched).
        trakt_client_id: Trakt API client ID (required for trakt_list).
        tmdb_api_key: TMDb API key (required for tmdb_list).
        mal_client_id: MyAnimeList client ID (required for mal_list).
        anilist_api_url: Optional custom AniList API URL.
        item_type: Optional restriction to ``"movies"`` or ``"series"``.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
    # External list sources dispatch
    if type_name in _LIST_SOURCE_TYPES:
        items, error, code = _dispatch_list_source(
            type_name,
            "Preview",
            val,
            "",  # sort_order — default to no sort for preview
            url,
            api_key,
            watch_state,
            trakt_client_id=trakt_client_id,
            tmdb_api_key=tmdb_api_key,
            mal_client_id=mal_client_id,
            anilist_api_url=anilist_api_url,
        )
        return _filter_by_item_type(items, item_type), error, code

    # Complex query (metadata-based). Mirrors _resolve_group_source so the
    # preview count matches what the sync will actually link.
    if type_name == "complex" or _COMPLEX_QUERY_RE.search(val):
        rules = parse_complex_query(
            val,
            "genre" if type_name == "complex" else type_name,
        )
        return _fetch_items_for_complex_group(
            "preview",
            rules,
            "",
            url,
            api_key,
            watch_state,
            item_type,
        )
    return _fetch_items_for_metadata_group(
        "preview",
        type_name,
        val,
        "",
        url,
        api_key,
        watch_state,
        item_type,
    )


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

    Args:
        group_name: Name of the group/collection.
        items: Resolved Jellyfin items to add to the collection.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        target_base: Root directory for cover storage.
        dry_run: If True, do not create the collection; return preview items.
        auto_set_library_covers: Whether to set the collection cover image.

    Returns:
        A result dict with ``"group"``, ``"links"``, and optionally
        ``"error"`` and ``"items"`` (in dry run).

    """
    item_ids = [
        item["Id"] for item in items if isinstance(item, dict) and item.get("Id")
    ]
    if not item_ids:
        return {
            "group": group_name,
            "links": 0,
            "error": "No item IDs to add to collection",
        }

    if dry_run:
        preview_items = [
            _build_preview_item(item) for item in items[:_MAX_PREVIEW_ITEMS]
        ]
        return {"group": group_name, "links": len(item_ids), "items": preview_items}

    try:
        collection_id = find_collection_by_name(url, api_key, group_name)
        if collection_id:
            logger.info(
                "Found existing collection %r (id=%s)",
                group_name,
                collection_id,
            )
            # Add items to existing collection; duplicates are safely
            # ignored by Jellyfin
            add_to_collection(url, api_key, collection_id, item_ids)
            logger.info("Added %s items to collection %r", len(item_ids), group_name)
        else:
            # create_collection already includes the item_ids, so
            # no separate add_to_collection needed
            collection_id = create_collection(url, api_key, group_name, item_ids)
            logger.info(
                "Created collection %r (id=%s) with %s items",
                group_name,
                collection_id,
                len(item_ids),
            )
    except (RuntimeError, OSError) as exc:
        return {"group": group_name, "links": 0, "error": str(exc)}

    result: dict[str, Any] = {"group": group_name, "links": len(item_ids)}

    if auto_set_library_covers:
        source_cover = get_cover_path(group_name, target_base)
        if source_cover and Path(source_cover).exists():
            try:
                set_collection_image(url, api_key, collection_id, source_cover)
            except OSError:
                logger.exception("Failed to set collection image for %r", group_name)

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

    Args:
        result: The current result dict for the group.
        group_name: The group name.
        group_dir: The filesystem path of the group directory.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        dry_run: If True, do not actually create the library.
        auto_create_libraries: Whether auto-creation is enabled.
        links_created: Number of symlinks created for this group.
        existing_libraries: List of libraries already created this run.
        target_path_in_jellyfin: Path prefix for Jellyfin library paths.

    Returns:
        The updated result dict.

    """
    # Nested groups ("Anime/Action") are meant to be browsed as folders inside
    # a single library the user points at the tree root, so auto-creating one
    # Jellyfin library per sub-folder would defeat the purpose.
    relpath = normalize_group_relpath(group_name)
    is_nested = relpath is not None and "/" in relpath
    if is_nested:
        logger.info(
            "Skipping library auto-creation for nested grouping %r "
            "(point one library at the tree root instead)",
            group_name,
        )

    if (
        not dry_run
        and auto_create_libraries
        and not is_nested
        and links_created > 0
        and existing_libraries is not None
        and group_name not in existing_libraries
    ):
        logger.info("Creating Jellyfin library for grouping: %r", group_name)
        lib_path = (
            str(Path(target_path_in_jellyfin) / group_name)
            if target_path_in_jellyfin
            else group_dir
        )

        try:
            add_virtual_folder(
                url,
                api_key,
                group_name,
                [lib_path],
                collection_type="mixed",
            )
            logger.info(
                "Successfully created library %r with path %r",
                group_name,
                lib_path,
            )
            existing_libraries.append(group_name)
        except (RuntimeError, OSError) as exc:
            logger.exception("Failed to create Jellyfin library %r", group_name)
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
    """Set the library cover image via API if configured.

    Args:
        group_name: The group name.
        source_cover: Path to the cover image, or ``None``.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        dry_run: If True, do not actually set the cover.
        auto_set_library_covers: Whether auto-setting is enabled.

    """
    if (
        not dry_run
        and auto_set_library_covers
        and source_cover
        and Path(source_cover).exists()
    ):
        logger.info("Setting cover image for library %r via API", group_name)
        set_virtual_folder_image(url, api_key, group_name, source_cover)


def _create_or_preview_link(
    item: dict[str, Any],
    host_path: str,
    dest_path: str,
    file_name: str,
    dry_run: bool,
    preview_items: list[dict[str, Any]],
) -> bool:
    """Create a symlink or append a preview item.

    Args:
        item: The Jellyfin item dict.
        host_path: The resolved host-side path of the media file.
        dest_path: The destination directory for the symlink.
        file_name: The name of the symlink to create.
        dry_run: If True, record a preview entry instead of creating a symlink.
        preview_items: List to append preview entries to.

    Returns:
        True if the link was (or would be) created successfully.

    """
    if dry_run:
        if len(preview_items) < _MAX_PREVIEW_ITEMS:
            preview_items.append(_build_preview_item(item, file_name))
        return True
    try:
        Path(dest_path).symlink_to(host_path)
        logger.info("Created symlink: %s -> %s", dest_path, host_path)
    except OSError:
        logger.exception("Error creating symlink %s", dest_path)
        return False
    else:
        return True


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

    Args:
        items: The resolved Jellyfin items to link.
        group_dir: The destination directory for symlinks.
        group_name: The group name (for logging).
        jellyfin_root: Jellyfin-side media path prefix.
        host_root: Host-side media path prefix.
        sort_order: The sort order to use for numbering.
        dry_run: If True, do not create symlinks; return preview items.

    Returns:
        A tuple of ``(links_created, preview_items)``.

    """
    use_prefix: bool = bool(sort_order)
    width: int = max(
        len(str(len(items))) if items else _MIN_PREFIX_WIDTH,
        _MIN_PREFIX_WIDTH,
    )
    links_created: int = 0
    preview_items: list[dict[str, Any]] = []
    # Track destination filenames already claimed this run so that two
    # distinct items resolving to the same basename (e.g. two movies both
    # named "Movie (2000).mkv" in different folders) do not silently drop
    # the second one — it gets a numeric suffix instead.
    used_dest_names: set[str] = set()
    if not dry_run:
        # Seed with names already present on disk so a generated suffix can
        # never collide with a pre-existing file (e.g. a leftover from a
        # partial/aborted run, a manually-placed file, or a nested group's
        # own symlink). Without this, a collision with an on-disk file would
        # make symlink_to() raise FileExistsError and silently drop the link.
        with contextlib.suppress(OSError):
            # Directory may not exist yet or be unreadable — nothing to seed.
            # Reserve every existing entry name (files, directories, and
            # dangling symlinks alike) so a generated suffix can never collide
            # with anything already on disk.
            used_dest_names.update(entry.name for entry in Path(group_dir).iterdir())

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue

        source_path: str | None = item.get("Path")
        if not source_path or not isinstance(source_path, str):
            logger.info("Item %s has no valid Path — skipping", item.get("Id"))
            continue

        host_path = _translate_path(source_path, jellyfin_root, host_root)
        if host_path != source_path:
            logger.info("Translated path: %s -> %s", source_path, host_path)

        if not Path(host_path).exists():
            logger.info("Skipping (path not found on host): %s", host_path)
            continue

        file_name: str = Path(host_path).name
        if use_prefix:
            file_name = f"{str(idx).zfill(width)} - {file_name}"

        # Disambiguate collisions with an already-claimed destination name.
        base_name = Path(file_name).stem
        ext = Path(file_name).suffix
        candidate = file_name
        suffix = 2
        while candidate in used_dest_names:
            candidate = f"{base_name} ({suffix}){ext}"
            suffix += 1
        file_name = candidate
        used_dest_names.add(file_name)

        dest_path: str = str(Path(group_dir) / file_name)
        if _create_or_preview_link(
            item,
            host_path,
            dest_path,
            file_name,
            dry_run,
            preview_items,
        ):
            links_created += 1

    action = "Would create" if dry_run else "Created"
    logger.info("%s %s symlinks for %r", action, links_created, group_name)

    return links_created, preview_items


def _clear_group_directory(group_dir: Path) -> None:
    """Remove a group's own contents, leaving nested child groups intact.

    A group's directory can double as the parent of nested groups: with
    both ``Action`` and ``Action/Filme`` configured, ``<target>/Action``
    holds this group's symlinks *and* the ``Filme`` subdirectory. Wiping
    the whole tree would delete the child group's links, and whether they
    came back depended on the order the groups happened to sync in.

    Only the entries this group owns are removed — its symlinks and cover
    image. Subdirectories are left alone; a child group cleans up its own
    directory when it syncs.

    Args:
        group_dir: The group's directory.

    """
    try:
        entries = list(group_dir.iterdir())
    except FileNotFoundError:
        # Raced with something else removing it, or it never existed —
        # either way there is nothing to clean.
        return

    for entry in entries:
        # is_dir() follows symlinks, so check for a link first — a symlink
        # pointing at a season folder is ours to remove, a real directory
        # belongs to a nested group.
        if entry.is_symlink() or not entry.is_dir():
            entry.unlink()


def _prepare_group_directory(
    group_dir: str,
    group_name: str,
    target_base: str,
    dry_run: bool,
) -> str | None:
    """Clean up and recreate the group directory, copying a cover image if available.

    If *dry_run* is ``True`` the directory is not modified, but the cover path
    is still resolved (if any) so callers can use it for preview purposes.

    Args:
        group_dir: The filesystem path of the group directory.
        group_name: The group name (for cover lookup).
        target_base: The root target directory (for cover lookup).
        dry_run: If True, do not actually create the directory.

    Returns:
        The path to the source cover image (or ``None`` if none found).

    Raises:
        OSError: If the directory cannot be cleaned or created (only in
            non-dry-run mode).

    """
    source_cover: str | None = get_cover_path(group_name, target_base)

    if not dry_run:
        if Path(group_dir).exists():
            logger.info("Cleaning existing directory: %s", group_dir)
            _clear_group_directory(Path(group_dir))
        Path(group_dir).mkdir(parents=True, exist_ok=True)

        if source_cover:
            poster_dest = str(Path(group_dir) / "poster.jpg")
            try:
                shutil.copy2(source_cover, poster_dest)
                logger.info(
                    "Copied cover image from %s to %s",
                    source_cover,
                    poster_dest,
                )
            except OSError:
                logger.exception("Failed to copy cover image")

    return source_cover


def _dispatch_list_source(
    source_type: str,
    group_name: str,
    source_value: str,
    sort_order: str,
    url: str,
    api_key: str,
    watch_state: str,
    *,
    trakt_client_id: str = "",
    tmdb_api_key: str = "",
    mal_client_id: str = "",
    anilist_api_url: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Dispatch to the correct external-list fetch function based on *source_type*.

    Each external list source has a slightly different parameter signature;
    this helper normalises the call site so the dispatch table can remain
    a simple name-to-function mapping.

    Args:
        source_type: The external list type (e.g. ``"imdb_list"``).
        group_name: The group name (for logging).
        source_value: The list URL or identifier.
        sort_order: The requested sort order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        watch_state: Optional watch-state filter.
        trakt_client_id: Trakt API client ID.
        tmdb_api_key: TMDb API key.
        mal_client_id: MyAnimeList client ID.
        anilist_api_url: Optional custom AniList API URL.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
    match source_type:
        case "imdb_list":
            return _fetch_items_for_imdb_group(
                group_name,
                source_value,
                sort_order,
                url,
                api_key,
                watch_state,
            )
        case "trakt_list":
            return _fetch_items_for_trakt_group(
                group_name,
                source_value,
                sort_order,
                url,
                api_key,
                trakt_client_id,
                watch_state,
            )
        case "tmdb_list":
            return _fetch_items_for_tmdb_group(
                group_name,
                source_value,
                sort_order,
                url,
                api_key,
                tmdb_api_key,
                watch_state,
            )
        case "anilist_list":
            return _fetch_items_for_anilist_group(
                group_name,
                source_value,
                sort_order,
                url,
                api_key,
                watch_state,
                anilist_api_url=anilist_api_url,
            )
        case "mal_list":
            return _fetch_items_for_mal_group(
                group_name,
                source_value,
                sort_order,
                url,
                api_key,
                mal_client_id,
                watch_state,
            )
        case "letterboxd_list":
            return _fetch_items_for_letterboxd_group(
                group_name,
                source_value,
                sort_order,
                url,
                api_key,
                watch_state,
            )
        case "recommendations":
            return _fetch_items_for_recommendations_group(
                group_name,
                source_value,
                sort_order,
                url,
                api_key,
                tmdb_api_key,
                watch_state,
            )
        case _:
            return [], f"Unknown source type: {source_type}", 400


def _optional_group_str(
    group: dict[str, Any], key: str, default: str = ""
) -> str | None:
    """Read an optional string field from a group, treating ``null`` as empty.

    ``config.json`` is user-editable, so a field that the web form always
    writes as a string can hold a number, a list or an object.  The values
    read here are used as dict keys and set memberships
    (``source_type in _LIST_SOURCE_TYPES``, ``sort_order in SORT_MAP``), so an
    unhashable list raised ``TypeError: unhashable type: 'list'`` and aborted
    the whole sync run instead of failing that one group.

    Args:
        group: The group configuration dict.
        key: The field name to read.
        default: Value returned when the field is absent or JSON ``null``.

    Returns:
        The field value, or ``None`` when it holds a non-string type so the
        caller can report a per-group error.

    """
    value = group.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        logger.warning(
            "Ignoring group with non-string '%s' (expected string, got %s): %r",
            key,
            type(value).__name__,
            value,
        )
        return None
    return value


def _group_display_name(group: dict[str, Any]) -> str | None:
    """Return a group's trimmed name, or ``None`` when it is not a string.

    ``config.json`` is user-editable, so ``groups[].name`` can hold a number,
    a list or ``null`` even though the web form always writes a string.
    Calling ``.strip()`` on such a value raised ``AttributeError``, which
    aborted the whole ``run_sync`` loop and surfaced as an HTTP 500 for
    ``POST /api/sync`` — one bad entry took down every other group.  Callers
    turn ``None`` into a per-group error instead.

    Args:
        group: The group configuration dict.

    Returns:
        The stripped name (``""`` when absent or JSON ``null``), or ``None``
        when the value has another type.

    """
    raw_name = group.get("name")
    if raw_name is None:
        return ""
    if not isinstance(raw_name, str):
        logger.warning(
            "Ignoring group with non-string name (expected string, got %s): %r",
            type(raw_name).__name__,
            raw_name,
        )
        return None
    return raw_name.strip()


def _resolve_group_source(
    group: dict[str, Any],
    group_name: str,
    source_type: str | None,
    source_value: str | None,
    sort_order: str,
    url: str,
    api_key: str,
    trakt_client_id: str,
    tmdb_api_key: str,
    mal_client_id: str,
    watch_state: str,
    anilist_api_url: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Resolve items for a group based on its source configuration.

    Dispatches to the appropriate fetch function based on *source_type*.
    External list sources (IMDb, Trakt, etc.) use their dedicated fetchers;
    metadata sources use Jellyfin API filters or complex rule evaluation.

    Args:
        group: The group configuration dict.
        group_name: The group name (for logging).
        source_type: The source type (e.g. ``"genre"``, ``"imdb_list"``).
        source_value: The source value (e.g. ``"Action"``, list URL).
        sort_order: The requested sort order.
        url: Jellyfin base URL.
        api_key: Jellyfin API key.
        trakt_client_id: Trakt API client ID.
        tmdb_api_key: TMDb API key.
        mal_client_id: MyAnimeList client ID.
        watch_state: Optional watch-state filter.
        anilist_api_url: Optional custom AniList API URL.

    Returns:
        A ``(items, error, status_code)`` tuple.

    """
    item_type = _optional_group_str(group, "item_type")
    if item_type is None:
        item_type = ""
    item_type = item_type.strip().lower()

    if source_type in _LIST_SOURCE_TYPES:
        items, error, code = _dispatch_list_source(
            source_type,
            group_name,
            source_value or "",
            sort_order,
            url,
            api_key,
            watch_state,
            trakt_client_id=trakt_client_id,
            tmdb_api_key=tmdb_api_key,
            mal_client_id=mal_client_id,
            anilist_api_url=anilist_api_url,
        )
        return _filter_by_item_type(items, item_type), error, code
    if isinstance(group.get("rules"), list) and group["rules"]:
        rules_list = group["rules"]
        return _fetch_items_for_complex_group(
            group_name,
            rules_list,
            sort_order,
            url,
            api_key,
            watch_state,
            item_type,
        )

    val_str = str(source_value or "")
    # "complex" is a source type in its own right; the metadata types are
    # included because their *value* may carry operators ("Action OR Drama").
    # Without the explicit "complex" case the group fell through to the
    # metadata fetch, which has no filter for it and returned the entire
    # library.
    # A "complex" group always takes this path — even a single condition
    # ("genre:Action") is a rule expression, not a metadata filter value.
    is_complex_type = source_type == "complex"
    if is_complex_type or (
        source_type in _COMPLEX_QUERY_SOURCE_TYPES and _COMPLEX_QUERY_RE.search(val_str)
    ):
        # A bare "complex" group has no implicit field, so rules must name
        # their own ("genre:Action"); default to genre for the rest.
        default_type = "genre" if is_complex_type else str(source_type)
        rules = parse_complex_query(val_str, default_type)
        return _fetch_items_for_complex_group(
            group_name,
            rules,
            sort_order,
            url,
            api_key,
            watch_state,
            item_type,
        )
    return _fetch_items_for_metadata_group(
        group_name,
        source_type,
        source_value,
        sort_order,
        url,
        api_key,
        watch_state,
        item_type,
    )


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
    anilist_api_url: str | None = None,
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
        auto_create_libraries: Whether to auto-create Jellyfin libraries.
        auto_set_library_covers: Whether to set library cover images.
        existing_libraries: List of libraries already created this run.
        target_path_in_jellyfin: Path prefix for Jellyfin library paths.
        anilist_api_url: AniList API URL (may be None).

    Returns:
        A result dict with keys ``"group"``, ``"links"``, optionally ``"error"``,
        and ``"items"`` (the first 100 matches) if *dry_run* is True.

    """
    group_name = _group_display_name(group)
    if group_name is None:
        return {"group": "(unnamed)", "links": 0, "error": "Invalid group name"}
    if not group_name:
        return {"group": "(unnamed)", "links": 0, "error": "Empty group name"}

    # A name may describe a nested folder ("Anime/Action"). Normalising here
    # keeps the resulting directory inside target_base — important because
    # _prepare_group_directory rmtree()s it.
    relpath: str | None = normalize_group_relpath(group_name)
    if relpath is None:
        return {"group": group_name, "links": 0, "error": "Invalid group name"}

    group_dir: str = str(Path(target_base).joinpath(*relpath.split("/")))
    sort_order = _optional_group_str(group, "sort_order")
    if sort_order is None:
        return {"group": group_name, "links": 0, "error": "Invalid sort order"}
    source_type = _optional_group_str(group, "source_type") or None
    if source_type is None and group.get("source_type") is not None:
        return {"group": group_name, "links": 0, "error": "Invalid source type"}
    source_value = _optional_group_str(group, "source_value") or None
    if source_value is None and group.get("source_value") is not None:
        return {"group": group_name, "links": 0, "error": "Invalid source value"}

    logger.info(
        "Processing group: %r -> %s  (sort_order=%r)",
        group_name,
        group_dir,
        sort_order,
    )

    try:
        source_cover = _prepare_group_directory(
            group_dir,
            group_name,
            target_base,
            dry_run,
        )
    except OSError as exc:
        return {"group": group_name, "links": 0, "error": f"Directory error: {exc!s}"}

    # --- Resolve items ---
    watch_state = _optional_group_str(group, "watch_state")
    if watch_state is None:
        return {"group": group_name, "links": 0, "error": "Invalid watch state"}
    items, error, _status_code = _resolve_group_source(
        group,
        group_name,
        source_type,
        source_value,
        sort_order,
        url,
        api_key,
        trakt_client_id,
        tmdb_api_key,
        mal_client_id,
        watch_state,
        anilist_api_url=anilist_api_url,
    )

    if error is not None:
        return {"group": group_name, "links": 0, "error": error}

    if not items:
        return {"group": group_name, "links": 0}

    # Apply in-memory sort for external-list sources when a non-list-order
    # sort is requested (Jellyfin cannot sort external lists for us).
    if (
        source_type in _LIST_SOURCE_TYPES
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
        items,
        group_dir,
        group_name,
        jellyfin_root,
        host_root,
        sort_order,
        dry_run,
    )
    result: dict[str, Any] = {"group": group_name, "links": links_created}
    if dry_run:
        result["items"] = preview_items

    result = _auto_create_library(
        result,
        group_name,
        group_dir,
        url,
        api_key,
        dry_run,
        auto_create_libraries,
        links_created,
        existing_libraries,
        target_path_in_jellyfin,
    )
    _auto_set_library_cover(
        group_name,
        source_cover,
        url,
        api_key,
        dry_run,
        auto_set_library_covers,
    )

    return result


def _parse_mmdd(value: str | None) -> tuple[int, int]:
    """Parse an ``MM-DD`` string into a ``(month, day)`` tuple.

    Validates that month is 1-12 and that *day* is valid for the given month.
    Returns ``(0, 0)`` for unparseable or out-of-range values so they never match.

    Args:
        value: The ``MM-DD`` string to parse, or ``None``.

    Returns:
        A ``(month, day)`` tuple, or ``(0, 0)`` for invalid input.

    Examples:
        >>> _parse_mmdd("06-15")
        (6, 15)
        >>> _parse_mmdd("")
        (0, 0)
        >>> _parse_mmdd("13-01")
        (0, 0)
        >>> _parse_mmdd(None)
        (0, 0)

    """
    if not isinstance(value, str) or value.strip() == "":
        return (0, 0)
    parts = value.strip().split("-", 1)
    if len(parts) < 2:
        logger.debug("Invalid MM-DD format: %r — missing dash", value)
        return (0, 0)
    try:
        month = int(parts[0])
        day = int(parts[1])
    except ValueError:
        logger.debug("Invalid MM-DD format: %r — non-numeric parts", value)
        return (0, 0)
    if not (1 <= month <= 12):
        logger.debug("Invalid MM-DD format: %r — month out of range", value)
        return (0, 0)
    # Use a leap year (2024) for monthrange so Feb 29 is valid
    _, max_day = calendar.monthrange(2024, month)
    if not (1 <= day <= max_day):
        logger.debug(
            "Invalid MM-DD format: %r — day out of range for month %d",
            value,
            month,
        )
        return (0, 0)
    return (month, day)


def _is_in_season(start_str: str | None, end_str: str | None) -> bool:
    """Check if the current date is within the seasonal window [start, end).

    Both start and end must be ``MM-DD`` strings.  The window is **inclusive**
    of *start* and **exclusive** of *end* so that two windows can cleanly
    abut without overlap.  Year-boundaries are handled correctly (e.g.
    ``12-01`` to ``01-01`` means the period covering all of December).

    Args:
        start_str: Start date in ``MM-DD`` format.
        end_str: End date in ``MM-DD`` format.

    Returns:
        ``True`` if the current date falls within the seasonal window.
        ``True`` also when inputs are malformed (graceful degradation
        — treats a broken season rule as "always in season").

    """
    if not isinstance(start_str, str) or not isinstance(end_str, str):
        return True

    now = datetime.now(tz=UTC)
    current = (now.month, now.day)

    s = _parse_mmdd(start_str)
    e = _parse_mmdd(end_str)

    if s == (0, 0) or e == (0, 0):
        return True

    if s <= e:
        # Simple case: window stays within one calendar year (e.g., 06-01 to 08-31)
        return s <= current < e
    # Over-year case: window spans across Jan 1st (e.g., 12-01 to 01-01)
    return current >= s or current < e


def _fetch_existing_libraries(url: str, api_key: str) -> list[str]:
    """Return existing Jellyfin libraries, logging any fetch errors.

    Args:
        url: Jellyfin base URL.
        api_key: Jellyfin API key.

    Returns:
        A list of library names (strings).

    """
    try:
        libraries = get_libraries(url, api_key)
        logger.info("Found %s existing virtual folders in Jellyfin", len(libraries))
    except (RuntimeError, OSError) as exc:
        logger.warning("Warning: Could not fetch existing libraries: %s", exc)
        return []
    else:
        return libraries


def _maybe_handle_seasonal(
    group: dict[str, Any],
    name: str,
    target_base: str,
    dry_run: bool,
) -> dict[str, Any] | None:
    """If the group is seasonal and out of season, clean up and return a result.

    Args:
        group: The group configuration dict.
        name: The group name.
        target_base: The root target directory.
        dry_run: If True, do not actually remove directories.

    Returns:
        A result dict if the group is out of season, or ``None`` if it is
        in season (or not a seasonal group).

    """
    if not group.get("seasonal_enabled"):
        return None
    start = group.get("seasonal_start")
    end = group.get("seasonal_end")
    if _is_in_season(start, end):
        return None
    if not dry_run and name:
        # Resolve the directory exactly as _process_group does, so an
        # out-of-season group cleans up the *same* directory that would
        # otherwise be created/synced.  A name may describe a nested folder
        # ("Anime/Action") and may carry surrounding whitespace or redundant
        # slashes; normalising here keeps the two paths in lock-step.  If the
        # name is invalid (e.g. contains ".."), _process_group would reject it
        # anyway, so there is nothing to clean up.
        relpath = normalize_group_relpath(name)
        if relpath is not None:
            group_dir = str(Path(target_base).joinpath(*relpath.split("/")))
            if Path(group_dir).is_dir():
                logger.info(
                    "Seasonal group %r is out of season. Deleting directory: %s",
                    name,
                    group_dir,
                )
                try:
                    shutil.rmtree(group_dir)
                except OSError:
                    logger.exception(
                        "Failed to delete directory for out-of-season group %r: %s",
                        name,
                        group_dir,
                    )
    return {"group": name or "(unnamed)", "links": 0, "status": "out_of_season"}


def run_sync(
    config: dict[str, Any],
    dry_run: bool = False,
    group_names: list[str] | None = None,
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
        config.get("media_path_in_jellyfin") or config.get("jellyfin_root", ""),
    ).strip()
    host_root: str = str(
        config.get("media_path_on_host") or config.get("host_root", ""),
    ).strip()
    trakt_client_id: str = str(config.get("trakt_client_id") or "").strip()
    tmdb_api_key: str = str(config.get("tmdb_api_key") or "").strip()
    mal_client_id: str = str(config.get("mal_client_id") or "").strip()
    anilist_api_url: str | None = (
        str(config.get("anilist_api_url") or "").strip() or None
    )
    auto_create_libraries: bool = bool(config.get("auto_create_libraries", False))
    auto_set_library_covers: bool = bool(config.get("auto_set_library_covers", False))
    target_path_in_jellyfin: str = str(
        config.get("target_path_in_jellyfin") or "",
    ).strip()

    if not url or not api_key or not target_base:
        msg = "Server settings or target path not configured"
        raise ValueError(msg)

    if not dry_run:
        try:
            Path(target_base).mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            msg = (
                f"Cannot create target directory '{target_base}'"
                " (permission denied). Please choose a path the application"
                " can write to."
            )
            raise ValueError(msg) from exc

    logger.info("Starting sync to: %s", target_base)
    if jellyfin_root and host_root:
        logger.info("Path translation active: %s -> %s", jellyfin_root, host_root)

    existing_libraries: list[str] = []
    if auto_create_libraries:
        existing_libraries = _fetch_existing_libraries(url, api_key)

    # The full-library cache is now TTL-based and persists across
    # run_sync() calls.  Stale entries are evicted on access in
    # _fetch_full_library, so we no longer clear the cache here.

    results: list[dict[str, Any]] = []
    if not groups:
        logger.warning("No groups configured — nothing to sync")
        return results

    for group in groups:
        if not isinstance(group, dict):
            logger.info("Skipping invalid group entry: %s", group)
            continue

        name = _group_display_name(group)
        if name is None:
            # A non-string name is reported per group rather than raising,
            # so one malformed entry cannot abort the whole sync run.
            results.append(
                {"group": "(unnamed)", "links": 0, "error": "Invalid group name"},
            )
            continue
        if group_names is not None and (not name or name not in group_names):
            continue

        seasonal_result = _maybe_handle_seasonal(group, name, target_base, dry_run)
        if seasonal_result is not None:
            results.append(seasonal_result)
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
            anilist_api_url=anilist_api_url,
        )
        results.append(result)

    return results


def run_cleanup_broken_symlinks(config: dict[str, Any]) -> int:
    """Scan the target directory for broken symlinks and remove them.

    Handles both broken file symlinks and broken symlink directories.
    Uses ``pathlib.Path.rglob`` to traverse all entries regardless of
    symlink target validity, which catches broken directory symlinks
    that ``os.walk`` would silently skip.

    Args:
        config: The application configuration dict.

    Returns:
        The number of broken symlinks deleted.

    """
    target_base: str = str(config.get("target_path") or "")

    if not target_base or not Path(target_base).is_dir():
        logger.info("Cleanup aborted: invalid target base path '%s'", target_base)
        return 0

    deleted_count = 0

    # Use rglob to catch broken symlink directories that os.walk would miss
    for path in Path(target_base).rglob("*"):
        if path.is_symlink() and not path.exists():
            try:
                path.unlink()
                logger.info("Deleted broken symlink: %s", path)
                deleted_count += 1
            except OSError:
                logger.exception("Error deleting broken symlink %s", path)

    if deleted_count:
        logger.info(
            "Cleanup complete: deleted %s broken symlink(s)",
            deleted_count,
        )
    else:
        logger.debug("Cleanup complete: no broken symlinks found")

    return deleted_count
