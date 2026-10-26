"""Formatting and helper functions must tolerate non-string field values.

Jellyfin payloads and hand-edited config are not type-safe: ``ProductionYear``
can arrive as a string, ``Name`` as ``null``, and a corrupt entry can put a
number or a list where a title is expected.  Every helper here declares a
concrete return type, so raising ``AttributeError``/``TypeError`` from an
inner ``.strip()`` or ``re.sub`` turned a bad field into a 500 instead of a
blank cell.  These tests pin the documented "unusable input yields the empty
result" behaviour.
"""

import math

import pytest

from utils.formatting import (
    format_release_date,
    format_resolution,
    slugify,
    truncate_text,
)
from utils.helpers import (
    extract_year_from_title,
    normalize_title,
    sanitize_filename,
)

# Values a loosely typed payload can realistically carry where a string,
# a year, or a pixel dimension is documented.
BAD_SCALARS = [123, 1999, 20240101, True, False, 1.5, ["2020-01-01"], {"a": 1}]


@pytest.mark.parametrize("value", BAD_SCALARS)
def test_slugify_returns_empty_for_non_string(value):
    assert slugify(value) == ""


@pytest.mark.parametrize("value", BAD_SCALARS)
def test_truncate_text_returns_empty_for_non_string(value):
    # The declared return type is ``str``; a list used to come back unchanged.
    result = truncate_text(value, 10)
    assert isinstance(result, str)
    assert result == ""


@pytest.mark.parametrize("value", BAD_SCALARS)
def test_format_release_date_returns_empty_for_non_string(value):
    assert format_release_date(value) == ""


@pytest.mark.parametrize("value", BAD_SCALARS)
def test_normalize_title_returns_empty_for_non_string(value):
    assert normalize_title(value) == ""


@pytest.mark.parametrize("value", BAD_SCALARS)
def test_extract_year_from_title_tolerates_non_string(value):
    assert extract_year_from_title(value) == ("", None)


@pytest.mark.parametrize("value", BAD_SCALARS)
def test_sanitize_filename_tolerates_non_string(value):
    assert sanitize_filename(value) == "unnamed"


@pytest.mark.parametrize("width,height", [(True, 1080), (1920, False)])
def test_format_resolution_rejects_booleans(width, height):
    # bool is an int subclass but True is not a pixel dimension; this used to
    # render as "Truex1080".
    assert format_resolution(width, height) == "Unknown"


@pytest.mark.parametrize(
    "width,height",
    [
        (["1920"], 1080),
        (1920, {"h": 1080}),
        (0, 1080),
        (-5, 1080),
        (float("nan"), 1080),
        (float("inf"), 1080),
        (1.5, 1080),
    ],
)
def test_format_resolution_rejects_unusable_dimensions(width, height):
    assert format_resolution(width, height) == "Unknown"


def test_format_resolution_accepts_numeric_strings():
    assert format_resolution("1920", "1080") == "1080p"
    assert format_resolution(" 1280 ", 720) == "720p"


def test_format_resolution_accepts_integral_floats():
    assert format_resolution(3840.0, 2160.0) == "4K"
    assert format_resolution(1920.0, 1080.0) == "1080p"


def test_format_resolution_still_formats_non_standard_ratios():
    assert format_resolution(1920, 1200) == "1920x1200"
    assert format_resolution(100, 2160) == "100x2160 (4K)"


def test_helper_outputs_for_valid_input_are_unchanged():
    """The coercion guards must not change results for well-formed input."""
    assert slugify("Café & Bar") == "cafe-bar"
    assert truncate_text("hello world!", 8) == "hello..."
    assert format_release_date("2023-05-12T14:30:00Z") == "2023-05-12"
    assert normalize_title("The Iron Man") == "iron man"
    assert sanitize_filename("  My: Movie?.mkv  ") == "My_ Movie_.mkv"
    assert extract_year_from_title("Blade Runner [1982]") == ("Blade Runner", 1982)


def test_finite_number_helper_rejects_non_finite():
    """Guard the shared numeric coercion used by the size/duration helpers."""
    from utils.formatting import _coerce_finite_number

    assert _coerce_finite_number(float("nan")) is None
    assert _coerce_finite_number(float("inf")) is None
    assert _coerce_finite_number(True) is None
    assert _coerce_finite_number("12.5") == 12.5
    assert _coerce_finite_number(math.e) == math.e
