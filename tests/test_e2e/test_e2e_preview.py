"""E2E tests for grouping preview functionality."""

import pytest

from .conftest import api_post


@pytest.mark.e2e
class TestE2EPreview:
    """Test the preview endpoint against a real Jellyfin server."""

    def test_preview_genre(self, e2e_session):
        """Preview with a genre should return item count and items."""
        result = api_post(e2e_session, "/api/grouping/preview", {
            "type": "genre",
            "value": "Action",
            "watch_state": "",
        })
        assert result["status"] == "success"
        assert isinstance(result.get("count"), int)
        assert isinstance(result.get("preview_items"), list)

    def test_preview_requires_value(self, e2e_session):
        """Preview without a value should error."""
        result = api_post(e2e_session, "/api/grouping/preview", {
            "type": "genre",
            "value": "",
            "watch_state": "",
        })
        assert result["status"] == "error"

    def test_preview_general_search(self, e2e_session):
        """Preview with 'general' type should work for text searches."""
        result = api_post(e2e_session, "/api/grouping/preview", {
            "type": "general",
            "value": "Matrix",
            "watch_state": "",
        })
        assert result["status"] == "success"
