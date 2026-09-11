from jellyfin_auto_groupings import JellyfinClient
import pytest

def test_client_init():
    client = JellyfinClient("http://localhost:8096", "test-key", "user-1")
    assert client.server_url == "http://localhost:8096"
    assert client.api_key == "test-key"
    assert client.user_id == "user-1"
