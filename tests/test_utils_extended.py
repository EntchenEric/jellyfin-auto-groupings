from utils.formatting import (
    format_bitrate,
    format_duration,
    format_file_size,
    format_release_date,
    format_resolution,
    slugify,
    truncate_text,
)
from utils.helpers import (
    chunk_list,
    deep_merge,
    extract_year_from_title,
    flatten_dict,
    group_by_key,
    is_valid_uuid,
    normalize_title,
    parse_media_tags,
    safe_get,
    sanitize_filename,
)


def test_format_duration():
    assert format_duration(None) == "0m"
    assert format_duration(0) == "0m"
    assert format_duration(45) == "45s"
    assert format_duration(120) == "2m"
    assert format_duration(150) == "2m 30s"
    assert format_duration(3600) == "1h"
    assert format_duration(3665) == "1h 1m 5s"
    assert format_duration(-10) == "0m"


def test_format_file_size():
    assert format_file_size(None) == "0 B"
    assert format_file_size(0) == "0 B"
    assert format_file_size(-50) == "0 B"
    assert format_file_size(500) == "500.0 B"
    assert format_file_size(1024) == "1.0 KB"
    assert format_file_size(1024 * 1024) == "1.0 MB"
    assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"
    assert format_file_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"


def test_format_bitrate():
    assert format_bitrate(None) == "0 bps"
    assert format_bitrate(0) == "0 bps"
    assert format_bitrate(-100) == "0 bps"
    assert format_bitrate(500) == "500 bps"
    assert format_bitrate(2000) == "2.0 Kbps"
    assert format_bitrate(5000000) == "5.0 Mbps"
    assert format_bitrate(2000000000) == "2.0 Gbps"


def test_format_resolution():
    assert format_resolution(None, 1080) == "Unknown"
    assert format_resolution(1920, None) == "Unknown"
    assert format_resolution(3840, 2160) == "4K"
    assert format_resolution(1920, 1080) == "1080p"
    assert format_resolution(1280, 720) == "720p"
    assert format_resolution(854, 480) == "480p"
    assert format_resolution(640, 360) == "360p"
    assert format_resolution(800, 600) == "800x600"
    # Non-standard widths fall back to the height-based pattern.
    assert format_resolution(720, 480) == "720x480"
    assert format_resolution(960, 720) == "960x720"
    assert format_resolution(1440, 1080) == "1440x1080"
    assert format_resolution(100, 2160) == "100x2160 (4K)"
    assert format_resolution(1920, 1200) == "1920x1200"


def test_truncate_text():
    assert truncate_text(None, 10) == ""
    assert truncate_text("short", 10) == "short"
    assert truncate_text("hello world!", 8) == "hello..."
    assert truncate_text("hello world!", 8, suffix="~") == "hello w~"
    assert truncate_text("hello", 2, suffix="...") == "he"
    # max_width exactly equal to the suffix length leaves no room for text.
    assert truncate_text("hello", 3, suffix="...") == "hel"


def test_slugify():
    assert slugify(None) == ""
    assert slugify("  Hello World!  ") == "hello-world"
    assert slugify("Café & Bar") == "cafe-bar"
    assert slugify("__Special---Chars__") == "special-chars"
    # Whitespace-only and punctuation-only input collapse to an empty slug.
    assert slugify("   ") == ""
    assert slugify("---") == ""


def test_format_release_date():
    assert format_release_date(None) == ""
    assert format_release_date("") == ""
    assert format_release_date("2023-05-12T14:30:00Z") == "2023-05-12"
    assert format_release_date("2023-05-12") == "2023-05-12"
    assert format_release_date("invalid-date") == "invalid-date"
    # Year-month and bare-year forms are accepted as-is.
    assert format_release_date("2023-05") == "2023-05"
    assert format_release_date("2023") == "2023"


