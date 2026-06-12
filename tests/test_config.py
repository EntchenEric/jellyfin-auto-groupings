"""Tests for configuration loading, saving, migration, and env-override logic.

Verifies default config generation, file I/O, legacy key migration,
corrupt/empty file recovery, and all environment variable overrides
(including the ``_env_flag`` helper).
"""

import json
from pathlib import Path

from config import DEFAULT_CONFIG, load_config, save_config

TEST_URL = "http://localhost:8096"


def test_load_config_defaults(temp_config) -> None:
    """Test that loading a non-existent config returns defaults."""
    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []
    assert Path(temp_config).exists()


def test_save_and_load_config(temp_config) -> None:
    """Test saving and then loading configuration."""
    import copy

    new_cfg = copy.deepcopy(DEFAULT_CONFIG)
    new_cfg["jellyfin_url"] = TEST_URL
    save_config(new_cfg)

    loaded_cfg = load_config()
    assert loaded_cfg["jellyfin_url"] == TEST_URL


def test_config_migration(temp_config) -> None:
    """Test that legacy keys are migrated to new names."""
    legacy_cfg = {
        "jellyfin_root": "/jellyfin/path",
        "host_root": "/host/path",
    }
    with Path(temp_config).open("w") as f:
        json.dump(legacy_cfg, f)

    cfg = load_config()
    assert cfg["media_path_in_jellyfin"] == "/jellyfin/path"
    assert cfg["media_path_on_host"] == "/host/path"
    assert "jellyfin_root" not in cfg
    assert "host_root" not in cfg


def test_nested_defaults(temp_config) -> None:
    """Test that nested keys gain defaults if missing."""
    partial_cfg = {
        "scheduler": {
            "global_enabled": True,
        },
    }
    with Path(temp_config).open("w") as f:
        json.dump(partial_cfg, f)

    cfg = load_config()
    assert cfg["scheduler"]["global_enabled"] is True
    assert cfg["scheduler"]["global_schedule"] == "0 0 * * *"
    assert cfg["scheduler"]["global_exclude_ids"] == []


# ---------------------------------------------------------------------------
# config.py edge cases
# ---------------------------------------------------------------------------


def test_load_config_corrupt_file(temp_config) -> None:
    """Test that a corrupt config file falls back to defaults."""
    with Path(temp_config).open("w") as f:
        f.write("this is not json{{{")

    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []


def test_load_config_env_override(temp_config, monkeypatch) -> None:
    """Test that environment variables override config values."""
    monkeypatch.setenv("JELLYFIN_API_KEY", "env_api_key")
    cfg = load_config()
    assert cfg["api_key"] == "env_api_key"


def test_load_config_anilist_url_env_override(temp_config, monkeypatch) -> None:
    """Test that ANILIST_API_URL environment variable overrides config."""
    monkeypatch.setenv("ANILIST_API_URL", "https://custom.anilist.example/graphql")
    cfg = load_config()
    assert cfg["anilist_api_url"] == "https://custom.anilist.example/graphql"


def test_load_config_empty_file(temp_config) -> None:
    """Test that an empty config file falls back to defaults."""
    with Path(temp_config).open("w") as f:
        f.write("")

    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []


def test_load_config_all_env_overrides(temp_config, monkeypatch) -> None:
    """Test all environment variable overrides take effect."""
    monkeypatch.setenv("JELLYFIN_API_KEY", "env_api_key")
    monkeypatch.setenv("TRAKT_CLIENT_ID", "env_trakt")
    monkeypatch.setenv("TMDB_API_KEY", "env_tmdb")
    monkeypatch.setenv("MAL_CLIENT_ID", "env_mal")
    monkeypatch.setenv("ANILIST_API_URL", "https://env.anilist/graphql")
    cfg = load_config()
    assert cfg["api_key"] == "env_api_key"
    assert cfg["trakt_client_id"] == "env_trakt"
    assert cfg["tmdb_api_key"] == "env_tmdb"
    assert cfg["mal_client_id"] == "env_mal"
    assert cfg["anilist_api_url"] == "https://env.anilist/graphql"


