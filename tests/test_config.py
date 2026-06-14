import json
from pathlib import Path

from config import DEFAULT_CONFIG, load_config, save_config

TEST_URL = "http://localhost:8096"


def test_load_config_defaults(temp_config):
    """Test that loading a non-existent config returns defaults."""
    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []
    assert Path(temp_config).exists()


def test_save_and_load_config(temp_config):
    """Test saving and then loading configuration."""
    import copy

    new_cfg = copy.deepcopy(DEFAULT_CONFIG)
    new_cfg["jellyfin_url"] = TEST_URL
    save_config(new_cfg)

    loaded_cfg = load_config()
    assert loaded_cfg["jellyfin_url"] == TEST_URL


def test_config_migration(temp_config):
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


def test_nested_defaults(temp_config):
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


def test_load_config_corrupt_file(temp_config):
    """Test that a corrupt config file falls back to defaults."""
    with Path(temp_config).open("w") as f:
        f.write("this is not json{{{")

    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []


def test_load_config_env_override(temp_config, monkeypatch):
    """Test that environment variables override config values."""
    monkeypatch.setenv("JELLYFIN_API_KEY", "env_api_key")
    cfg = load_config()
    assert cfg["api_key"] == "env_api_key"


def test_env_flag():
    from config import _env_flag

    assert _env_flag("MISSING_VAR", default=True) is True
    assert _env_flag("MISSING_VAR", default=False) is False


def test_load_config_oserror_on_read(temp_config):
    import stat

    config_path = Path(temp_config)
    with config_path.open("w") as f:
        json.dump({"jellyfin_url": "http://test"}, f)
    config_path.chmod(0)
    try:
        cfg = load_config()
    finally:
        config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert cfg["jellyfin_url"] == ""


def test_load_config_corrupt_backup_oserror(temp_config, monkeypatch):
    with Path(temp_config).open("w") as f:
        f.write("{bad json")

    def fail_copy(*_args, **_kwargs):
        msg = "backup failed"
        raise OSError(msg)

    monkeypatch.setattr("config.shutil.copy2", fail_copy)
    cfg = load_config()
    assert cfg["groups"] == []


def test_save_config_cleans_temp_on_failure(temp_config, monkeypatch):
    def fail_replace(self, _target):
        msg = "replace failed"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", fail_replace)
    tmp = Path(temp_config).with_suffix(".json.tmp")
    try:
        import pytest

        with pytest.raises(OSError):
            save_config({"jellyfin_url": TEST_URL, "groups": []})
    finally:
        assert not tmp.exists()
