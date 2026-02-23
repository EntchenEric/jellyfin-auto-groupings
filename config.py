"""
config.py – Configuration persistence helpers.

Handles loading and saving the application's ``config.json`` file, including
backwards-compatible key migration and first-run default creation.
"""

from __future__ import annotations

import json
import os
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR: str = os.path.join(os.path.dirname(__file__), "config")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "jellyfin_url": "",
    "api_key": "",
    "target_path": "",
    "media_path_in_jellyfin": "",
    "media_path_on_host": "",
    "trakt_client_id": "",
    "tmdb_api_key": "",
    "mal_client_id": "",
    "groups": [],
    "scheduler": {
        "global_enabled": False,
        "global_schedule": "0 0 * * *",
        "global_exclude_ids": [],
        "cleanup_enabled": True,
        "cleanup_schedule": "0 * * * *"
    }
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Load configuration from disk.

    If the config file does not exist it is created from :data:`DEFAULT_CONFIG`
    and that default dict is returned.  When loading an existing file:

    * Missing keys are filled in from :data:`DEFAULT_CONFIG` (forward-compat).
    * Legacy keys ``jellyfin_root`` / ``host_root`` are migrated to their new
      names and the updated config is persisted automatically.

    Returns:
        The (possibly migrated) configuration dictionary.
    """
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as fh:
            cfg: dict[str, Any] = json.load(fh)

        # Fill in any keys added after initial creation
        for key, default_value in DEFAULT_CONFIG.items():
            cfg.setdefault(key, default_value)
            # Ensure nested dictionaries (like scheduler) also have defaults
            if isinstance(default_value, dict) and isinstance(cfg[key], dict):
                for sub_key, sub_val in default_value.items():
                    cfg[key].setdefault(sub_key, sub_val)

        # Migrate renamed keys
        migrated = False
        if cfg.get("jellyfin_root") and not cfg.get("media_path_in_jellyfin"):
            cfg["media_path_in_jellyfin"] = cfg["jellyfin_root"]
            migrated = True
        if cfg.get("host_root") and not cfg.get("media_path_on_host"):
            cfg["media_path_on_host"] = cfg["host_root"]
            migrated = True
        if migrated:
            cfg.pop("jellyfin_root", None)
            cfg.pop("host_root", None)
            save_config(cfg)

        return cfg

    except Exception:
        # If the file is corrupt or unreadable, fall back to safe defaults
        return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    """Persist *config* to :data:`CONFIG_FILE` as pretty-printed JSON.

    Args:
        config: The configuration dictionary to write.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as fh:
        json.dump(config, fh, indent=4)
