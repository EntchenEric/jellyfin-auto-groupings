"""
jellyfin.py – Jellyfin API client helpers.

Contains the sort-order mapping used across the application and a thin
convenience wrapper around ``requests.get`` for fetching items from the
Jellyfin ``/Items`` endpoint.
"""

from __future__ import annotations

from typing import Any

import requests

# ---------------------------------------------------------------------------
# Sort-order mapping
# ---------------------------------------------------------------------------

# Maps internal ``sort_order`` keys to the Jellyfin API ``SortBy`` /
# ``SortOrder`` query parameter pairs.
#
# ``"imdb_list_order"``, ``"trakt_list_order"``, and ``""`` are handled
# separately by the sync logic and do **not** appear in this map.
SORT_MAP: dict[str, tuple[str, str]] = {
    "CommunityRating": ("CommunityRating", "Descending"),
    "ProductionYear": ("ProductionYear,SortName", "Descending,Ascending"),
    "SortName": ("SortName", "Ascending"),
    "DateCreated": ("DateCreated", "Descending"),
    "Random": ("Random", "Ascending"),
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def fetch_jellyfin_items(
    base_url: str,
    api_key: str,
    extra_params: dict[str, str] | None = None,
    *,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Fetch the ``Items`` list from the Jellyfin ``/Items`` endpoint.

    Builds query parameters, performs a GET request, and returns the parsed
    ``Items`` list from the JSON response.

    Args:
        base_url: Jellyfin server base URL (no trailing slash), e.g.
            ``"http://localhost:8096"``.
        api_key: Jellyfin API key.
        extra_params: Additional query-string parameters to merge into the
            request (e.g. ``{"IncludeItemTypes": "Movie,Series"}``).
        timeout: HTTP request timeout in seconds.

    Returns:
        The ``Items`` list from the Jellyfin response, or an empty list if
        the response contained no ``Items`` key.

    Raises:
        requests.HTTPError: If the server returns a non-2xx status code.
        requests.RequestException: For any other network-level error.
    """
    params: dict[str, str] = {"api_key": api_key}
    if extra_params:
        params.update(extra_params)

    response = requests.get(f"{base_url}/Items", params=params, timeout=timeout)
    response.raise_for_status()
    return response.json().get("Items", [])
