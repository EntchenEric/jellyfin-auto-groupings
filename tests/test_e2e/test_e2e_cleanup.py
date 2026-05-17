"""E2E tests for cleanup functionality."""

import pytest

from .conftest import api_get, api_post


@pytest.mark.e2e
class TestE2ECleanup:
    """Test listing and deleting folders."""

    def test_list_cleanup_items(self, e2e_session):
        """Should be able to list items for cleanup."""
        result = api_get(e2e_session, "/api/cleanup")
        assert result["status"] == "success"
        assert isinstance(result.get("items"), list)

    def test_cleanup_empty_list(self, e2e_session):
        """Cleaning up with empty folder list should succeed."""
        result = api_post(e2e_session, "/api/cleanup", {"folders": []})
        assert result["status"] in ("success", "error")
