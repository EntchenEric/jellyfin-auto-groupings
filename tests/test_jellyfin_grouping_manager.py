"""
Unit tests for JellyfinGroupingManager and other functions in jellyfin_auto_groupings/__init__.py
"""

from unittest.mock import MagicMock

from jellyfin_auto_groupings import (
    JellyfinGroupingManager,
    extract_collection_name,
    validate_movie_item,
)


def test_extract_collection_name():
    # Basic case
    assert extract_collection_name("Toy Story 2") == "Toy Story Collection"
    assert extract_collection_name("Inception") is None

    # Edge cases
    assert extract_collection_name("") is None
    assert extract_collection_name(None) is None
    assert extract_collection_name(123) is None

    # Patterns
    assert extract_collection_name("Series: Episode 1") == "Series Collection"
    assert extract_collection_name("Movie (1999)") == "Movie Collection"
    assert extract_collection_name("Title: Subtitle") == "Title Collection"

    # Already a collection name
    assert extract_collection_name("Toy Story Collection") is None
    assert extract_collection_name("Test") is None


def test_validate_movie_item():
    # Valid
    assert validate_movie_item({"Name": "Test", "Id": "123"}) is True

    # Invalid
    assert validate_movie_item(None) is False
    assert validate_movie_item({}) is False
    assert validate_movie_item({"Name": "Test"}) is False  # Missing Id
    assert validate_movie_item({"Id": "123"}) is False  # Missing Name
    assert validate_movie_item([]) is False
    assert validate_movie_item("string") is False


def test_jellyfin_grouping_manager_mock():
    mock_client = MagicMock()
    manager = JellyfinGroupingManager(mock_client)

    # Patch the actual process_groupings in the module
    import jellyfin_auto_groupings

    original_process_groupings = jellyfin_auto_groupings.process_groupings
    jellyfin_auto_groupings.process_groupings = MagicMock(
        return_value=[{"Id": "1", "Name": "Test"}]
    )

    try:
        result = manager.process("library123")
        assert result == [{"Id": "1", "Name": "Test"}]
        jellyfin_auto_groupings.process_groupings.assert_called_once_with(
            mock_client, "library123"
        )
    finally:
        jellyfin_auto_groupings.process_groupings = original_process_groupings
