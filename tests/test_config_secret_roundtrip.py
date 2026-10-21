"""Regression tests for masked secret round-tripping through the config API.

``GET /api/config`` replaces sensitive values with ``"****"`` so they never
leak to the browser. The frontend then posts that same object back on save,
so without an explicit restore step the real API key was overwritten with
the literal mask, silently breaking the next sync.
"""

import json

import pytest

import config
from config import load_stored_config


@pytest.fixture
def seeded_config(temp_config):
    """Write a config with real secrets and return the on-disk path."""
    cfg = config._default_config_copy()
    cfg["jellyfin_url"] = "http://jellyfin.local:8096"
    cfg["api_key"] = "real-jellyfin-key"
    cfg["trakt_client_id"] = "real-trakt-id"
    cfg["tmdb_api_key"] = "real-tmdb-key"
    config.save_config(cfg)
    return temp_config


def _read_saved(temp_config):
    return json.loads(temp_config.read_text(encoding="utf-8"))


def test_get_config_masks_every_sensitive_key(client, seeded_config):
    payload = client.get("/api/config").get_json()

    assert payload["api_key"] == "****"
    assert payload["trakt_client_id"] == "****"
    assert payload["tmdb_api_key"] == "****"
    # Non-sensitive values stay readable.
    assert payload["jellyfin_url"] == "http://jellyfin.local:8096"


def test_saving_masked_config_preserves_stored_secrets(client, seeded_config):
    """Posting the masked GET response back must not destroy the secrets."""
    payload = client.get("/api/config").get_json()

    response = client.post("/api/config", json=payload)

    assert response.status_code == 200
    saved = _read_saved(seeded_config)
    assert saved["api_key"] == "real-jellyfin-key"
    assert saved["trakt_client_id"] == "real-trakt-id"
    assert saved["tmdb_api_key"] == "real-tmdb-key"


def test_saving_masked_config_reports_restored_key(client, seeded_config):
    payload = client.get("/api/config").get_json()

    body = client.post("/api/config", json=payload).get_json()

    assert body["config"]["api_key"] == "real-jellyfin-key"


def test_explicit_new_secret_overrides_the_mask(client, seeded_config):
    """A genuinely new value is written through unchanged."""
    payload = client.get("/api/config").get_json()
    payload["api_key"] = "rotated-key"

    client.post("/api/config", json=payload)

    assert _read_saved(seeded_config)["api_key"] == "rotated-key"


def test_mixed_masked_and_new_secrets(client, seeded_config):
    """Each sensitive field is resolved independently."""
    payload = client.get("/api/config").get_json()
    payload["tmdb_api_key"] = "new-tmdb-key"

    client.post("/api/config", json=payload)

    saved = _read_saved(seeded_config)
    assert saved["api_key"] == "real-jellyfin-key"
    assert saved["trakt_client_id"] == "real-trakt-id"
    assert saved["tmdb_api_key"] == "new-tmdb-key"


def test_internal_helper_keys_are_not_persisted(client, seeded_config):
    """``_active_env_overrides`` is response-only and must not hit disk."""
    payload = client.get("/api/config").get_json()
    assert "_active_env_overrides" in payload

    client.post("/api/config", json=payload)

    assert "_active_env_overrides" not in _read_saved(seeded_config)


def test_mask_without_stored_file_clears_the_field(client, temp_config):
    """A mask with nothing behind it degrades to empty, never to ``"****"``."""
    payload = config._default_config_copy()
    payload["api_key"] = "****"

    client.post("/api/config", json=payload)

    assert _read_saved(temp_config)["api_key"] == ""


def test_load_stored_config_ignores_env_overrides(monkeypatch, seeded_config):
    monkeypatch.setenv("JELLYFIN_API_KEY", "env-only-key")

    stored = load_stored_config()

    assert stored["api_key"] == "real-jellyfin-key"
    # The live loader still prefers the environment.
    assert config.load_config()["api_key"] == "env-only-key"


def test_load_stored_config_returns_empty_for_missing_file(temp_config):
    temp_config.unlink(missing_ok=True)

    assert load_stored_config() == {}


def test_load_stored_config_returns_empty_for_invalid_json(temp_config):
    temp_config.write_text("{not json", encoding="utf-8")

    assert load_stored_config() == {}


def test_load_stored_config_returns_empty_for_non_object_json(temp_config):
    temp_config.write_text("[1, 2, 3]", encoding="utf-8")

    assert load_stored_config() == {}


def test_connection_test_resolves_mask_to_stored_key(
    client, seeded_config, monkeypatch
):
    """The sidebar sends the masked field; the test must still authenticate."""
    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers", {})

        class _Resp:
            status_code = 200

        return _Resp()

    monkeypatch.setattr("routes.network.get", fake_get)

    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": "http://jellyfin.local:8096", "api_key": "****"},
    )

    assert response.status_code == 200
    assert captured["headers"]["X-Emby-Token"] == "real-jellyfin-key"


def test_connection_test_still_rejects_empty_key(client, seeded_config):
    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": "http://jellyfin.local:8096", "api_key": ""},
    )

    assert response.status_code == 400
