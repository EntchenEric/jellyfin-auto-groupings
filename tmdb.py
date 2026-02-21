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
