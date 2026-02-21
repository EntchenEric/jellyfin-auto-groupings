"""
imdb.py – IMDb list scraping utilities.

Provides a single public function for fetching ordered IMDb IDs from a
public IMDb list page via regex extraction over the rendered HTML.
"""

from __future__ import annotations

import re

import requests

# Maximum number of pages to scrape (safety guard, ~2 000 items at 100/page)
_MAX_PAGES: int = 20

_REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_imdb_list(list_id: str) -> list[str]:
    """Fetch an IMDb list and return its IMDb title IDs in list order.

    *list_id* may be a full URL (e.g. ``https://www.imdb.com/list/ls000024390/``)
    or a bare list ID (e.g. ``ls000024390``).  The function paginates
    automatically and deduplicates results while preserving order.

    Args:
        list_id: A full IMDb list URL or a bare ``ls\\d+`` list ID.

    Returns:
        An ordered list of IMDb title IDs (e.g. ``["tt0111161", ...]``).

    Raises:
        ValueError: If *list_id* cannot be parsed as a valid IMDb list ID.
        RuntimeError: If an HTTP error occurs while fetching a page.
    """
    list_id = list_id.strip()

    # Accept full URLs – extract just the ls-ID
    url_match = re.search(r"ls\d+", list_id)
    if url_match:
        list_id = url_match.group(0)

    if not list_id.startswith("ls"):
        raise ValueError(
            f"Invalid IMDb list ID: {list_id!r}. Expected format: ls000024390"
        )

    ids: list[str] = []
    page: int = 1

    while True:
        page_url = (
            f"https://www.imdb.com/list/{list_id}/"
            f"?sort=list_order,asc&st_dt=&mode=detail&page={page}"
        )
        try:
            resp = requests.get(page_url, headers=_REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch IMDb list page {page}: {exc}") from exc

        html: str = resp.text

        # Extract title IDs from canonical anchor hrefs: href="/title/tt1234567/"
        found: list[str] = re.findall(r'href="/title/(tt\d+)/', html)

        seen: set[str] = set(ids)
        for tt in found:
            if tt not in seen:
                ids.append(tt)
                seen.add(tt)

        # Stop when there is no pagination link pointing to the next page
        has_next = re.search(r'class="[^"]*next-page[^"]*"', html) or re.search(
            r'rel="next"', html
        )
        if not has_next or page >= _MAX_PAGES:
            break

        page += 1

    return ids
