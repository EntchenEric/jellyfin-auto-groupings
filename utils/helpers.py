"""Helper utilities for Jellyfin Groupings."""

import re
from typing import Any

_UUID_WITH_DASHES = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_UUID_WITHOUT_DASHES = re.compile(r"^[0-9a-fA-F]{32}$")


def safe_get(data: dict | None, key: str, default=None):
    """Get a value from a nested dict/list using a dot-separated key path.

    Args:
        data: The dictionary/list to search (or None).
        key: Dot-separated key path (e.g. "a.b.c" or "a.items.1").
        default: Default value if key not found.

    Returns:
        The nested value or default.
    """
    if data is None:
        return default
    if not key:
        return data

    keys = key.split(".")
    current = data
    for k in keys:
        if isinstance(current, dict):
            if k in current:
                current = current[k]
            else:
                return default
        elif isinstance(current, list):
            # Try to interpret k as an integer index
            try:
                idx = int(k)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return default
            except ValueError:
                return default
        else:
            return default
    return current


def items_from_body(body: Any) -> list[dict]:
    """Return the item dictionaries in a Jellyfin response body.

    Jellyfin reports an empty result set as ``"Items": null`` rather than an
    absent key or an empty array, so ``body.get("Items", [])`` returns
    ``None`` and the caller fails later on ``len()`` or iteration.  A proxy
    or an error page served with status 200 can also put a string or an
    object where the array belongs, and a partial response can contain
    ``null`` placeholders, which make each ``item.get(...)`` raise
    ``AttributeError``.

    Args:
        body: The parsed JSON body, expected to be an object.

    Returns:
        The usable item dictionaries, or ``[]`` when there are none.
    """
    if not isinstance(body, dict):
        return []
    items = body.get("Items")
    if not isinstance(items, list):
        return []
    return [entry for entry in items if isinstance(entry, dict)]


def chunk_list(lst: list, size: int) -> list:
    """Split a list into chunks of a given size.

    Args:
        lst: The list to split.
        size: Size of each chunk.

    Returns:
        List of chunks.
    """
    if size <= 0:
        return [lst]
    if not lst:
        return []

    return [lst[i : i + size] for i in range(0, len(lst), size)]


