"""Error branches of the legacy root ``main.py`` client.

Each Jellyfin REST call in ``JellyfinGroupings`` logs and re-raises a
``requests.RequestException``. Those except arms were the only uncovered
statements in the module.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

import main as root_main


def _error_response():
    response = MagicMock()
    response.raise_for_status.side_effect = requests.ConnectionError("refused")
    return response


def test_get_collections_request_error_logged_and_raised():
    client = root_main.JellyfinGroupings(
        server_url="http://localhost:8096", api_key="key"
    )
    with (
        patch.object(client.session, "get", return_value=_error_response()),
        pytest.raises(requests.ConnectionError),
    ):
        client.get_collections()


def test_get_movies_request_error_logged_and_raised():
    client = root_main.JellyfinGroupings(
        server_url="http://localhost:8096", api_key="key"
    )
    with (
        patch.object(client.session, "get", return_value=_error_response()),
        pytest.raises(requests.ConnectionError),
    ):
        client.get_movies()


def test_create_collection_request_error_logged_and_raised():
    client = root_main.JellyfinGroupings(
        server_url="http://localhost:8096", api_key="key"
    )
    with (
        patch.object(client.session, "post", return_value=_error_response()),
        pytest.raises(requests.ConnectionError),
    ):
        client.create_collection("Set")


def test_add_to_collection_request_error_logged_and_raised():
    client = root_main.JellyfinGroupings(
        server_url="http://localhost:8096", api_key="key"
    )
    with (
        patch.object(client.session, "post", return_value=_error_response()),
        pytest.raises(requests.ConnectionError),
    ):
        client.add_to_collection("col1", ["mov1"])
