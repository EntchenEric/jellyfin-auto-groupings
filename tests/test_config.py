import os
import json
from config import load_config, save_config, DEFAULT_CONFIG

def test_load_config_defaults(temp_config):
    """Test that loading a non-existent config returns defaults."""
    cfg = load_config()
    assert cfg["jellyfin_url"] == ""
    assert cfg["groups"] == []
    assert os.path.exists(temp_config)

def test_save_and_load_config(temp_config):
    """Test saving and then loading configuration."""
    import copy
    new_cfg = copy.deepcopy(DEFAULT_CONFIG)
    new_cfg["jellyfin_url"] = "http://localhost:8096"
    save_config(new_cfg)
    
    loaded_cfg = load_config()
    assert loaded_cfg["jellyfin_url"] == "http://localhost:8096"

def test_config_migration(temp_config):
    """Test that legacy keys are migrated to new names."""
    legacy_cfg = {
        "jellyfin_root": "/jellyfin/path",
        "host_root": "/host/path"
    }
    with open(temp_config, "w") as f:
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
            "global_enabled": True
        }
    }
    with open(temp_config, "w") as f:
        json.dump(partial_cfg, f)
        
    cfg = load_config()
    assert cfg["scheduler"]["global_enabled"] is True
    assert cfg["scheduler"]["global_schedule"] == "0 0 * * *"
    assert cfg["scheduler"]["global_exclude_ids"] == []
