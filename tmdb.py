"""tmdb.py - TMDb API list fetching utilities.

Provides a single public function for fetching TMDb IDs from a
TMDb v3 list.
"""

from __future__ import annotations

import logging
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
    return cast("dict[str, Any]", resp.json())


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
        if tmdb_id is None or isinstance(tmdb_id, bool):
            continue
        str_id = str(tmdb_id)
        if str_id not in seen:
            seen.add(str_id)
            ids.append(str_id)


def _normalize_tmdb_list_id(list_id: str) -> str:
    """Normalize *list_id*: strip whitespace, extract from URL if needed.

    Args:
        list_id: The TMDb list ID.

    """
    list_id = list_id.strip()
    if "themoviedb.org/list/" in list_id:
        parsed = urlparse(list_id)
        list_id = parsed.path.strip("/").split("/")[-1]
    return list_id


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
    if not list_id:
        msg = "A TMDb List ID is required."
        raise ValueError(msg)

    list_id = _normalize_tmdb_list_id(list_id)

    ids: list[str] = []
    seen: set[str] = set()
    page: int = 1

    while True:
        data = _fetch_tmdb_page(list_id, api_key, page)
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
