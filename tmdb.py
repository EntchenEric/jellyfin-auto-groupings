"""tmdb.py - TMDb API list fetching utilities.

Provides a single public function for fetching TMDb IDs from a
TMDb v3 list.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from urllib.parse import urlparse

import requests

import network

__all__ = ["fetch_tmdb_list", "get_tmdb_recommendations"]

logger = logging.getLogger(__name__)

_TMDB_API_BASE: str = "https://api.themoviedb.org/3"
_DEFAULT_TMDB_LANGUAGE: str = "en-US"
_MAX_TMDB_PAGES: int = 50


def _fetch_tmdb_page(
    list_id: str,
    api_key: str,
    page: int,
) -> dict[str, Any]:
    """Fetch a single TMDb list page and return the parsed JSON response.

    Raises:
        RuntimeError: If an HTTP error occurs.

    Args:
        list_id: The TMDb list ID.
        api_key: Jellyfin API key.
        page: Page number to fetch.

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
    for item in data.get("items", []):
        tmdb_id = item.get("id")
        if tmdb_id:
            str_id = str(tmdb_id)
            if str_id not in seen:
                seen.add(str_id)
                ids.append(str_id)


def _normalize_tmdb_list_id(list_id: str) -> str:
    """Normalize *list_id*: strip whitespace, extract from URL if needed.

    Args:
        list_id: The TMDb list ID.

    Returns:
        The normalized list ID.
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

        if not data.get("items"):
            break

        total_pages: int = data.get("total_pages", 1)
        if page >= total_pages or page >= _MAX_TMDB_PAGES:
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
        try:
            resp = network.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for i, rec in enumerate(data.get("results", [])):
                    rec_id = str(rec.get("id"))
                    score = 1.0 / (i + 1)  # Higher weight for top recommendations
                    recommendation_counts[rec_id] = (
                        recommendation_counts.get(rec_id, 0.0) + score
                    )
        except (requests.exceptions.RequestException, ValueError):
            logger.debug("Skipping failed recommendation item", exc_info=True)

    # Sort items by their accumulated score
    sorted_recs = sorted(
        recommendation_counts.items(),
        key=lambda x: x[1],
        reverse=True,
    )
    return [rec_id for rec_id, _ in sorted_recs]
