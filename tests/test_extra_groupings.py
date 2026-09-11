import pytest
from unittest.mock import MagicMock
from jellyfin_auto_groupings import (
    JellyfinGroupingManager,
    group_movies_by_collection,
    validate_movie_item,
    extract_collection_name,
)
from src.jellyfin_auto_groupings.groupings import process_groupings, parse_grouping_rules


def test_extract_collection_name():
    assert extract_collection_name("Toy Story 2") == "Toy Story Collection"
    assert extract_collection_name("Iron Man 3") == "Iron Man Collection"
    assert extract_collection_name("The Dark Knight") is None
    assert extract_collection_name("") is None
    assert extract_collection_name(None) is None


def test_validate_movie_item():
    assert validate_movie_item({"Name": "Movie 1", "Id": "123"}) is True
    assert validate_movie_item({"Name": "Movie 1"}) is False
    assert validate_movie_item({"Id": "123"}) is False
    assert validate_movie_item({}) is False
    assert validate_movie_item(None) is False


def test_group_movies_by_collection():
    movies = [
        {"Name": "Toy Story 1", "Id": "1"},
        {"Name": "Toy Story 2", "Id": "2"},
        {"Name": "Avatar", "Id": "3"},
    ]
    grouped = group_movies_by_collection(movies)
    assert "Toy Story Collection" in grouped
    assert len(grouped["Toy Story Collection"]) == 2
    assert "Avatar" not in grouped


def test_parse_grouping_rules():
    rules = {"collections": {"Sci-Fi": ["Star Wars", "Star Trek"]}}
    parsed = parse_grouping_rules(rules)
    assert "Sci-Fi" in parsed
    assert parsed["Sci-Fi"] == ["Star Wars", "Star Trek"]


def test_process_groupings_empty():
    client = MagicMock()
    result = process_groupings(client, {})
    assert result == {}
