"""
letterboxd.py – Letterboxd list scraping utilities.

Provides a single public function for fetching ordered IMDb or TMDb IDs from a
Letterboxd list by parsing the HTML.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

# Maximum pages to scrape (safety guard, 100 items per page)
_MAX_PAGES: int = 10

_REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://letterboxd.com/",
}


def fetch_letterboxd_list(list_url: str) -> list[str]:
    """Fetch a Letterboxd list and return its IMDb or TMDb IDs in list order.

    *list_url* should be a full Letterboxd list URL.
    The function paginates automatically and extracts IDs from the HTML.

    Args:
        list_url: Full Letterboxd list URL.

    Returns:
        An ordered list of IDs (IMDb 'tt...' or TMDb numeric strings).

    Raises:
        ValueError: If *list_url* is invalid.
        RuntimeError: If an HTTP error occurs while fetching.
    """
    list_url = list_url.rstrip("/")
    if "letterboxd.com" not in list_url:
        raise ValueError(f"Invalid Letterboxd URL: {list_url!r}")

    ids: list[str] = []
    session = requests.Session()
    session.headers.update(_REQUEST_HEADERS)

    page = 1
    seen_ids: set[str] = set()

    while True:
        # Letterboxd pagination: /page/2/
        current_url = f"{list_url}/page/{page}/" if page > 1 else f"{list_url}/"
        
        try:
            resp = session.get(current_url, timeout=15)
            # If we get a 404 on a page > 1, it means we've reached the end
            if resp.status_code == 404 and page > 1:
                break
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch Letterboxd list page {page}: {exc}") from exc

        html = resp.text
        
        # Look for the film posters which contain data-film-slug or are wrapped in links
        # We can also look for data-film-id or data-target-link
        # A more robust way is to find the slugs and then we might need to fetch the film page 
        # BUT many enthusiasts have found that Letterboxd often includes TMDB IDs in the HTML
        # specifically in data attributes of the poster div or in the json-ld.
        
        # Method 1: Extraction of slugs
        slugs = re.findall(r'data-film-slug="([^"]+)"', html)
        
        # If no slugs found with data-film-slug, try standard links
        if not slugs:
            slugs = re.findall(r'href="/film/([^/"]+)/"', html)

        # Deduplicate slugs while preserving order
        unique_slugs_in_page = []
        for slug in slugs:
            if slug not in unique_slugs_in_page:
                unique_slugs_in_page.append(slug)

        if not unique_slugs_in_page:
            print("No slugs found on page.")
            break

        print(f"Found {len(unique_slugs_in_page)} slugs on page {page}. Fetching IDs...")
        for slug in unique_slugs_in_page:
            print(f"  Fetching ID for: {slug}")
            film_id = _fetch_id_for_slug(session, slug)
            if film_id:
                print(f"    Found ID: {film_id}")
                if film_id not in seen_ids:
                    ids.append(film_id)
                    seen_ids.add(film_id)
            else:
                print(f"    No ID found for: {slug}")

        # Check for next page
        if 'class="next"' not in html or page >= _MAX_PAGES:
            break
            
        page += 1
        # Small delay to be respectful
        time.sleep(0.5)

    return ids


def _fetch_id_for_slug(session: requests.Session, slug: str) -> str | None:
    """Fetch the IMDb or TMDb ID for a specific film slug.

    Performs a GET request to the film's Letterboxd page and extracts either
    the IMDb ID (tt...) or TMDb ID from the HTML content.

    Args:
        session: The active requests.Session to use for the request.
        slug: The Letterboxd film slug (e.g., "the-godfather").

    Returns:
        The extracted ID as a string, or None if no ID could be found or an
        error occurred.
    """
    film_url = f"https://letterboxd.com/film/{slug}/"
    try:
        resp = session.get(film_url, timeout=10)
        resp.raise_for_status()
        html = resp.text
        
        # Try to find IMDb ID
        imdb_match = re.search(r'href="[^"]*imdb\.com/title/(tt\d+)', html)
        if imdb_match:
            return imdb_match.group(1)
            
        # Try to find TMDb ID
        tmdb_match = re.search(r'href="[^"]*themoviedb\.org/movie/(\d+)', html)
        if tmdb_match:
            return tmdb_match.group(1)

        # Alternative: check for data-tmdb-id or similar
        tmdb_attr = re.search(r'data-tmdb-id="(\d+)"', html)
        if tmdb_attr:
            return tmdb_attr.group(1)

    except Exception:
        return None
    
    return None
