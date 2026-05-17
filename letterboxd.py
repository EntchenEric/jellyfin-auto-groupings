"""
letterboxd.py – Letterboxd list scraping utilities.

Provides a single public function for fetching ordered IMDb or TMDb IDs from a
Letterboxd list by parsing the HTML.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

_MAX_PAGES: int = 10
_MAX_WORKERS: int = 6

_REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://letterboxd.com/",
}


def _extract_ids_from_list_page(html: str) -> dict[str, str]:
    """Extract IMDb/TMDb IDs embedded in list-page HTML.

    Returns a mapping of ``slug -> id`` for films where an ID was found
    directly on the list page, avoiding a per-film page fetch.
    """
    found: dict[str, str] = {}

    for match in re.finditer(
        r'data-film-slug="([^"]+)".*?data-tmdb-id="(\d+)"', html, re.DOTALL
    ):
        found[match.group(1)] = match.group(2)

    for match in re.finditer(
        r'data-film-slug="([^"]+)".*?imdb\.com/title/(tt\d+)', html, re.DOTALL
    ):
        slug = match.group(1)
        if slug not in found:
            found[slug] = match.group(2)

    for match in re.finditer(
        r'data-film-slug="([^"]+)".*?themoviedb\.org/movie/(\d+)', html, re.DOTALL
    ):
        slug = match.group(1)
        if slug not in found:
            found[slug] = match.group(2)

    return found


def _fetch_id_for_slug(slug: str) -> str | None:
    """Fetch the IMDb or TMDb ID from a film's detail page.

    Args:
        slug: The Letterboxd film slug (e.g., ``"the-godfather"``).

    Returns:
        The extracted ID as a string, or ``None`` if no ID was found.
    """
    film_url = f"https://letterboxd.com/film/{slug}/"
    try:
        resp = requests.get(film_url, headers=_REQUEST_HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text

        imdb_match = re.search(r'href="[^"]*imdb\.com/title/(tt\d+)', html)
        if imdb_match:
            return imdb_match.group(1)

        tmdb_match = re.search(r'href="[^"]*themoviedb\.org/movie/(\d+)', html)
        if tmdb_match:
            return tmdb_match.group(1)

        tmdb_attr = re.search(r'data-tmdb-id="(\d+)"', html)
        if tmdb_attr:
            return tmdb_attr.group(1)

    except requests.RequestException:
        logger.warning("Failed to fetch Letterboxd film page for '%s'", slug, exc_info=True)
        return None

    return None


def fetch_letterboxd_list(list_url: str) -> list[str]:
    """Fetch a Letterboxd list and return its IMDb or TMDb IDs in list order.

    Extracts IDs embedded in list-page HTML where possible; remaining slugs
    are resolved via parallel film-page requests.

    Args:
        list_url: Full Letterboxd list URL.

    Returns:
        An ordered list of IDs (IMDb ``tt...`` or TMDb numeric strings).

    Raises:
        ValueError: If *list_url* is invalid.
        RuntimeError: If an HTTP error occurs while fetching a list page.
    """
    list_url = list_url.rstrip("/")
    if "letterboxd.com" not in list_url:
        raise ValueError(f"Invalid Letterboxd URL: {list_url!r}")

    ids: list[str] = []
    seen_ids: set[str] = set()
    page = 1

    while True:
        current_url = f"{list_url}/page/{page}/" if page > 1 else f"{list_url}/"

        try:
            resp = requests.get(current_url, headers=_REQUEST_HEADERS, timeout=15)
            if resp.status_code == 404 and page > 1:
                break
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to fetch Letterboxd list page {page}: {exc}") from exc

        html = resp.text

        ids_from_list = _extract_ids_from_list_page(html)

        slugs = re.findall(r'data-film-slug="([^"]+)"', html)
        if not slugs:
            slugs = re.findall(r'href="/film/([^/"]+)/"', html)

        unique_slugs: list[str] = []
        for slug in slugs:
            if slug not in unique_slugs:
                unique_slugs.append(slug)

        if not unique_slugs:
            logger.warning("No film slugs found on Letterboxd page %d", page)
            break

        slugs_to_fetch = [s for s in unique_slugs if s not in ids_from_list]
        logger.info(
            "Letterboxd page %d: %d slugs (%d from list, %d to fetch)",
            page, len(unique_slugs), len(ids_from_list), len(slugs_to_fetch),
        )

        slug_results: dict[str, str | None] = {}
        if slugs_to_fetch:
            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
                future_map = {
                    executor.submit(_fetch_id_for_slug, slug): slug
                    for slug in slugs_to_fetch
                }
                for future in as_completed(future_map):
                    slug = future_map[future]
                    try:
                        slug_results[slug] = future.result()
                    except Exception:
                        logger.debug("Unexpected error for '%s'", slug, exc_info=True)
                        slug_results[slug] = None

        for slug in unique_slugs:
            film_id = ids_from_list.get(slug) or slug_results.get(slug)
            if film_id and film_id not in seen_ids:
                ids.append(film_id)
                seen_ids.add(film_id)

        if 'class="next"' not in html or page >= _MAX_PAGES:
            break

        page += 1
        time.sleep(0.5)

    return ids
