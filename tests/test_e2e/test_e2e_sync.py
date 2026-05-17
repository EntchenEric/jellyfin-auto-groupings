"""E2E tests for full sync cycle."""


import pytest
import requests

from .conftest import api_get, api_post


@pytest.mark.e2e
class TestE2ESync:
    """Test the complete sync workflow against real Jellyfin."""

    @pytest.fixture(autouse=True)
    def cleanup_groups(self, e2e_session):
        """Remove all groups before each test."""
        config = api_get(e2e_session, "/api/config")
        config["groups"] = []
        requests.post(
            f"{e2e_session['app_url']}/api/config",
            json=config,
            timeout=10,
        )
        yield
        # Cleanup after test
        config = api_get(e2e_session, "/api/config")
        config["groups"] = []
        requests.post(
            f"{e2e_session['app_url']}/api/config",
            json=config,
            timeout=10,
        )

    def test_sync_with_single_genre_group(self, e2e_session):
        """Full sync with one genre-based grouping."""
        # Create a group
        config = api_get(e2e_session, "/api/config")
        config["groups"] = [{
            "name": "E2E Action Movies",
            "source_category": "jellyfin",
            "source_type": "genre",
            "source_value": "Action",
            "sort_order": "",
            "schedule_enabled": False,
            "schedule": "",
            "seasonal_enabled": False,
            "watch_state": "",
        }]
        resp = requests.post(
            f"{e2e_session['app_url']}/api/config",
            json=config,
            timeout=10,
        )
        assert resp.status_code == 200

        # Run sync
        result = api_post(e2e_session, "/api/sync")
        assert result["status"] == "success"
        assert isinstance(result.get("results"), list)
        assert len(result["results"]) == 1
        assert result["results"][0]["group"] == "E2E Action Movies"

    def test_sync_preview_all(self, e2e_session):
        """Preview sync should show expected results without touching disk."""
        config = api_get(e2e_session, "/api/config")
        config["groups"] = [{
            "name": "E2E Sci-Fi",
            "source_category": "jellyfin",
            "source_type": "genre",
            "source_value": "Sci-Fi",
            "sort_order": "",
            "schedule_enabled": False,
            "schedule": "",
            "seasonal_enabled": False,
            "watch_state": "",
        }]
        requests.post(
            f"{e2e_session['app_url']}/api/config",
            json=config,
            timeout=10,
        )

        result = api_post(e2e_session, "/api/sync/preview_all")
        assert result["status"] == "success"
        assert isinstance(result.get("results"), list)
        assert len(result["results"]) >= 1

    def test_sync_empty_groups(self, e2e_session):
        """Sync with no groups should succeed gracefully."""
        result = api_post(e2e_session, "/api/sync")
        assert result["status"] == "success"
        assert result.get("results") == []
