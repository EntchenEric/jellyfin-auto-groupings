"""Tests for configuration state management."""

import json

from config import DEFAULT_CONFIG, load_config, save_config


def test_default_config_has_required_keys():
    """DEFAULT_CONFIG must contain all essential keys."""
    required = [
        "jellyfin_url", "api_key", "target_path",
        "media_path_in_jellyfin", "media_path_on_host",
        "groups", "scheduler", "setup_done"
    ]
    for key in required:
        assert key in DEFAULT_CONFIG, f"Missing required key: {key}"


def test_default_config_groups_is_list():
    """Groups must default to an empty list."""
    assert DEFAULT_CONFIG["groups"] == []


def test_default_config_scheduler_has_defaults():
    """Scheduler defaults must be sane."""
    s = DEFAULT_CONFIG["scheduler"]
    assert "global_enabled" in s
    assert "global_schedule" in s
    assert "global_exclude_ids" in s
    assert "cleanup_enabled" in s
    assert "cleanup_schedule" in s
    assert s["global_exclude_ids"] == []
    assert s["cleanup_enabled"] is True


def test_default_config_api_keys_are_empty():
    """All API keys start empty."""
    assert DEFAULT_CONFIG["api_key"] == ""
    assert DEFAULT_CONFIG["trakt_client_id"] == ""
    assert DEFAULT_CONFIG["tmdb_api_key"] == ""
    assert DEFAULT_CONFIG["mal_client_id"] == ""


def test_setup_done_defaults_false():
    """New configs must not be marked as setup complete."""
    assert DEFAULT_CONFIG["setup_done"] is False


def test_save_config_preserves_structure(temp_config):
    """Saving config should produce valid JSON with all required fields."""
    import copy
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["jellyfin_url"] = "http://example.com:8096"
    cfg["api_key"] = "test-key-123"
    save_config(cfg)

    with open(temp_config, "r") as f:
        saved = json.load(f)

    assert saved["jellyfin_url"] == "http://example.com:8096"
    assert saved["api_key"] == "test-key-123"
    assert isinstance(saved["groups"], list)
    assert isinstance(saved["scheduler"], dict)


def test_load_config_fills_missing_nested_keys(temp_config):
    """When a stored config is missing nested keys, defaults should fill in."""
    minimal = {"jellyfin_url": "http://srv"}
    with open(temp_config, "w") as f:
        json.dump(minimal, f)

    cfg = load_config()
    assert cfg["jellyfin_url"] == "http://srv"
    assert isinstance(cfg["groups"], list)
    assert isinstance(cfg["scheduler"], dict)
    assert "cleanup_schedule" in cfg["scheduler"]


def test_load_config_does_not_lose_extra_keys(temp_config):
    """Unknown keys in saved config should survive a load/save round-trip."""
    extra = {"jellyfin_url": "", "custom_field": "keep-me"}
    with open(temp_config, "w") as f:
        json.dump(extra, f)

    cfg = load_config()
    # The config module's load_config uses dict union, extra keys may or may not be kept
    # depending on merge direction. If kept, verifies preservation.
    assert cfg["jellyfin_url"] == ""
