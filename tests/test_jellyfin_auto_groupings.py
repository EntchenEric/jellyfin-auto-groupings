import sys
import pytest
from unittest.mock import MagicMock, patch
import requests

from jellyfin_auto_groupings import (
    get_items,
    group_items_by_prefix,
    create_collection,
    build_argument_parser,
    main,
)


def test_group_items_by_prefix():
    items = [
        {"Id": "1", "Name": "Toy Story"},
        {"Id": "2", "Name": "Toy Story 2"},
        {"Id": "3", "Name": "Toy Story 3"},
        {"Id": "4", "Name": "Standalone Movie"},
    ]
    groups = group_items_by_prefix(items)
    assert "Toy Story" in groups
    assert len(groups["Toy Story"]) == 3
    assert "Standalone Movie" not in groups


def test_get_items_pagination():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = [
        {"Items": [{"Id": "1", "Name": "Movie 1"}], "TotalRecordCount": 2},
        {"Items": [{"Id": "2", "Name": "Movie 2"}], "TotalRecordCount": 2},
    ]

    with patch("requests.get", return_value=mock_response) as mock_get:
        items = get_items("http://localhost:8096", "testkey")
        assert len(items) == 2
        assert mock_get.call_count == 2


def test_get_items_exception():
    with patch("requests.get", side_effect=requests.RequestException("Connection error")):
        items = get_items("http://localhost:8096", "testkey")
        assert items == []


def test_create_collection_dry_run():
    res = create_collection("http://localhost:8096", "testkey", "Test Collection", ["1", "2"], dry_run=True)
    assert res == "dry-run-collection-id"


def test_create_collection_success():
    mock_res = MagicMock()
    mock_res.raise_for_status.return_value = None
    mock_res.json.return_value = {"Id": "col123"}
    with patch("requests.post", return_value=mock_res):
        res = create_collection("http://localhost:8096", "testkey", "Test Collection", ["1", "2"])
        assert res == "col123"


def test_create_collection_failure():
    with patch("requests.post", side_effect=requests.RequestException("API error")):
        res = create_collection("http://localhost:8096", "testkey", "Test Collection", ["1", "2"])
        assert res is None


def test_build_argument_parser():
    parser = build_argument_parser()
    args = parser.parse_args(["--url", "http://localhost:8096", "--api-key", "secret"])
    assert args.url == "http://localhost:8096"
    assert args.api_key == "secret"


def test_main_missing_args(capsys):
    exit_code = main([])
    assert exit_code == 1


def test_main_success():
    items = [{"Id": "1", "Name": "Matrix 1"}, {"Id": "2", "Name": "Matrix 2"}]
    with patch("jellyfin_auto_groupings.get_items", return_value=items):
        with patch("jellyfin_auto_groupings.create_collection", return_value="col_matrix") as mock_create:
            exit_code = main(["--url", "http://localhost", "--api-key", "key", "--dry-run"])
            assert exit_code == 0
            assert mock_create.called
