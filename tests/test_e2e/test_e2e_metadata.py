"""E2E tests for metadata retrieval from real Jellyfin."""

import pytest
from .conftest import api_get


@pytest.mark.e2e
class TestE2EMetadata:
    """Test fetching metadata from Jellyfin."""

    def test_metadata_endpoint_returns_success(self, e2e_session):
        """The metadata endpoint should return status success."""
        result = api_get(e2e_session, "/api/jellyfin/metadata")
        assert result["status"] == "success"

    def test_metadata_has_categories(self, e2e_session):
        """Metadata should include genre, studio, tag, actor categories."""
        result = api_get(e2e_session, "/api/jellyfin/metadata")
        metadata = result["metadata"]
        for cat in ("genre", "studio", "tag", "actor"):
            assert cat in metadata
            assert isinstance(metadata[cat], list)

    def test_users_endpoint(self, e2e_session):
        """The users endpoint should return Jellyfin users."""
        result = api_get(e2e_session, "/api/jellyfin/users")
        assert result["status"] == "success"
        assert isinstance(result.get("users"), list)
