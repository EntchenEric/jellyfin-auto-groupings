"""tmdb.py - TMDb API list fetching utilities.

Provides a single public function for fetching TMDb IDs from a
TMDb v3 list.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, cast
from urllib.parse import urlparse

import requests

import network

__all__ = ["fetch_tmdb_list", "get_tmdb_recommendations"]

logger = logging.getLogger(__name__)

_TMDB_API_BASE: str = "https://api.themoviedb.org/3"
_DEFAULT_TMDB_LANGUAGE: str = "en-US"
_MAX_TMDB_PAGES: int = 50

# Maximum number of attempts per item when retrying a 429 rate-limit
# response.  A 429 means "slow down and retry", not "skip this item", so a
# bounded retry loop prevents a rate-limited item's recommendations from
# being silently dropped while still bounding the total wait time.
_MAX_RECOMMENDATION_RETRIES: int = 3

#: Hosts that may serve a TMDb list page. The previous check was a substring
#: test on the raw input, so any host mentioning ``themoviedb.org`` was
#: accepted and its trailing path segment was used as the list ID.
_TMDB_HOSTS: frozenset[str] = frozenset({"themoviedb.org", "www.themoviedb.org"})

# Matches the list-ID segment of a TMDb list path, e.g. ``/list/8204231``.
_TMDB_LIST_PATH_PATTERN: re.Pattern[str] = re.compile(r"/list/(\d+)(?:/|$)")

# A bare list ID is passed through to the API as a single path segment.
_TMDB_LIST_ID_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]+$")


def _fetch_tmdb_page(
    list_id: str,
    api_key: str,
    page: int,
) -> dict[str, Any]:
    """Fetch a single TMDb list page and return the parsed JSON response.

    Args:
        list_id: The TMDb list ID.
        api_key: TMDb API key.
        page: Page number to fetch.

    Raises:
        RuntimeError: If an HTTP error occurs.

    """
    url = f"{_TMDB_API_BASE}/list/{list_id}"
    params = {
        "api_key": api_key,
        "page": str(page),
        "language": _DEFAULT_TMDB_LANGUAGE,
    }
    try:
        resp = network.get(url, params=params, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        msg = f"Failed to fetch TMDb list page {page}: {exc}"
        raise RuntimeError(msg) from exc
    try:
        data = resp.json()
    except ValueError as exc:
        msg = f"Invalid JSON response from TMDb API on page {page}: {exc}"
        raise RuntimeError(msg) from exc
    # ``fetch_tmdb_list`` reads ``items``/``total_pages`` off this value. A
    # bare list or string body raised ``AttributeError``, which the sync
    # layer does not catch, so one malformed page aborted the whole run.
    # ``fetch_tmdb_list`` converts this ``TypeError`` to ``RuntimeError``,
    # the type every caller handles.
    if not isinstance(data, dict):
        msg = f"expected a JSON object, got {type(data).__name__}"
        raise TypeError(msg)
    return cast("dict[str, Any]", data)


def _collect_tmdb_ids_from_page(
    data: dict[str, Any],
    ids: list[str],
    seen: set[str],
) -> None:
    """Extract TMDb IDs from a page response, deduplicating via *seen*.

    Args:
        data: The API response data dict.
        ids: List to collect IDs into.
        seen: Set of already-seen IDs for deduplication.

    """
    items = data.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        tmdb_id = item.get("id")
        # TMDb sends a number, but a malformed item can carry an object or a
        # list. ``str(tmdb_id)`` then produced a garbage provider id such as
        # ``"{'a': 1}"`` that was looked up in the library and, worse, written
        # into the group's stored id list. Only numbers and strings are IDs.
        if isinstance(tmdb_id, bool) or not isinstance(tmdb_id, (int, str)):
            continue
        str_id = str(tmdb_id).strip()
        if not str_id:
            continue
        if str_id not in seen:
            seen.add(str_id)
            ids.append(str_id)


def _normalize_tmdb_list_id(list_id: str) -> str:
    """Normalize *list_id*: strip whitespace, extract the ID from a URL.

    A pasted TMDb list URL carries the ID in the *first* path segment after
    ``/list/``: real URLs are rendered as ``/list/8204231/my-list-name``. The
    previous implementation took the last path segment, so a correct URL sent
    the list's *slug* to the API and the group failed with a 404 (or, for a
    slug that happens to be numeric, fetched an unrelated list).

    A URL is accepted only when it points at a TMDb host, and the ID is read
    from the path rather than from the whole input, so a lookalike host or a
    stray mention of ``themoviedb.org`` cannot select a list.

    Args:
        list_id: A bare list ID or a full TMDb list URL.

    Returns:
        The bare list ID, or the empty string when *list_id* is blank.

    Raises:
        ValueError: If *list_id* is neither a bare ID nor a genuine TMDb list
            URL naming a numeric list.

    """
    candidate = list_id.strip()
    if not candidate:
        return ""

    if "themoviedb.org" in candidate:
        # Tolerate a scheme-less input such as ``themoviedb.org/list/123``;
        # without a scheme ``urlparse`` reports an empty hostname.
        parsed = urlparse(candidate if "//" in candidate else f"https://{candidate}")
        host = (parsed.hostname or "").lower()
        if parsed.scheme in ("http", "https") and (
            host in _TMDB_HOSTS or host.endswith(".themoviedb.org")
        ):
            path_match = _TMDB_LIST_PATH_PATTERN.search(parsed.path)
            if path_match:
                return path_match.group(1)
        msg = (
            f"Invalid TMDb list URL: {list_id!r}. "
            "Expected format: https://www.themoviedb.org/list/8204231"
        )
        raise ValueError(msg)

    if not _TMDB_LIST_ID_PATTERN.match(candidate):
        msg = f"Invalid TMDb list ID: {list_id!r}. Expected a numeric list ID."
        raise ValueError(msg)
    return candidate


def fetch_tmdb_list(list_id: str, api_key: str) -> list[str]:
    """Fetch a TMDb v3 list and return its items as TMDb IDs in list order.

    Args:
        list_id: TMDb list ID (numeric or alphanumeric).
        api_key: TMDb API Key (v3).

    Returns:
        An ordered list of TMDb IDs (as strings).

    Raises:
        ValueError: If *api_key* or *list_id* is empty.
        RuntimeError: If an HTTP error occurs while fetching a page.

    """
    if not api_key:
        msg = "A TMDb API Key is required to fetch TMDb lists."
        raise ValueError(msg)

    # Normalise before the emptiness check so a whitespace-only value is
    # rejected instead of being sent to the API as ``/list/``.
    list_id = _normalize_tmdb_list_id(list_id)
    if not list_id:
        msg = "A TMDb List ID is required."
        raise ValueError(msg)

    ids: list[str] = []
    seen: set[str] = set()
    page: int = 1

    while True:
        try:
            data = _fetch_tmdb_page(list_id, api_key, page)
        except TypeError as exc:
            msg = f"Unexpected TMDb API response shape for list {list_id!r}: {exc}"
            raise RuntimeError(msg) from exc
        _collect_tmdb_ids_from_page(data, ids, seen)

        items = data.get("items")
        if not isinstance(items, list) or not items:
            break

        total_pages = data.get("total_pages", 1)
        # A malformed ``total_pages`` must not end the walk early, so a
        # non-integer value is treated as "unknown" (keep paginating until an
        # empty page) rather than as "this was the last page".
        if not isinstance(total_pages, int) or isinstance(total_pages, bool):
            total_pages = page + 1
        if page >= total_pages:
            break
        if page >= _MAX_TMDB_PAGES:
            # The README promises a warning when the cap truncates a list;
            # stopping silently makes a partial result look complete.
            logger.warning(
                "Stopping after %d pages (the safety limit) — the TMDb list "
                "%r has more entries than were fetched",
                _MAX_TMDB_PAGES,
                list_id,
            )
            break
        page += 1

    return ids


def get_tmdb_recommendations(
    items_with_type: list[tuple[str, str]],
    api_key: str,
) -> list[str]:
    """Fetch recommendations for a list of TMDb IDs.

    Args:
        items_with_type: List of (tmdb_id, media_type) where media_type
            is "movie" or "tv".
        api_key: TMDb API Key (v3).

    Returns:
        A list of recommended TMDb IDs (as strings), sorted by
        recommendation frequency and rank.

    Raises:
        ValueError: If *api_key* is empty.

    """
    if not api_key:
        msg = "A TMDb API Key is required to fetch TMDb recommendations."
        raise ValueError(msg)

    recommendation_counts: dict[str, float] = {}

    for tmdb_id, media_type in items_with_type:
        url = f"{_TMDB_API_BASE}/{media_type}/{tmdb_id}/recommendations"
        params = {
            "api_key": api_key,
            "language": _DEFAULT_TMDB_LANGUAGE,
            "page": "1",
        }
        # Retry on 429 rate limits (bounded) so a rate-limited item's
        # recommendations are not silently dropped.  Other non-200 statuses
        # and request/parse errors still skip the item as before.
        for _attempt in range(_MAX_RECOMMENDATION_RETRIES):
            try:
                resp = network.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if not isinstance(data, dict):
                        logger.debug(
                            "Skipping recommendation item with non-object payload",
                        )
                        break
                    for i, rec in enumerate(data.get("results", [])):
                        # A recommendation without an ``id`` used to become the
                        # literal string ``"None"``, which then went to Jellyfin
                        # as a TMDb provider id. Skip it instead.
                        if not isinstance(rec, dict):
                            continue
                        raw_id = rec.get("id")
                        if raw_id is None or isinstance(raw_id, bool):
                            continue
                        rec_id = str(raw_id)
                        score = 1.0 / (i + 1)  # Higher weight for top recommendations
                        recommendation_counts[rec_id] = (
                            recommendation_counts.get(rec_id, 0.0) + score
                        )
                    break
                if resp.status_code == 429:
                    # Rate limited — back off to avoid further 429s, then retry
                    retry_after = resp.headers.get("Retry-After")
                    wait = (
                        int(retry_after) if retry_after and retry_after.isdigit() else 1
                    )
                    logger.debug(
                        "TMDb rate limited (429) — sleeping %ds",
                        wait,
                    )
                    time.sleep(wait)
                    continue
                # Other non-200 status: skip this item.
                break
            except (requests.exceptions.RequestException, ValueError):
                logger.debug("Skipping failed recommendation item", exc_info=True)
                break

    # Sort items by their accumulated score
    sorted_recs = sorted(
        recommendation_counts.items(),
        key=lambda x: x[1],
        reverse=True,
    )
    return [rec_id for rec_id, _ in sorted_recs]
