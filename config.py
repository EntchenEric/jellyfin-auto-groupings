"""config.py - Configuration persistence helpers.

Handles loading and saving the application's ``config.json`` file, including
backwards-compatible key migration and first-run default creation.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Environment-variable overrides for sensitive config keys
_ENV_OVERRIDES: dict[str, str] = {
    "api_key": "JELLYFIN_API_KEY",
    "trakt_client_id": "TRAKT_CLIENT_ID",
    "tmdb_api_key": "TMDB_API_KEY",
    "mal_client_id": "MAL_CLIENT_ID",
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parent / "config"
CONFIG_DIR: str = str(_CONFIG_PATH)
CONFIG_FILE: str = str(_CONFIG_PATH / "config.json")

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
        "cleanup_schedule": "0 * * * *",
    },
    "auto_create_libraries": False,
    "auto_set_library_covers": False,
    "target_path_in_jellyfin": "",
    "setup_done": False,
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _fill_defaults(cfg: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Fill missing keys in *cfg* from *defaults*, including nested dicts."""
    for key, default_value in defaults.items():
        cfg.setdefault(key, default_value)
        if isinstance(default_value, dict) and isinstance(cfg.get(key), dict):
            for sub_key, sub_val in default_value.items():
                cfg[key].setdefault(sub_key, sub_val)


def _migrate_legacy_keys(cfg: dict[str, Any]) -> bool:
    """Migrate legacy keys to their new names. Returns True if any changes were made."""
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
    return migrated


def load_config() -> dict[str, Any]:
    """Load configuration from disk.

    If the config file does not exist it is created from :data:`DEFAULT_CONFIG`
    and that default dict is returned.  When loading an existing file:

    * Missing keys are filled in from :data:`DEFAULT_CONFIG` (forward-compat).
    * Legacy keys ``jellyfin_root`` / ``host_root`` are migrated to their new
      names and the updated config is persisted automatically.
    * Environment variable overrides take precedence for sensitive values:
      ``JELLYFIN_API_KEY``, ``TRAKT_CLIENT_ID``, ``TMDB_API_KEY``,
      ``MAL_CLIENT_ID``.

    Returns:
        The (possibly migrated) configuration dictionary.

    """
    cfg: dict[str, Any]
    if not Path(CONFIG_FILE).exists():
        save_config(DEFAULT_CONFIG.copy())
        cfg = DEFAULT_CONFIG.copy()
    else:
        try:
            with Path(CONFIG_FILE).open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            _fill_defaults(cfg, DEFAULT_CONFIG)
            _migrate_legacy_keys(cfg)
        except (json.JSONDecodeError, OSError):
            # If the file is corrupt or unreadable, fall back to safe defaults
            logger.warning("Could not read config file, falling back to defaults", exc_info=True)
            cfg = DEFAULT_CONFIG.copy()

    # Apply environment-variable overrides (additive, never persisted)
    for cfg_key, env_var in _ENV_OVERRIDES.items():
        env_val = os.environ.get(env_var)
        if env_val:
            cfg[cfg_key] = env_val

    return cfg


def save_config(config: dict[str, Any]) -> None:
    """Persist *config* to :data:`CONFIG_FILE` as pretty-printed JSON.

    Args:
        config: The configuration dictionary to write.

    """
    Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    with Path(CONFIG_FILE).open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=4)
