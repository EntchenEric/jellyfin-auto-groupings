"""E2E tests for server connection."""

import pytest

from .conftest import api_post


@pytest.mark.e2e
class TestE2EConnection:
    """Test connection to Jellyfin server via the app."""

    def test_test_server_endpoint(self, e2e_session):
        """The test-server endpoint should return success against real Jellyfin."""
        result = api_post(e2e_session, "/api/test-server", {
            "jellyfin_url": e2e_session["jellyfin_url_internal"],
            "api_key": e2e_session["api_key"],
        })
        assert result["status"] == "success"

    def test_server_info_accessible(self, e2e_session):
        """Server info should be retrievable from the test-server response."""
        result = api_post(e2e_session, "/api/test-server", {
            "jellyfin_url": e2e_session["jellyfin_url_internal"],
            "api_key": e2e_session["api_key"],
        })
        assert "message" in result

    def test_invalid_url_fails(self, e2e_session):
        """An invalid URL should result in an error."""
        result = api_post(e2e_session, "/api/test-server", {
            "jellyfin_url": "http://nonexistent:9999",
            "api_key": "fake-key",
        })
        assert result["status"] == "error"

    def test_invalid_api_key_fails(self, e2e_session):
        """An incorrect API key should result in an error."""
        result = api_post(e2e_session, "/api/test-server", {
            "jellyfin_url": e2e_session["jellyfin_url_internal"],
            "api_key": "invalid-key-12345",
        })
        assert result["status"] == "error"
