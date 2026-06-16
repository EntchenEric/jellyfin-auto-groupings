"""Tests for configuration loading, saving, migration, and env-override logic.

Verifies default config generation, file I/O, legacy key migration,
corrupt/empty file recovery, and all environment variable overrides
(including the ``_env_flag`` helper).
"""

import json
from pathlib import Path

import pytest

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


def test_env_flag_ambiguous_value_returns_default(monkeypatch) -> None:
    """_env_flag returns default when value is not a recognized boolean."""
    from config import _env_flag

    monkeypatch.setenv("TEST_AMBIGUOUS", "maybe")
    assert _env_flag("TEST_AMBIGUOUS") is False


def test_env_flag_default_true_param(monkeypatch) -> None:
    """_env_flag respects the default parameter."""
    from config import _env_flag

    # Unset var uses the provided default
    monkeypatch.delenv("TEST_NOT_SET", raising=False)
    assert _env_flag("TEST_NOT_SET", default=True) is True


def test_env_flag_numeric_string_middle(monkeypatch) -> None:
    """_env_flag returns default for non-boolean values like '2'."""
    from config import _env_flag

    monkeypatch.setenv("TEST_MID", "2")
    assert _env_flag("TEST_MID") is False
    assert _env_flag("TEST_MID", default=True) is True


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


def test_active_env_overrides_empty(monkeypatch) -> None:
    """_active_env_overrides returns empty dict when no env vars are set."""
    from config import _active_env_overrides

    # Clear relevant env vars
    for var in ["JELLYFIN_URL", "JELLYFIN_API_KEY", "TRAKT_CLIENT_ID"]:
        monkeypatch.delenv(var, raising=False)

    result = _active_env_overrides()
    assert result == {}


def test_active_env_overrides_with_values(monkeypatch) -> None:
    """_active_env_overrides returns overrides when env vars are set."""
    from config import _active_env_overrides

    monkeypatch.setenv("JELLYFIN_API_KEY", "secret-key")
    monkeypatch.setenv("TRAKT_CLIENT_ID", "trakt-id")

    result = _active_env_overrides()
    assert "api_key" in result
    assert result["api_key"] == "JELLYFIN_API_KEY"
    assert "trakt_client_id" in result
    assert result["trakt_client_id"] == "TRAKT_CLIENT_ID"


def test_load_config_corrupt_file_backup_rename_failure(temp_config) -> None:
    """Test that corrupt config backup rename failure is handled gracefully."""
    with Path(temp_config).open("w") as f:
        f.write("this is not json{{{ ")

    # Make the config directory read-only so rename fails with OSError
    cfg_dir = Path(temp_config).parent
    # First ensure the backup path doesn't exist (so we go straight to rename)
    # and make the dir read-only
    original_mode = cfg_dir.stat().st_mode
    cfg_dir.chmod(0o555)  # read-only, no write

    try:
        cfg = load_config()
        assert cfg["jellyfin_url"] == ""
        assert cfg["groups"] == []
    finally:
        cfg_dir.chmod(original_mode)


def test_load_config_corrupt_file_backup_success(temp_config, caplog) -> None:
    """Test that corrupt config backup creates a .corrupt.bak file."""
    with Path(temp_config).open("w") as f:
        f.write("this is not json{{{ ")

    cfg = load_config()
    assert cfg["jellyfin_url"] == ""

    backup_path = Path(temp_config).with_name(Path(temp_config).name + ".corrupt.bak")
    assert backup_path.exists()


def test_load_config_corrupt_file_backup_timestamp_collision(temp_config) -> None:
    """Test that corrupt config backup uses a timestamped name when .corrupt.bak already exists."""
    with Path(temp_config).open("w") as f:
        f.write("this is not json{{{ ")

    # Pre-create the .corrupt.bak file so the collision branch is taken
    backup_path = Path(temp_config).with_name(Path(temp_config).name + ".corrupt.bak")
    backup_path.write_text("existing backup")

    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []

    # The original backup path should still exist (wasn't overwritten)
    assert backup_path.read_text() == "existing backup"
    # A timestamped backup should also exist
    ts_files = list(Path(temp_config).parent.glob("*.corrupt.*.bak"))
    assert len(ts_files) >= 1


def test_load_config_unreadable_file(temp_config, monkeypatch) -> None:
    """Test that an unreadable config file falls back to defaults."""
    with Path(temp_config).open("w") as f:
        f.write('{"jellyfin_url":"http://example.com"}')

    # Make the file unreadable
    Path(temp_config).chmod(0o000)

    try:
        cfg = load_config()
        assert cfg["jellyfin_url"] == ""
    finally:
        # Restore permissions to allow cleanup
        Path(temp_config).chmod(0o644)


def test_save_config_path_objects(tmp_path) -> None:
    """Test save_config with actual Path objects (coverage for Path(CONFIG_DIR)/Path(CONFIG_FILE) lines)."""
    import config

    # Save original module-level paths
    orig_dir = config.CONFIG_DIR
    orig_file = config.CONFIG_FILE

    try:
        test_dir = tmp_path / "cfg"
        test_file = test_dir / "config.json"
        config.CONFIG_DIR = test_dir
        config.CONFIG_FILE = test_file

        config.save_config({"key": "value"})
        assert test_file.exists()

        import json

        with test_file.open() as f:
            data = json.load(f)
        assert data["key"] == "value"
    finally:
        config.CONFIG_DIR = orig_dir
        config.CONFIG_FILE = orig_file


def test_save_config_backup_rotation(tmp_path) -> None:
    """save_config creates a timestamped .bak when a previous config exists."""
    import config

    orig_dir = config.CONFIG_DIR
    orig_file = config.CONFIG_FILE

    try:
        test_dir = tmp_path / "cfg"
        test_dir.mkdir()
        test_file = test_dir / "config.json"
        config.CONFIG_DIR = str(test_dir)
        config.CONFIG_FILE = str(test_file)

        # First save — no backup expected
        config.save_config({"version": 1})
        assert test_file.exists()

        # Second save — backup should be created
        config.save_config({"version": 2})
        assert test_file.exists()
        # Verify backup file exists
        backups = list(test_dir.glob("*.bak"))
        assert len(backups) >= 1
        # Verify current file has new content
        import json

        with test_file.open() as f:
            data = json.load(f)
        assert data["version"] == 2
    finally:
        config.CONFIG_DIR = orig_dir
        config.CONFIG_FILE = orig_file


def test_save_config_backup_rotation_cleanup_on_failure(tmp_path) -> None:
    """save_config cleans up temp file on write failure."""
    from unittest.mock import patch

    import config

    orig_dir = config.CONFIG_DIR
    orig_file = config.CONFIG_FILE

    try:
        test_dir = tmp_path / "cfg_fail"
        test_dir.mkdir()
        test_file = test_dir / "config.json"
        config.CONFIG_DIR = str(test_dir)
        config.CONFIG_FILE = str(test_file)

        # Create an existing config
        config.save_config({"version": 1})
        assert test_file.exists()

        # Mock json.dump to fail
        with (
            patch("json.dump", side_effect=OSError("write error")),
            pytest.raises(OSError, match="write error"),
        ):
            config.save_config({"version": 2})

        # Temp file should be cleaned up
        tmp_files = list(test_dir.glob("*.json.tmp"))
        assert len(tmp_files) == 0
        # Original config should still exist
        assert test_file.exists()
        with test_file.open() as f:
            import json

            data = json.load(f)
        assert data["version"] == 1
    finally:
        config.CONFIG_DIR = orig_dir
        config.CONFIG_FILE = orig_file
