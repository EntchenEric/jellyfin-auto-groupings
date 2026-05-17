"""E2E tests for Jellyfin library creation features."""

import pytest
import requests

from .conftest import api_get


@pytest.mark.e2e
class TestE2ELibraries:
    """Test library auto-creation and cover setting features."""

    def test_config_supports_library_features(self, e2e_session):
        """Config should support auto_create_libraries and auto_set_library_covers."""
        config = api_get(e2e_session, "/api/config")
        assert "auto_create_libraries" in config
        assert "auto_set_library_covers" in config
        assert "target_path_in_jellyfin" in config

    def test_can_enable_library_features(self, e2e_session):
        """Should be able to toggle library features in config."""
        config = api_get(e2e_session, "/api/config")
        config["auto_create_libraries"] = True
        config["auto_set_library_covers"] = True
        config["target_path_in_jellyfin"] = "/e2e-libraries"

        resp = requests.post(
            f"{e2e_session['app_url']}/api/config",
            json=config,
            timeout=10
        )
        assert resp.status_code == 200

        # Verify it was saved
        updated = api_get(e2e_session, "/api/config")
        assert updated["auto_create_libraries"] is True
        assert updated["auto_set_library_covers"] is True
        assert updated["target_path_in_jellyfin"] == "/e2e-libraries"
