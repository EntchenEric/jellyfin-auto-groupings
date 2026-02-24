"""
tmdb.py – TMDb API list fetching utilities.

Provides a single public function for fetching TMDb IDs from a
TMDb v3 list.
"""

from __future__ import annotations

from typing import Any

import requests

_TMDB_API_BASE: str = "https://api.themoviedb.org/3"


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
        raise ValueError("A TMDb API Key is required to fetch TMDb lists.")
    if not list_id:
        raise ValueError("A TMDb List ID is required.")

    list_id = list_id.strip()
    
    # Handle full URL if provided (extracting ID from https://www.themoviedb.org/list/123)
    if "themoviedb.org/list/" in list_id:
        list_id = list_id.split("/list/")[1].split("?")[0].split("#")[0].strip("/").split("/")[0]


    ids: list[str] = []
    page: int = 1

    while True:
        url = f"{_TMDB_API_BASE}/list/{list_id}"
        params = {
            "api_key": api_key,
            "page": str(page),
            "language": "en-US"
        }
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch TMDb list page {page}: {exc}"
            ) from exc

        data: dict[str, Any] = resp.json()
        items: list[dict[str, Any]] = data.get("items", [])
        
        if not items:
            break

        for item in items:
            tmdb_id = item.get("id")
            if tmdb_id:
                ids.append(str(tmdb_id))

        total_pages: int = data.get("total_pages", 1)
        if page >= total_pages or page >= 50:  # Safety cap
            break
        page += 1

    return ids


def get_tmdb_recommendations(items_with_type: list[tuple[str, str]], api_key: str) -> list[str]:
    """Fetch recommendations for a list of TMDb IDs.

    Args:
        items_with_type: A list of tuples (tmdb_id, media_type) where media_type is "movie" or "tv".
        api_key: TMDb API Key (v3).

    Returns:
        A list of recommended TMDb IDs (as strings), sorted by recommendation frequency and rank.

    Raises:
        ValueError: If *api_key* is empty.
    """
    if not api_key:
        raise ValueError("A TMDb API Key is required to fetch TMDb recommendations.")

    recommendation_counts: dict[str, float] = {}

    for tmdb_id, media_type in items_with_type:
        url = f"{_TMDB_API_BASE}/{media_type}/{tmdb_id}/recommendations"
        params = {
            "api_key": api_key,
            "language": "en-US",
            "page": "1"
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for i, rec in enumerate(data.get("results", [])):
                    rec_id = str(rec.get("id"))
                    score = 1.0 / (i + 1)  # Higher weight for top recommendations
                    recommendation_counts[rec_id] = recommendation_counts.get(rec_id, 0.0) + score
        except Exception:
            pass  # Skip failures for individual items to keep aggregating

    # Sort items by their accumulated score
    sorted_recs = sorted(recommendation_counts.items(), key=lambda x: x[1], reverse=True)
    return [rec_id for rec_id, _ in sorted_recs]
