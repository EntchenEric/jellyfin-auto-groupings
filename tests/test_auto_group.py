"""Tests for the standalone ``auto_group`` CLI module.

The module is imported from the repository root, so this file bootstraps
``sys.path`` the same way the other root-module tests do.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auto_group import (
    DEFAULT_PATTERNS,
    add_to_collection,
    clean_title,
    create_collection,
    extract_base_title,
    get_libraries,
    get_library_items,
    group_items,
    load_config,
)

# ---------------------------------------------------------------------------
# clean_title
# ---------------------------------------------------------------------------


def test_clean_title_strips_years_and_quality_tags():
    assert clean_title("Matrix (1999)") == "Matrix"
    assert clean_title("Matrix [1080p]") == "Matrix"
    assert clean_title(" Movie (2020) [1080p] ") == "Movie"


def test_clean_title_preserves_inner_punctuation():
    assert clean_title("Matrix: Reloaded") == "Matrix: Reloaded"
    assert clean_title("Matrix, The ") == "Matrix, The"


def test_clean_title_handles_empty_input():
    assert clean_title("") == ""
    assert clean_title(None) == ""


# ---------------------------------------------------------------------------
# extract_base_title
# ---------------------------------------------------------------------------


def test_extract_base_title_uses_first_capture_group():
    patterns = [r"^(.*?)\s+Part\s+\d+", r"^(.*?)\s+\d+$", r"^(.*?):.*$"]
    assert extract_base_title("Harry Potter Part 1", patterns) == "Harry Potter"
    assert extract_base_title("Star Wars 2", patterns) == "Star Wars"
    assert extract_base_title("Avatar: The Way of Water", patterns) == "Avatar"


def test_extract_base_title_falls_back_to_cleaned_title():
    assert extract_base_title("Unique Movie", [r"^(.*?)\s+\d+$"]) == "Unique Movie"


def test_extract_base_title_pattern_without_capture_group():
    """A pattern with no capture group must not raise ``IndexError``."""
    assert extract_base_title("Star Wars: A New Hope", [r"^Star Wars"]) == "Star Wars"
    assert extract_base_title("Matrix 2", [r"^(?:Matrix)"]) == "Matrix"


def test_extract_base_title_non_participating_group():
    """A branch that did not match yields ``None`` instead of crashing."""
    assert extract_base_title("The Matrix", [r"^(\d{4})|(.*)$"]) == "The Matrix"


def test_extract_base_title_invalid_regex_is_skipped():
    """An invalid regex falls through to the next usable pattern."""
    assert (
        extract_base_title("Harry Potter 2", [r"([", r"^(.*?)\s+\d+$"])
        == "Harry Potter"
    )


def test_extract_base_title_empty_title():
    assert extract_base_title("", DEFAULT_PATTERNS) == ""


# ---------------------------------------------------------------------------
# group_items
# ---------------------------------------------------------------------------


def test_group_items_groups_matching_titles():
    items = [
        {"Id": "1", "Name": "Harry Potter 1"},
        {"Id": "2", "Name": "Harry Potter 2"},
        {"Id": "3", "Name": "Unique Movie"},
    ]
    groups = group_items(items, [r"^(.*?)\s+\d+$"], min_group_size=2)
    assert list(groups) == ["Harry Potter"]
    assert len(groups["Harry Potter"]) == 2


def test_group_items_skips_missing_or_null_names():
    """Items without a usable name are skipped, not merged into one group."""
    items = [
        {"Id": "1", "Name": None},
        {"Id": "2"},
        {"Id": "3", "Name": "   "},
        {"Id": "4", "Name": "Unique Movie"},
    ]
    groups = group_items(items, [r"^(.*)$"], min_group_size=1)
    assert groups == {"Unique Movie": [{"Id": "4", "Name": "Unique Movie"}]}


def test_group_items_clamps_min_group_size_below_one():
    """A ``min_group_size`` below 1 still returns every group exactly once."""
    items = [{"Id": str(i), "Name": "X"} for i in range(3)]
    groups = group_items(items, [r"^(.*)$"], min_group_size=0)
    assert len(groups["X"]) == 3


def test_group_items_empty_input():
    assert group_items([], DEFAULT_PATTERNS) == {}


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_reads_environment(monkeypatch):
    monkeypatch.setenv("JELLYFIN_URL", "http://env-jellyfin:8096")
    monkeypatch.setenv("JELLYFIN_API_KEY", "env_key_123")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("MIN_GROUP_SIZE", "3")

    config = load_config("definitely_missing.json")

    assert config["JELLYFIN_URL"] == "http://env-jellyfin:8096"
    assert config["JELLYFIN_API_KEY"] == "env_key_123"
    assert config["DRY_RUN"] is True
    assert config["MIN_GROUP_SIZE"] == 3


def test_load_config_json_file_overrides_environment(monkeypatch):
    monkeypatch.setenv("JELLYFIN_URL", "http://env-jellyfin:8096")
    config_data = {
        "JELLYFIN_URL": "http://file-jellyfin:8096",
        "JELLYFIN_API_KEY": "file_key",
        "DRY_RUN": False,
        "MIN_GROUP_SIZE": 2,
    }
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        json.dump(config_data, handle)
        temp_path = handle.name
    try:
        config = load_config(temp_path)
    finally:
        Path(temp_path).unlink()

    assert config["JELLYFIN_URL"] == "http://file-jellyfin:8096"
    assert config["JELLYFIN_API_KEY"] == "file_key"
    assert config["DRY_RUN"] is False


def test_load_config_tolerates_bad_min_group_size_env(monkeypatch):
    """A non-numeric ``MIN_GROUP_SIZE`` falls back instead of failing import."""
    monkeypatch.setenv("MIN_GROUP_SIZE", "not-a-number")
    assert load_config("definitely_missing.json")["MIN_GROUP_SIZE"] == 2


@pytest.mark.parametrize("raw", ["0", "-5", "null"])
def test_load_config_clamps_invalid_min_group_size(raw):
    """Out-of-range or untyped ``MIN_GROUP_SIZE`` values never reach the caller."""
    payload = {"MIN_GROUP_SIZE": None if raw == "null" else int(raw)}
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        json.dump(payload, handle)
        temp_path = handle.name
    try:
        config = load_config(temp_path)
    finally:
        Path(temp_path).unlink()

    assert config["MIN_GROUP_SIZE"] >= 1


def test_load_config_normalizes_json_string_booleans():
    """A JSON ``"DRY_RUN": "false"`` string must not read as truthy."""
    config_data = {"DRY_RUN": "false", "MIN_GROUP_SIZE": "3", "PATTERNS": ["^(.*)$"]}
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        json.dump(config_data, handle)
        temp_path = handle.name
    try:
        config = load_config(temp_path)
    finally:
        Path(temp_path).unlink()

    assert config["DRY_RUN"] is False
    assert config["MIN_GROUP_SIZE"] == 3
    assert config["PATTERNS"] == ["^(.*)$"]


def test_load_config_rejects_non_list_patterns():
    """``PATTERNS`` that is not a list of strings falls back to the defaults."""
    config_data = {"PATTERNS": "^(.*)$"}
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        json.dump(config_data, handle)
        temp_path = handle.name
    try:
        config = load_config(temp_path)
    finally:
        Path(temp_path).unlink()

    assert config["PATTERNS"] == DEFAULT_PATTERNS


def test_load_config_malformed_json_keeps_defaults():
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write("{not json")
        temp_path = handle.name
    try:
        config = load_config(temp_path)
    finally:
        Path(temp_path).unlink()

    assert config["MIN_GROUP_SIZE"] == 2
    assert config["PATTERNS"] == DEFAULT_PATTERNS


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


@patch("requests.get")
def test_get_libraries_returns_items(mock_get):
    response = MagicMock()
    response.json.return_value = {"Items": [{"Name": "Movies", "Id": "lib1"}]}
    mock_get.return_value = response

    assert get_libraries("http://localhost:8096", "key") == [
        {"Name": "Movies", "Id": "lib1"}
    ]


@patch("requests.get")
def test_get_libraries_returns_empty_on_error(mock_get):
    mock_get.side_effect = OSError("boom")
    assert get_libraries("http://localhost:8096", "key") == []


@patch("requests.get")
def test_get_library_items_returns_items(mock_get):
    response = MagicMock()
    response.json.return_value = {"Items": [{"Id": "1", "Name": "A"}]}
    mock_get.return_value = response

    assert get_library_items("http://localhost:8096", "key", "lib1") == [
        {"Id": "1", "Name": "A"}
    ]


@patch("requests.get")
def test_get_library_items_returns_empty_on_error(mock_get):
    mock_get.side_effect = OSError("boom")
    assert get_library_items("http://localhost:8096", "key", "lib1") == []


@patch("requests.post")
def test_create_collection_returns_id(mock_post):
    response = MagicMock()
    response.json.return_value = {"Id": "coll123"}
    mock_post.return_value = response

    assert (
        create_collection(
            "http://localhost:8096", "key", "Matrix Collection", ["1", "2"]
        )
        == "coll123"
    )


@patch("requests.post")
def test_create_collection_filters_unusable_ids(mock_post):
    """Null/blank IDs are dropped before the request is built."""
    response = MagicMock()
    response.json.return_value = {"Id": "coll123"}
    mock_post.return_value = response

    create_collection("http://localhost:8096", "key", "Group", [None, "", "  ", "abc"])

    assert mock_post.call_args.kwargs["params"]["Ids"] == "abc"


@patch("requests.post")
def test_create_collection_no_usable_ids_sends_no_request(mock_post):
    assert create_collection("http://u", "k", "Group", [None, ""]) is None
    mock_post.assert_not_called()


@patch("requests.post")
def test_create_collection_with_empty_body(mock_post):
    """A 200 response with no JSON body returns ``None`` instead of raising."""
    response = MagicMock()
    response.json.side_effect = ValueError("no json")
    mock_post.return_value = response

    assert create_collection("http://u", "k", "Group", ["1"]) is None


@patch("requests.post")
def test_create_collection_returns_none_on_http_error(mock_post):
    mock_post.side_effect = OSError("boom")
    assert create_collection("http://u", "k", "Group", ["1"]) is None


@patch("requests.post")
def test_add_to_collection_filters_unusable_ids(mock_post):
    mock_post.return_value = MagicMock()

    assert add_to_collection("http://u", "k", "coll1", [None, "  ", "abc"]) is True
    assert mock_post.call_args.kwargs["params"]["Ids"] == "abc"


@patch("requests.post")
def test_add_to_collection_no_usable_ids_sends_no_request(mock_post):
    assert add_to_collection("http://u", "k", "coll1", [None, ""]) is False
    mock_post.assert_not_called()


@patch("requests.post")
def test_add_to_collection_returns_false_on_http_error(mock_post):
    mock_post.side_effect = OSError("boom")
    assert add_to_collection("http://u", "k", "coll1", ["abc"]) is False


# ---------------------------------------------------------------------------
# Unusable JELLYFIN_URL values
# ---------------------------------------------------------------------------
# ``config.json`` is user-editable, so JELLYFIN_URL can be any JSON type.
# ``url.rstrip("/")`` used to run before the ``try`` block, so a number, null,
# or a list raised ``AttributeError`` out of helpers that document an
# empty-list/None return and killed the CLI on the first library.


@pytest.mark.parametrize("url", [None, 5, ["http://x"], {"u": 1}, ""])
@patch("requests.get")
def test_get_libraries_tolerates_unusable_url(mock_get, url):
    assert get_libraries(url, "key") == []
    mock_get.assert_not_called()


@pytest.mark.parametrize("url", [None, 5, ["http://x"], {"u": 1}, ""])
@patch("requests.get")
def test_get_library_items_tolerates_unusable_url(mock_get, url):
    assert get_library_items(url, "key", "lib1") == []
    mock_get.assert_not_called()


@pytest.mark.parametrize("url", [None, 5, ["http://x"], {"u": 1}, ""])
@patch("requests.post")
def test_create_collection_tolerates_unusable_url(mock_post, url):
    assert create_collection(url, "key", "Name", ["1"]) is None
    mock_post.assert_not_called()


@pytest.mark.parametrize("url", [None, 5, ["http://x"], {"u": 1}, ""])
@patch("requests.post")
def test_add_to_collection_tolerates_unusable_url(mock_post, url):
    assert add_to_collection(url, "key", "coll", ["1"]) is False
    mock_post.assert_not_called()


@patch("requests.get")
def test_get_libraries_trims_padded_url(mock_get):
    response = MagicMock()
    response.json.return_value = {"Items": [{"Name": "Movies", "Id": "lib1"}]}
    mock_get.return_value = response

    get_libraries("  http://localhost:8096/  ", "key")

    assert mock_get.call_args.args[0] == "http://localhost:8096/Views"
