"""Formatting utilities for Jellyfin Groupings."""

import math
import re
import unicodedata
from typing import Any


def _coerce_finite_number(value: Any) -> float | None:
    """Coerce *value* to a finite float, or ``None`` when it is not usable.

    Jellyfin does not guarantee a numeric type or a finite value for fields
    that are conceptually numbers: ``RunTimeTicks``-derived durations arrive
    as strings from some clients, and a corrupt or partially scanned item can
    report ``NaN`` or ``Infinity``. Passing those straight into the format
    helpers produced output like ``"1.0m 30.599999999999994s"`` or
    ``"nan B"``, so every helper normalises its input first.

    Args:
        value: The raw value to coerce.

    Returns:
        The value as a finite ``float``, or ``None`` if it cannot be used.
        ``bool`` is rejected because ``True`` is not a duration or a size.

    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _coerce_text(value: Any) -> str | None:
    """Coerce *value* to a string, or ``None`` when it is not text.

    Item fields are typed loosely in Jellyfin payloads and in stored config, so
    a helper that declares ``str`` can still receive an ``int``, a ``list``, or
    an object. Calling ``.strip()`` or ``re.match`` on those raised
    ``AttributeError``/``TypeError`` from deep inside a formatting call, which
    surfaced as a 500 instead of a blank cell.

    Only real strings are accepted; a number is *not* valid text here, because
    silently rendering a corrupt ``ProductionYear`` of ``20240101`` as a
    date-looking string would hide the bad value rather than drop it.

    Args:
        value: The raw value to coerce.

    Returns:
        The value when it is a ``str``, otherwise ``None``.

    """
    if not isinstance(value, str):
        return None
    return value


def _coerce_dimension(value: Any) -> int | None:
    """Coerce *value* to a positive pixel dimension, or ``None``.

    Width and height reach these helpers as ``int`` in normal payloads, but a
    string from a hand-edited config or a partially scanned item must not be
    rendered as ``"1920x1080.0"``. ``bool`` is rejected because ``True`` is not
    a width — ``format_resolution(True, 1080)`` previously returned
    ``"Truex1080"``.

    Args:
        value: The raw dimension to coerce.

    Returns:
        The dimension as a positive ``int``, or ``None`` if it cannot be used.

    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if not math.isfinite(value) or value <= 0 or not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text.isdigit():
            return None
        parsed = int(text)
        return parsed if parsed > 0 else None
    return None


def format_duration(seconds: float | None) -> str:
    """Format a duration in seconds to a human-readable string.

    Fractional seconds are truncated rather than rounded, so ``90.6`` is
    "1m 30s" — a duration shown in the UI never claims a second that has not
    elapsed. Values that arrive as strings or as ``NaN`` / ``Infinity`` are
    treated as unset.

    Args:
        seconds: Duration in seconds (or None).

    Returns:
        Formatted duration string.
    """
    number = _coerce_finite_number(seconds)
    if number is None or number <= 0:
        return "0m"
    seconds = int(number)
    if seconds == 0:
        # Sub-second durations floor to zero; showing "0s" adds no information.
        return "0m"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0:
        parts.append(f"{secs}s")

    return " ".join(parts) if parts else "0m"


def format_file_size(size: float | None) -> str:
    """Format a file size in bytes to a human-readable string.

    Non-finite and non-numeric values are treated as unset instead of being
    rendered as ``"nan B"`` / ``"inf TB"``.

    Args:
        size: Size in bytes (or None).

    Returns:
        Formatted size string.
    """
    number = _coerce_finite_number(size)
    if number is None or number <= 0:
        return "0 B"

    abs_size = abs(number)
    if abs_size >= 1024**4:
        return f"{abs_size / (1024**4):.1f} TB"
    if abs_size >= 1024**3:
        return f"{abs_size / (1024**3):.1f} GB"
    if abs_size >= 1024**2:
        return f"{abs_size / (1024**2):.1f} MB"
    if abs_size >= 1024:
        return f"{abs_size / 1024:.1f} KB"

    return f"{abs_size:.1f} B"


def format_bitrate(bitrate: float | None) -> str:
    """Format a bitrate in bits per second to a human-readable string.

    Non-finite and non-numeric values are treated as unset.

    Args:
        bitrate: Bitrate in bps (or None).

    Returns:
        Formatted bitrate string.
    """
    number = _coerce_finite_number(bitrate)
    if number is None or number <= 0:
        return "0 bps"

    abs_br = abs(number)
    if abs_br >= 10**9:
        return f"{abs_br / 10**9:.1f} Gbps"
    if abs_br >= 10**6:
        return f"{abs_br / 10**6:.1f} Mbps"
    if abs_br >= 10**3:
        return f"{abs_br / 10**3:.1f} Kbps"

    return f"{abs_br:.0f} bps"


