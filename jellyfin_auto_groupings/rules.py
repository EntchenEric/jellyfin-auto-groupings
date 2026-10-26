import logging
import re
from typing import Any

from utils.helpers import string_list, studio_names

logger = logging.getLogger(__name__)

FRANCHISE_RULES = {
    "Marvel Cinematic Universe": [
        r"\bmcu\b",
        r"marvel cinematic universe",
        r"avengers",
        r"iron man",
        r"thor",
        r"captain america",
    ],
    "Star Wars": [r"star wars", r"\bsw\b"],
    "Harry Potter": [r"harry potter", r"wizarding world", r"fantastic beasts"],
    "Lord of the Rings": [r"lord of the rings", r"\blotr\b", r"the hobbit"],
    "James Bond": [r"james bond", r"007"],
}

GENRE_KEYWORDS = {
    "Sci-Fi Classics": [
        r"sci-fi",
        r"science fiction",
        r"space",
        r"alien",
        r"cyberpunk",
    ],
    "Oscar Winners": [r"oscar", r"academy award", r"best picture"],
    "90s Action": [r"action"],
}


def create_groupings(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group items by the built-in franchise, genre, and decade rules.

    Franchise and genre matches come from :data:`FRANCHISE_RULES` and
    :data:`GENRE_KEYWORDS` and are searched case-insensitively in the title and
    overview. Decade groups are appended afterwards, so an item can appear in
    both a keyword group and its decade group.

    Args:
        items: Item dictionaries; missing ``Name`` or ``Overview`` values are
            treated as empty strings.

    Returns:
        Mapping of group name to the items in it. Empty input yields ``{}``.
    """
    if not items:
        return {}

    groupings: dict[str, list[dict[str, Any]]] = {}

    for item in items:
        title = item.get("Name", "")
        overview = item.get("Overview", "")
        text_to_check = f"{title} {overview}".lower()

        for franchise_name, patterns in FRANCHISE_RULES.items():
            for pattern in patterns:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    groupings.setdefault(franchise_name, []).append(item)
                    break

        for genre_name, patterns in GENRE_KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    groupings.setdefault(genre_name, []).append(item)
                    break

    decade_groups = group_by_decade(items)
    for dec, dec_items in decade_groups.items():
        if dec_items:
            groupings.setdefault(dec, []).extend(dec_items)

    return groupings


def group_by_tag(
    items: list[dict[str, Any]], min_items: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Group items by tag, keeping groups with at least ``min_items`` members."""
    tag_groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        # Jellyfin uses ``null`` for empty tag lists and may include
        # non-string values; skip those rather than raising. A bare string is
        # one tag, not an iterable of characters.
        for tag in string_list(item.get("Tags")):
            if tag:
                tag_groups.setdefault(tag, []).append(item)
    return {k: v for k, v in tag_groups.items() if len(v) >= min_items}


def group_by_genre(
    items: list[dict[str, Any]], min_items: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Group items by genre, keeping groups with at least ``min_items`` members."""
    genre_groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for genre in string_list(item.get("Genres")):
            if genre:
                genre_groups.setdefault(genre, []).append(item)
    return {k: v for k, v in genre_groups.items() if len(v) >= min_items}


def group_by_studio(
    items: list[dict[str, Any]], min_items: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Group items by studio name, keeping groups with at least ``min_items``.

    Jellyfin returns studios as ``{"Name": ...}`` dictionaries, but plain
    strings and ``null`` also occur, so both shapes are accepted and anything
    else is skipped.
    """
    studio_groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for name in studio_names(item.get("Studios")):
            studio_groups.setdefault(name, []).append(item)
    return {k: v for k, v in studio_groups.items() if len(v) >= min_items}


def process_groupings(client: Any, rules: dict[str, Any]) -> dict[str, Any]:
    """Process automated groupings based on client and rules."""
    if not rules:
        return {}
    return {}


def parse_grouping_rules(rules: dict[str, Any]) -> dict[str, Any]:
    """Return the ``collections`` section of a rules dict, or ``{}``.

    Non-dict input, a missing ``collections`` key, and a non-dict
    ``collections`` value all fall back to an empty mapping.
    """
    if not isinstance(rules, dict):
        return {}
    collections = rules.get("collections", {})
    if not isinstance(collections, dict):
        return {}
    return collections


def group_by_decade(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group items by release decade, keyed like ``"1990s Movies"``.

    The year comes from ``ProductionYear`` when it is a usable int or numeric
    string, otherwise from the leading four digits of ``PremiereDate``.
    ``bool`` values and years outside 1800-2100 are ignored.
    """
    collections: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        year = None
        prod_year = item.get("ProductionYear")
        if (
            isinstance(prod_year, int)
            and not isinstance(prod_year, bool)
            and prod_year > 0
        ):
            year = prod_year
        elif isinstance(prod_year, str) and prod_year.strip().isdigit():
            year = int(prod_year.strip())

        if year is None and item.get("PremiereDate"):
            pdate = item.get("PremiereDate")
            if isinstance(pdate, str) and len(pdate) >= 4 and pdate[:4].isdigit():
                year = int(pdate[:4])
            elif isinstance(pdate, (int, float)) and not isinstance(pdate, bool):
                year = int(pdate)

        if year and 1800 <= year <= 2100:
            decade = f"{(year // 10) * 10}s Movies"
            if decade not in collections:
                collections[decade] = []
            collections[decade].append(item)

    return collections
