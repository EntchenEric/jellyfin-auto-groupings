"""Formatting utilities for Jellyfin Groupings."""


def format_duration(seconds: int | None) -> str:
    """Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds (or None).

    Returns:
        Formatted duration string.
    """
    if seconds is None or seconds == 0:
        return "0m"
    if seconds < 0:
        seconds = 0

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


def format_file_size(size: int | float | None) -> str:
    """Format a file size in bytes to a human-readable string.

    Args:
        size: Size in bytes (or None).

    Returns:
        Formatted size string.
    """
    if size is None or size <= 0:
        return "0 B"

    abs_size = abs(size)
    if abs_size >= 1024 ** 4:
        return f"{abs_size / (1024 ** 4):.1f} TB"
    if abs_size >= 1024 ** 3:
        return f"{abs_size / (1024 ** 3):.1f} GB"
    if abs_size >= 1024 ** 2:
        return f"{abs_size / (1024 ** 2):.1f} MB"
    if abs_size >= 1024:
        return f"{abs_size / 1024:.1f} KB"

    return f"{abs_size:.1f} B"


def format_bitrate(bitrate: int | float | None) -> str:
    """Format a bitrate in bits per second to a human-readable string.

    Args:
        bitrate: Bitrate in bps (or None).

    Returns:
        Formatted bitrate string.
    """
    if bitrate is None or bitrate <= 0:
        return "0 bps"

    abs_br = abs(bitrate)
    if abs_br >= 10 ** 9:
        return f"{abs_br / 10 ** 9:.1f} Gbps"
    if abs_br >= 10 ** 6:
        return f"{abs_br / 10 ** 6:.1f} Mbps"
    if abs_br >= 10 ** 3:
        return f"{abs_br / 10 ** 3:.1f} Kbps"

    return f"{abs_br} bps"


def format_resolution(width: int | None, height: int | None) -> str:
    """Format a resolution from width and height dimensions.

    Args:
        width: Width in pixels (or None).
        height: Height in pixels (or None).

    Returns:
        Formatted resolution string.
    """
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

    Args:
        text: The text to truncate (or None).
        max_width: Maximum width including suffix.
        suffix: Suffix to append when truncating (default "...").

    Returns:
        Truncated text string.
    """
    if text is None:
        return ""
    if len(text) <= max_width:
        return text

    # If there's no room for the suffix, just truncate to max_width
    if max_width <= len(suffix):
        return text[:max_width]

    # Reserve space for suffix
    available = max_width - len(suffix)
    if available <= 0:
        return text[:max_width]

    return text[:available].rstrip() + suffix


def slugify(text: str | None) -> str:
    """Convert text to a URL-friendly slug.

    Args:
        text: The text to convert (or None).

    Returns:
        A lowercase slug with hyphens separating words.
    """
    if text is None:
        return ""

    # Strip leading/trailing whitespace
    text = text.strip()
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Normalize unicode to ASCII (e.g., café -> cafe)
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    # Replace any sequence of non-alphanumeric (except spaces) with a single hyphen
    import re
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
        Date portion in YYYY-MM-DD format, or empty string.
    """
    if date_str is None or date_str == "":
        return ""

    import re

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