def format_resolution(width: int | None, height: int | None) -> str:
    """Format a resolution from width and height dimensions.

    Args:
        width: Width in pixels (or None).
        height: Height in pixels (or None).

    Returns:
        Formatted resolution string, or ``"Unknown"`` when either dimension
        is missing or unusable.
    """
    width = _coerce_dimension(width)
    height = _coerce_dimension(height)
    if width is None or height is None:
        return "Unknown"

    # Known resolutions
    if width == 1920 and height == 1080:
        return "1080p"
    if width == 1280 and height == 720:
        return "720p"
    if width == 854 and height == 480:
        return "480p"
    if width == 640 and height == 360:
        return "360p"
    if width == 3840 and height == 2160:
        return "4K"
    if width == 800 and height == 600:
        return "800x600"

    # General patterns by height
    if height == 480:
        return f"{width}x480"
    if height == 720:
        return f"{width}x720"
    if height == 1080:
        return f"{width}x1080"
    if height == 2160:
        return f"{width}x2160 (4K)"

    return f"{width}x{height}"


def truncate_text(text: str | None, max_width: int, suffix: str = "...") -> str:
    """Truncate text to a maximum width, adding a suffix if truncated.

    A non-positive *max_width* leaves no room for any text, so the result is
    the empty string; slicing with a negative width would otherwise return a
    large prefix of the input, which is the opposite of truncating.

    Args:
        text: The text to truncate (or None).
        max_width: Maximum width including suffix.
        suffix: Suffix to append when truncating (default "...").

    Returns:
        Truncated text string. Non-string *text* yields ``""`` so the declared
        return type always holds; a list or dict used to be returned unchanged.
    """
    text = _coerce_text(text)
    if text is None:
        return ""
    if max_width <= 0:
        return ""
    if len(text) <= max_width:
        return text

    # If there's no room for the suffix, just truncate to max_width
    if max_width <= len(suffix):
        return text[:max_width]

    # Reserve space for the suffix. The guard above guarantees
    # max_width > len(suffix) here, so ``available`` is always positive.
    available = max_width - len(suffix)
    return text[:available].rstrip() + suffix


def slugify(text: str | None) -> str:
    """Convert text to a URL-friendly slug.

    Args:
        text: The text to convert (or None).

    Returns:
        A lowercase slug with hyphens separating words, or ``""`` when *text*
        is missing or not a string.
    """
    text = _coerce_text(text)
    if text is None:
        return ""

    # Strip leading/trailing whitespace
    text = text.strip()
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Normalize unicode to ASCII (e.g., café -> cafe)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    # Replace any sequence of non-alphanumeric (except spaces) with a single hyphen
    text = re.sub(r"[^a-z0-9 ]+", "-", text)

    # Replace multiple spaces with a single hyphen
    text = re.sub(r" +", "-", text)

    # Collapse multiple hyphens into one
    text = re.sub(r"-+", "-", text)

    # Strip leading/trailing hyphens
    text = text.strip("-")

    # If only hyphens remain, return empty
    if not text:
        return ""

    return text


def format_release_date(date_str: str | None) -> str:
    """Format a release date string to just the date portion.

    Args:
        date_str: ISO format date string or similar (or None).

    Returns:
        Date portion in YYYY-MM-DD format, or empty string when the value is
        missing, empty, or not a string.

    """
    date_str = _coerce_text(date_str)
    if date_str is None:
        return ""
    # The patterns below are anchored at the start of the value, so padding
    # defeated every one of them: ``"  2023-05-12  "`` fell through to the
    # raw-input fallback and was rendered with its spaces intact, and a
    # padded ``"2024"`` was not recognised as a year at all.
    date_str = date_str.strip()
    if not date_str:
        return ""

    # Try to extract YYYY-MM-DD from ISO format
    match = re.match(r"(\d{4}-\d{2}-\d{2})", date_str)
    if match:
        return match.group(1)

    # Try YYYY-MM format
    match = re.match(r"(\d{4}-\d{2})", date_str)
    if match:
        return match.group(1)

    # Try just a year
    match = re.match(r"(\d{4})", date_str)
    if match:
        return match.group(1)

    return date_str
