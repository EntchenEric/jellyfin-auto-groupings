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
        List of chunks.  An empty input yields no chunks at all, whatever the
        chunk size — ``chunk_list([], 0)`` used to return ``[[]]``, a single
        empty chunk that made callers treat "nothing to do" as one work item.
    """
    if not lst:
        return []
    if size <= 0:
        return [lst]

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
        filename: The filename to sanitize. Non-string values are treated as
            unusable rather than raising ``AttributeError`` from ``.strip()``.

    Returns:
        A single path segment safe for use as a file name, or ``"unnamed"``
        when nothing usable remains. NUL and other control characters are
        replaced with ``_``: a NUL byte makes every filesystem call raise
        ``ValueError: embedded null byte``.
    """
    if not isinstance(filename, str) or not filename.strip():
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

    # A NUL byte cannot exist in a path: ``open()`` and every other
    # filesystem call raise ``ValueError: embedded null byte``, which the
    # sync layer does not expect from a name it already "sanitised". Other
    # C0 control characters are legal on Linux but produce names that are
    # invisible or unmanageable in a file manager, so both are replaced.
    name = re.sub(r"[\x00-\x1f\x7f]", "_", name)

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


def parse_media_tags(tags: Any) -> list[str]:
    """Parse and normalize media tags.

    Strips whitespace, removes duplicates (case-insensitive), and filters empty tags.

    Jellyfin sends ``null`` for empty tag lists and may include non-string
    entries, so anything that is not a string is skipped instead of raising
    the :class:`AttributeError` that ``.strip()`` on ``None`` would produce.
    A bare string is treated as a single tag rather than an iterable of
    characters (see :func:`string_list`).
    The same rule is applied by :func:`jellyfin_auto_groupings.rules.group_by_tag`.

    Args:
        tags: List of tag values, a single tag string, or ``None``;
            non-string entries are ignored.

    Returns:
        Unique normalized tags in first-seen order. Deduplication keeps the
        first spelling encountered, so the result is not sorted.
    """
    seen = set()
    result = []

    for tag in string_list(tags):
        stripped = tag.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower not in seen:
            seen.add(lower)
            result.append(stripped)

    return result


def string_list(value: Any) -> list[str]:
    """Return the strings in *value* as a list.

    Jellyfin usually serialises ``Tags``, ``Genres``, and ``Studios`` as
    arrays, but a hand-edited ``config.json``, a proxy, or an older server
    can put a bare string there. Iterating that string yields one character
    at a time, so ``"action"`` became six groups named ``a``, ``c``, ``t``,
    ``i``, ``o``, ``n``. A single string is therefore treated as one value,
    and ``null`` or any other shape yields no values at all.

    Args:
        value: A list/tuple/set of strings, a single string, or anything else.

    Returns:
        The contained strings, non-string entries removed. A bare string is
        returned as a one-element list; unusable input yields ``[]``.
    """
    if isinstance(value, str):
        return [value]
    if not isinstance(value, (list, tuple, set, frozenset)):
        return []
    return [entry for entry in value if isinstance(entry, str)]


def studio_names(value: Any) -> list[str]:
    """Return the studio names in a Jellyfin ``Studios`` field.

    Jellyfin serialises studios as an array of ``{"Name": ...}`` objects, but
    a bare string or a single object also occurs in hand-edited or older
    payloads. Iterating a bare string yields one character at a time, so a
    studio rule could never match and a grouping pass produced one group per
    letter. Anything that is not a studio object or a string is skipped.

    Args:
        value: The raw ``Studios`` field: a list of objects/strings, a single
            object, a bare string, or anything else.

    Returns:
        The non-empty studio names as strings; empty when there are none.
    """
    if isinstance(value, (str, dict)):
        value = [value]
    elif not isinstance(value, (list, tuple, set, frozenset)):
        return []

    names: list[str] = []
    for studio in value:
        name = studio.get("Name") if isinstance(studio, dict) else studio
        if isinstance(name, str) and name:
            names.append(name)
    return names