def test_save_config_backup_handling(temp_config) -> None:
    """Test that save_config writes valid JSON that can be re-loaded."""
    cfg = {
        "jellyfin_url": "http://example.com",
        "api_key": "test",
        "target_path": "/tmp/test",
        "groups": [
            {
                "name": "Test Group",
                "type": "genre",
                "value": "Action",
            },
        ],
    }
    save_config(cfg)
    with Path(temp_config).open("r") as f:
        loaded = json.load(f)
    assert loaded["jellyfin_url"] == "http://example.com"
    assert len(loaded["groups"]) == 1
    assert loaded["groups"][0]["name"] == "Test Group"


def test_config_no_migration_needed(temp_config) -> None:
    """Test that loading a config with modern keys doesn't apply migration."""
    cfg = {
        "media_path_in_jellyfin": "/jellyfin/media",
        "media_path_on_host": "/host/media",
        "jellyfin_root": "/legacy/path",  # legacy key exists but migration already happened
        "host_root": "/legacy/host",
    }
    with Path(temp_config).open("w") as f:
        json.dump(cfg, f)

    result = load_config()
    # Modern keys should be kept
    assert result["media_path_in_jellyfin"] == "/jellyfin/media"
    assert result["media_path_on_host"] == "/host/media"


def test_env_flag_default() -> None:
    """_env_flag returns False when the env var is not set."""
    from config import _env_flag

    assert _env_flag("THIS_VAR_SHOULD_NOT_EXIST_12345") is False


def test_env_flag_true(monkeypatch) -> None:
    """_env_flag returns True for "true"."""
    from config import _env_flag

    monkeypatch.setenv("TEST_ENV_FLAG", "true")
    assert _env_flag("TEST_ENV_FLAG") is True


def test_env_flag_case_insensitive(monkeypatch) -> None:
    """_env_flag treats "True", "TRUE", "Yes" as truthy."""
    from config import _env_flag

    monkeypatch.setenv("TEST_ENV_FLAG_2", "TRUE")
    assert _env_flag("TEST_ENV_FLAG_2") is True

    monkeypatch.setenv("TEST_ENV_FLAG_3", "Yes")
    assert _env_flag("TEST_ENV_FLAG_3") is True

    monkeypatch.setenv("TEST_ENV_FLAG_4", "1")
    assert _env_flag("TEST_ENV_FLAG_4") is True


def test_env_flag_false_values(monkeypatch) -> None:
    """_env_flag returns False for falsy values."""
    from config import _env_flag

    monkeypatch.setenv("TEST_ENV_FLAG_5", "false")
    assert _env_flag("TEST_ENV_FLAG_5") is False

    monkeypatch.setenv("TEST_ENV_FLAG_6", "0")
    assert _env_flag("TEST_ENV_FLAG_6") is False

    monkeypatch.setenv("TEST_ENV_FLAG_7", "no")
    assert _env_flag("TEST_ENV_FLAG_7") is False

    monkeypatch.setenv("TEST_ENV_FLAG_8", "")
    assert _env_flag("TEST_ENV_FLAG_8") is False


def test_load_config_corrupt_file_backup_rename_failure(temp_config) -> None:
    """Test that corrupt config backup rename failure is handled gracefully."""
    with Path(temp_config).open("w") as f:
        f.write("this is not json{{{ ")

    # Prevent rename by making the backup path collide with a directory
    backup_path = Path(temp_config).with_suffix(".corrupt.bak")
    backup_path.mkdir()

    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []


def test_load_config_corrupt_file_backup_success(temp_config, caplog) -> None:
    """Test that corrupt config backup creates a .corrupt.bak file."""

    with Path(temp_config).open("w") as f:
        f.write("this is not json{{{ ")

    cfg = load_config()
    assert cfg["jellyfin_url"] == ""

    backup_path = Path(temp_config).with_suffix(".corrupt.bak")
    assert backup_path.exists()


def test_load_config_unreadable_file(temp_config, monkeypatch) -> None:
    """Test that an unreadable config file falls back to defaults."""
    with Path(temp_config).open("w") as f:
        f.write("{\"jellyfin_url\":\"http://example.com\"}")

    # Make the file unreadable
    Path(temp_config).chmod(0o000)

    try:
        cfg = load_config()
        assert cfg["jellyfin_url"] == ""
    finally:
        # Restore permissions to allow cleanup
        Path(temp_config).chmod(0o644)
