"""imdb.py - IMDb list scraping utilities.

Provides a single public function for fetching ordered IMDb IDs from a
public IMDb list page via regex extraction over the rendered HTML.
"""

from __future__ import annotations

import logging
import re

import requests

import network
from _common import DEFAULT_LIST_FETCH_TIMEOUT as _REQUEST_TIMEOUT
from _common import DEFAULT_LIST_MAX_PAGES
from _common import DEFAULT_SCRAPING_HEADERS as _REQUEST_HEADERS

__all__ = ["fetch_imdb_list"]

logger = logging.getLogger(__name__)

# Maximum number of pages to scrape (safety guard, ~5 000 items at 100/page).
# Shared with the other list fetchers so every source truncates at the same
# point, and so the README's "safety cap (50 pages)" is actually true here.
_MAX_PAGES: int = DEFAULT_LIST_MAX_PAGES

# IMDb list IDs are the literal ``ls`` prefix followed by digits. Anything
# else (``ls``, ``lsabc``) would be pasted straight into the request URL and
# fetched only to come back as an empty or error page.
_LIST_ID_PATTERN: re.Pattern[str] = re.compile(r"^ls\d+$")


def fetch_imdb_list(list_id: str) -> list[str]:
    r"""Fetch an IMDb list and return its IMDb title IDs in list order.

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

    # Accept full URLs - extract just the ls-ID
    url_match = re.search(r"ls\d+", list_id)
    if url_match:
        list_id = url_match.group(0)

    if not _LIST_ID_PATTERN.match(list_id):
        msg = f"Invalid IMDb list ID: {list_id!r}. Expected format: ls000024390"
        raise ValueError(msg)

    ids: list[str] = []
    seen: set[str] = set()
    page: int = 1

    while True:
        page_url = (
            f"https://www.imdb.com/list/{list_id}/"
            f"?sort=list_order,asc&st_dt=&mode=detail&page={page}"
        )
        try:
            resp = network.get(
                page_url,
                headers=_REQUEST_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.exception("HTTP error fetching IMDb list page %d", page)
            msg = f"Failed to fetch IMDb list page {page}: {exc}"
            raise RuntimeError(msg) from exc

        html: str = resp.text

        # Extract title IDs from canonical anchor hrefs: href="/title/tt1234567/"
        found: list[str] = re.findall(r'href="/title/(tt\d+)/', html)

        for tt in found:
            if tt not in seen:
                ids.append(tt)
                seen.add(tt)

        # Stop when there is no pagination link pointing to the next page
        has_next = re.search(r'class="[^"]*next-page[^"]*"', html) or re.search(
            r'rel="next"',
            html,
        )
        if not has_next:
            break
        if page >= _MAX_PAGES:
            # Stopping silently would look like "the list ends here", so the
            # user gets a truncated collection with no hint that more exists.
            logger.warning(
                "Stopping after %d pages (the safety limit) — the IMDb list "
                "%s has more entries than were fetched",
                _MAX_PAGES,
                list_id,
            )
            break

        page += 1

    return ids