def test_safe_get():
    data = {"a": {"b": {"c": 42}, "items": [10, 20, 30]}}
    assert safe_get(data, "a.b.c") == 42
    assert safe_get(data, "a.items.1") == 20
    assert safe_get(data, "a.items.5", default="missing") == "missing"
    assert safe_get(data, "x.y.z", default=None) is None
    assert safe_get(None, "a.b") is None
    assert safe_get(data, "") == data
    assert safe_get(data, "a.b.c.d", default="none") == "none"
    # A non-numeric key against a list is a miss, not a TypeError.
    assert safe_get(data, "a.items.x", default="missing") == "missing"
    # Traversal past a scalar cannot continue.
    assert safe_get(data, "a.b.c.d.e", default="missing") == "missing"
    # Negative indexes are rejected rather than wrapping from the end.
    assert safe_get(data, "a.items.-1", default="missing") == "missing"


def test_chunk_list():
    assert chunk_list([], 2) == []
    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert chunk_list([1, 2], 0) == [[1, 2]]
    assert chunk_list([1, 2], -1) == [[1, 2]]


def test_deep_merge():
    dict1 = {"a": 1, "b": {"x": 10, "y": 20}}
    dict2 = {"b": {"y": 25, "z": 30}, "c": 3}
    merged = deep_merge(dict1, dict2)
    assert merged == {"a": 1, "b": {"x": 10, "y": 25, "z": 30}, "c": 3}
    # Ensure original dicts are not modified
    assert dict1["b"] == {"x": 10, "y": 20}


def test_flatten_dict():
    nested = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    assert flatten_dict(nested) == {"a": 1, "b.c": 2, "b.d.e": 3}
    assert flatten_dict({}) == {}
    assert flatten_dict({"a": 1, "b": 2}, sep="/") == {"a": 1, "b": 2}


def test_sanitize_filename():
    assert sanitize_filename("movie: the sequel?.mkv") == "movie_ the sequel_.mkv"
    assert sanitize_filename("../../../etc/passwd") == ".._.._.._etc_passwd"
    assert sanitize_filename("   name   ") == "name"
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename("  ...  ") == "unnamed"


def test_is_valid_uuid():
    assert is_valid_uuid("123e4567-e89b-12d3-a456-426614174000") is True
    assert is_valid_uuid("123e4567e89b12d3a456426614174000") is True
    assert is_valid_uuid("not-a-uuid") is False
    assert is_valid_uuid("") is False
    assert is_valid_uuid(None) is False


def test_parse_media_tags():
    tags = ["Action", " Sci-Fi ", "action", "", "Comedy"]
    assert parse_media_tags(tags) == ["Action", "Sci-Fi", "Comedy"]
    assert parse_media_tags([]) == []
    assert parse_media_tags(["  "]) == []
    # Deduplication is case-insensitive and keeps first-seen order, so the
    # result is not sorted (matching the documented behaviour).
    assert parse_media_tags(["b", "A", "a", "c"]) == ["b", "A", "c"]


def test_normalize_title():
    assert normalize_title("The Matrix") == "matrix"
    assert normalize_title("A Beautiful Mind") == "beautiful mind"
    assert normalize_title("An American Werewolf") == "american werewolf"
    assert normalize_title("Der Untergang", remove_articles=True) == "untergang"
    assert (
        normalize_title("Iron Man 2: Extended Edition") == "iron man 2 extended edition"
    )
    assert normalize_title("") == ""
    assert normalize_title(None) == ""
    assert normalize_title("The Matrix", remove_articles=False) == "the matrix"


def test_extract_year_from_title():
    assert extract_year_from_title("Inception (2010)") == ("Inception", 2010)
    assert extract_year_from_title("2001: A Space Odyssey (1968)") == (
        "2001: A Space Odyssey",
        1968,
    )
    assert extract_year_from_title("Blade Runner [1982]") == ("Blade Runner", 1982)
    assert extract_year_from_title("Interstellar 2014") == ("Interstellar", 2014)
    assert extract_year_from_title("Avengers") == ("Avengers", None)
    assert extract_year_from_title("") == ("", None)
    assert extract_year_from_title(None) == ("", None)


def test_group_by_key():
    items = [
        {"genre": "Action", "title": "Die Hard"},
        {"genre": "Action", "title": "Mad Max"},
        {"genre": "Comedy", "title": "Superbad"},
    ]
    grouped = group_by_key(items, "genre")
    assert len(grouped["Action"]) == 2
    assert len(grouped["Comedy"]) == 1
    assert grouped["Action"][0]["title"] == "Die Hard"
    assert group_by_key([], "genre") == {}