def deep_merge(dict1: dict, dict2: dict) -> dict:
    """Deep merge two dictionaries.

    Values from dict2 override dict1 for non-dict values.
    Dict values are merged recursively.

    Args:
        dict1: The base dictionary.
        dict2: The dictionary whose values take precedence.

    Returns:
        A new merged dictionary (originals unchanged).
    """
    result = dict(dict1)

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def flatten_dict(nested: dict, sep: str = ".") -> dict:
    """Flatten a nested dictionary into a single-level dictionary.

    Args:
        nested: The nested dictionary to flatten.
        sep: Separator for nested keys.

    Returns:
        A flattened dictionary with keys as path strings.
    """
    result = {}

    def _flatten(current: dict, prefix: str = ""):
        for key, value in current.items():
            new_key = f"{prefix}{sep}{key}" if prefix else key
            if isinstance(value, dict):
                _flatten(value, new_key)
            else:
                result[new_key] = value

    _flatten(nested)
    return result


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by replacing characters that are unsafe on disk.

    Leading ``./`` is dropped, while each leading ``../`` is rewritten as
    ``.._`` so a traversal attempt stays visible in the result instead of
    silently collapsing into a plain name.

    Args:
        filename: The filename to sanitize.

    Returns:
        A single path segment safe for use as a file name, or ``"unnamed"``
        when nothing usable remains.
    """
    if not filename or not filename.strip():
        return "unnamed"

    name = filename.strip()

    traversal = re.match(r"^(?:\.\./)+", name)
    if traversal:
        steps = traversal.group(0).count("../")
        name = (".._" * steps) + name[traversal.end() :]
    else:
        name = re.sub(r"^\./+", "", name)

    # Replace path separators and characters rejected by common filesystems.
    for char in '<>:"/\\|?*':
        name = name.replace(char, "_")

    # Collapse whitespace so the result stays a single path segment.
    name = re.sub(r"\s+", " ", name).strip()

    if not name or re.fullmatch(r"\.+", name):
        return "unnamed"
    if not re.search(r"[a-zA-Z0-9]", name):
        return "unnamed"

    return name


def is_valid_uuid(uuid_str: str | None) -> bool:
    """Check if a string is a valid UUID.

    Args:
        uuid_str: The string to check.

    Returns:
        True if the string is a valid UUID format, False otherwise.
    """
    if uuid_str is None or not isinstance(uuid_str, str):
        return False

    # With dashes: 8-4-4-4-12 hex digits. Without dashes: 32 hex digits.
    return bool(
        _UUID_WITH_DASHES.match(uuid_str) or _UUID_WITHOUT_DASHES.match(uuid_str)
    )


def parse_media_tags(tags: list[Any]) -> list[str]:
    """Parse and normalize media tags.

    Strips whitespace, removes duplicates (case-insensitive), and filters empty tags.

    Jellyfin sends ``null`` for empty tag lists and may include non-string
    entries, so anything that is not a string is skipped instead of raising
    the :class:`AttributeError` that ``.strip()`` on ``None`` would produce.
    The same rule is applied by :func:`jellyfin_auto_groupings.rules.group_by_tag`.

    Args:
        tags: List of tag values; non-string entries are ignored.

    Returns:
        Unique normalized tags in first-seen order. Deduplication keeps the
        first spelling encountered, so the result is not sorted.
    """
    seen = set()
    result = []

    for tag in tags:
        if not isinstance(tag, str):
            continue
        stripped = tag.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower not in seen:
            seen.add(lower)
            result.append(stripped)

    return result


def normalize_title(title: str | None, remove_articles: bool = True) -> str:
    """Normalize a title by lowercasing and optionally removing leading articles.

    Args:
        title: The title to normalize (or None).
        remove_articles: Whether to remove leading articles like "The", "A", "An".

    Returns:
        Normalized title string in lowercase.
    """
    if title is None or title == "":
        return ""

    # Replace punctuation characters with spaces or remove
    # Test expects: "Iron Man 2: Extended Edition" -> "iron man 2 extended edition"
    cleaned = re.sub(r"[:!?,;.\[\](){}\"'_\-]+([\s]|$)", " ", title)
    cleaned = re.sub(r"[:!?,;.\[\](){}\"'_\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()

    if remove_articles:
        # Split on spaces and remove leading articles (including foreign like der, die, das, le, la, el, un, etc. if needed)
        parts = cleaned.split()
        articles = {
            "the",
            "a",
            "an",
            "der",
            "die",
            "das",
            "le",
            "la",
            "les",
            "un",
            "une",
            "el",
            "los",
            "las",
        }
        while parts and parts[0] in articles:
            parts.pop(0)
        return " ".join(parts)

    return cleaned


def extract_year_from_title(title: str | None) -> tuple[str, int | None]:
    """Extract a year from a title string.

    Looks for year in parentheses [YYYY] or (YYYY) at the end of the title.

    Args:
        title: The title string (or None).

    Returns:
        A tuple of (title_without_year, extracted_year_or_None).
    """
    if title is None or title == "":
        return ("", None)

    # Try to find year in parentheses/brackets at end: ... (2023) or ... [2023]
    # Updated pattern to also match [YYYY]
    match = re.search(r"[\s(][\[\]]?(\d{4})[)\]]$", title)
    if match:
        year = int(match.group(1))
        # Remove the year portion from the title
        before = title[: match.start()].rstrip()
        # Clean up trailing colons, spaces, and brackets
        before = before.rstrip(" :[]")
        return (before, year)

    # Try year without brackets at very end: "Movie 2023"
    match = re.search(r"(\d{4})$", title)
    if match:
        year = int(match.group(1))
        # Check if the year is preceded by a space (not embedded in other text)
        before = title[: match.start()].rstrip()
        return (before, year)

    return (title, None)


def group_by_key(items: list[dict], key: str) -> dict:
    """Group a list of dictionaries by a given key.

    Args:
        items: List of dictionaries to group.
        key: The dictionary key to group by.

    Returns:
        Dictionary mapping key values to lists of items.
    """
    result: dict[Any, list[dict]] = {}

    for item in items:
        value = item.get(key)
        if value is not None:
            if value not in result:
                result[value] = []
            result[value].append(item)

    return result
