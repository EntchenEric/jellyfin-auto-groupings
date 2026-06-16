"""config.py - Configuration persistence helpers.

Handles loading and saving the application's ``config.json`` file, including
backwards-compatible key migration and first-run default creation.
"""

from __future__ import annotations

import contextlib
import copy
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DEFAULT_CONFIG",
    "_ENV_TO_CONFIG",
    "_active_env_overrides",
    "load_config",
    "save_config",
]

# Environment-variable overrides for sensitive config keys.
# Maps config key -> environment variable name.
_ENV_OVERRIDES: dict[str, str] = {
    "api_key": "JELLYFIN_API_KEY",
    "trakt_client_id": "TRAKT_CLIENT_ID",
    "tmdb_api_key": "TMDB_API_KEY",
    "mal_client_id": "MAL_CLIENT_ID",
    "anilist_api_url": "ANILIST_API_URL",
}

# Inverse mapping: env var name -> config key, used to report which
# values are being overridden at runtime.
_ENV_TO_CONFIG: dict[str, str] = {v: k for k, v in _ENV_OVERRIDES.items()}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parent / "config"
CONFIG_DIR: Path = _CONFIG_PATH
CONFIG_FILE: Path = _CONFIG_PATH / "config.json"

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
    "anilist_api_url": "",
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


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Parse an environment variable as a boolean flag.

    Accepts ``"true"``, ``"1"``, ``"yes"`` (case-insensitive) as truthy.
    Accepts ``"false"``, ``"0"``, ``"no"`` (case-insensitive) as falsy.
    If the variable is unset or empty, return *default*.
    All other values return *default*.


    Args:
        name: The environment variable name.
        default: Default value if the var is unset or empty.

    """
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    return default


def _fill_defaults(cfg: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Fill missing keys in *cfg* from *defaults*, recursing into nested dicts.

    Recursively walks *defaults* so that deeply nested structures (e.g.
    scheduler config with arbitrary sub-keys) are properly populated without
    requiring the caller to specify every intermediate level.


    Args:
            cfg: The configuration dict.
            defaults: Default values dict.

    """
    for key, default_value in defaults.items():
        if key not in cfg:
            # Deep-copy to prevent runtime mutations of cfg from aliasing
            # the DEFAULT_CONFIG object (via setdefault).
            cfg[key] = copy.deepcopy(default_value)
        elif isinstance(default_value, dict):
            current = cfg[key]
            if isinstance(current, dict):
                _fill_defaults(current, default_value)
            else:
                # Value exists but is not a dict (or is None) — replace with
                # a deep copy to avoid AttributeError downstream.
                cfg[key] = copy.deepcopy(default_value)


def _migrate_legacy_keys(cfg: dict[str, Any]) -> bool:
    """Migrate legacy keys to their new names. Returns True if any changes were made.

    The caller is responsible for persisting changes when this returns True.


    Args:
            cfg: The configuration dict.

    """
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
      ``MAL_CLIENT_ID``, ``ANILIST_API_URL``.

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
            if _migrate_legacy_keys(cfg):
                save_config(cfg)
        except json.JSONDecodeError:
            # If the file is corrupt, backup and fall back to safe defaults
            cfg_path = Path(CONFIG_FILE)
            logger.warning(
                "Config file %s contains invalid JSON. Falling back to defaults.",
                CONFIG_FILE,
            )
            backup_path = cfg_path.with_name(cfg_path.name + ".corrupt.bak")
            try:
                if backup_path.exists():
                    # Avoid collision by appending a timestamp
                    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
                    backup_path = cfg_path.with_name(
                        cfg_path.name + f".corrupt.{timestamp}.bak",
                    )
                cfg_path.rename(backup_path)
                logger.info("Backed up corrupt config to %s", backup_path)
            except OSError:
                logger.exception(
                    "Failed to backup corrupt config to %s (backup existed: %s)",
                    backup_path,
                    backup_path.exists(),
                )
            cfg = DEFAULT_CONFIG.copy()
        except OSError:
            # If the file is unreadable, fall back to safe defaults
            logger.warning(
                "Could not read config file %s, falling back to defaults",
                CONFIG_FILE,
                exc_info=True,
            )
            cfg = DEFAULT_CONFIG.copy()

    # Apply environment-variable overrides (additive, never persisted)
    for cfg_key, env_var in _ENV_OVERRIDES.items():
        env_val = os.environ.get(env_var)
        if env_val:
            cfg[cfg_key] = env_val

    return cfg


def _active_env_overrides() -> dict[str, str]:
    """Return config keys overridden by environment variables.

    Returns a dict like ``{"api_key": "JELLYFIN_API_KEY", ...}`` for any
    environment variable that is currently set, regardless of whether the
    value differs from the saved config.
    """
    overrides: dict[str, str] = {}
    for cfg_key, env_var in _ENV_OVERRIDES.items():
        env_val = os.environ.get(env_var)
        if env_val:
            overrides[cfg_key] = env_var
    return overrides


def save_config(config: dict[str, Any]) -> None:
    """Persist *config* to :data:`CONFIG_FILE` as pretty-printed JSON.

    The write is **atomic**: content is first written to a temporary file in
    the same directory, then renamed over the target.  If a previous config
    file existed, a timestamped backup is created via ``.bak`` suffix so
    administrators can recover the last-good state.

    Args:
        config: The configuration dictionary to write.

    """
    cfg_dir = Path(CONFIG_DIR)
    cfg_file = Path(CONFIG_FILE)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    # Atomic write via temp file first, then rotate existing + rename
    tmp_file = cfg_file.with_suffix(".json.tmp")
    try:
        with tmp_file.open("w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=4)
        # Write succeeded — now rotate the existing config and atomically replace
        if cfg_file.exists():
            backup_name = (
                cfg_file.name + f".{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}.bak"
            )
            backup_path = cfg_dir / backup_name
            cfg_file.rename(backup_path)
            logger.debug("Backed up previous config to %s", backup_path)
        tmp_file.rename(cfg_file)
    except Exception:
        # Clean up temp file on failure
        with contextlib.suppress(OSError):
            tmp_file.unlink(missing_ok=True)
        raise