def normalize_title(title: str | None, remove_articles: bool = True) -> str:
    """Normalize a title by lowercasing and optionally removing leading articles.

    Args:
        title: The title to normalize (or None). Non-string values are treated
            as missing rather than raising ``TypeError`` out of ``re.sub``.
        remove_articles: Whether to remove leading articles like "The", "A", "An".

    Returns:
        Normalized title string in lowercase, or ``""`` when *title* is not
        usable text.
    """
    if not isinstance(title, str) or not title:
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


#: Range accepted as a release year. Mirrors the range that
#: :func:`jellyfin_auto_groupings.rules.group_by_decade` uses, so a title that
#: yields a year here also lands in a decade group instead of being dropped.
_YEAR_MIN = 1800
_YEAR_MAX = 2100

#: Trailing punctuation left behind once a year is split off the title.
_TITLE_TRAILING_JUNK = " \t:;,-_.(["

#: A year wrapped in brackets or parentheses at the end of a title.
_TRAILING_BRACKETED_YEAR = re.compile(r"[\[(]\s*(\d{4})\s*[)\]]$")

#: A bare four-digit year at the end, provided the digit before it does not
#: belong to a longer number (``"Movie 12345"`` must not yield 2345).
_TRAILING_BARE_YEAR = re.compile(r"(?<!\d)(\d{4})$")


def _plausible_year(text: str) -> int | None:
    """Return *text* as a release year, or ``None`` when it is out of range."""
    year = int(text)
    if _YEAR_MIN <= year <= _YEAR_MAX:
        return year
    return None


def extract_year_from_title(title: str | None) -> tuple[str, int | None]:
    """Extract a release year from the end of a title string.

    Recognises ``"Movie (2023)"``, ``"Movie [2023]"``, ``"Movie[2023]"``, and
    ``"Movie 2023"``. The year must stand on its own: ``"Movie 12345"`` keeps
    its 5-digit number instead of being split into ``"Movie 1"`` + ``2345``,
    which used to produce a bogus year and a mangled title. Only years within
    1800-2100 are returned, so a stray number is left in the title.

    Surrounding whitespace is trimmed before matching and the returned title
    is stripped as well: the patterns are anchored at the end of the value, so
    a padded ``"  Movie (2023)  "`` previously matched nothing and came back
    with its spaces intact.

    Args:
        title: The title string (or None). Non-string values are treated as
            missing rather than raising ``TypeError`` out of ``re.search``.

    Returns:
        A tuple of (title_without_year, extracted_year_or_None). A non-string
        or blank *title* yields ``("", None)``.
    """
    if not isinstance(title, str):
        return ("", None)

    stripped = title.strip()
    if not stripped:
        return ("", None)

    match = _TRAILING_BRACKETED_YEAR.search(stripped)
    if match:
        year = _plausible_year(match.group(1))
        if year is not None:
            before = stripped[: match.start()].rstrip(_TITLE_TRAILING_JUNK)
            return (before, year)

    match = _TRAILING_BARE_YEAR.search(stripped)
    if match:
        year = _plausible_year(match.group(1))
        if year is not None:
            before = stripped[: match.start()].rstrip(_TITLE_TRAILING_JUNK)
            # A bare year is only split off when something precedes it. A
            # title that is itself a year (the film "1917") must keep its
            # text instead of becoming an empty name with a bogus year.
            if before:
                return (before, year)

    return (stripped, None)


def group_by_key(items: list[dict], key: str) -> dict:
    """Group a list of dictionaries by a given key.

    Args:
        items: List of dictionaries to group.
        key: The dictionary key to group by.

    Returns:
        Dictionary mapping key values to lists of items.  Items whose value is
        missing or cannot be a dictionary key are skipped: a Jellyfin field
        such as ``Genres`` holds a list, and using it as a key raised
        ``TypeError: unhashable type: 'list'`` instead of leaving that item
        out of the grouping.
    """
    result: dict[Any, list[dict]] = {}

    for item in items:
        value = item.get(key)
        if value is None:
            continue
        try:
            hash(value)
        except TypeError:
            continue
        result.setdefault(value, []).append(item)

    return result
