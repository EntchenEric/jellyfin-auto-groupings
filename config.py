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
import re
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
    "load_stored_config",
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

#: How many timestamped ``config.json.<timestamp>.bak`` files to retain.
#: Every save rotates the previous file, so without a cap the config
#: directory grows without bound (one backup per POST /api/config).
_BACKUP_KEEP: int = 5

#: Suffix pattern of the rotation backups written by :func:`save_config`.
#: Anchored so it matches only a ``<timestamp>.bak`` tail, which deliberately
#: excludes ``.corrupt*.bak`` files — those are rare diagnostic artifacts and
#: should survive normal pruning.
_BACKUP_SUFFIX_RE: re.Pattern[str] = re.compile(r"^\d{8}_\d{6}\.bak$")

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


def _default_config_copy() -> dict[str, Any]:
    """Return a deep copy of :data:`DEFAULT_CONFIG`.

    A shallow ``dict.copy()`` would leave nested containers (the
    ``scheduler`` dict and the ``groups`` list) aliased to the module-level
    defaults, so mutating the returned config would silently corrupt
    :data:`DEFAULT_CONFIG` for the rest of the process.

    Returns:
        A new dict with independent nested containers.

    """
    return copy.deepcopy(DEFAULT_CONFIG)


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


def _quarantine_broken_config(reason: str) -> None:
    """Move an unusable ``config.json`` aside so the original survives.

    The file is renamed to ``config.json.corrupt.bak`` (or a timestamped
    variant when that name is taken).  Renaming is intentional: overwriting
    it would destroy the only copy of a hand-edited configuration after a
    typo, which is exactly the state an administrator needs to inspect.

    Failure to move the file is logged but never raised — the caller is
    already on a recovery path and must still return usable defaults.

    Args:
        reason: Human-readable description of what was wrong with the file,
            included in the log message.

    """
    cfg_path = Path(CONFIG_FILE)
    logger.warning(
        "Config file %s %s. Falling back to defaults.",
        CONFIG_FILE,
        reason,
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
        cfg = _default_config_copy()
        save_config(cfg)
    else:
        try:
            with Path(CONFIG_FILE).open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if not isinstance(cfg, dict):
                # A syntactically valid but non-object document (``[]``,
                # ``"text"``, ``null``, ``42``) parses fine, then explodes in
                # _fill_defaults with ``TypeError: list indices must be
                # integers``. Catch it here so recovery matches the invalid
                # JSON path instead of crashing every endpoint that loads
                # the config.
                _quarantine_broken_config(
                    f"is valid JSON but not an object ({type(cfg).__name__})",
                )
                cfg = _default_config_copy()
            else:
                _fill_defaults(cfg, DEFAULT_CONFIG)
                if _migrate_legacy_keys(cfg):
                    save_config(cfg)
        except json.JSONDecodeError:
            # If the file is corrupt, backup and fall back to safe defaults
            _quarantine_broken_config("contains invalid JSON")
            cfg = _default_config_copy()
        except OSError:
            # If the file is unreadable, fall back to safe defaults
            logger.warning(
                "Could not read config file %s, falling back to defaults",
                CONFIG_FILE,
                exc_info=True,
            )
            cfg = _default_config_copy()

    # Apply environment-variable overrides (additive, never persisted)
    for cfg_key, env_var in _ENV_OVERRIDES.items():
        env_val = os.environ.get(env_var)
        if env_val:
            cfg[cfg_key] = env_val

    return cfg


def load_stored_config() -> dict[str, Any]:
    """Read the persisted configuration exactly as written on disk.

    Unlike :func:`load_config`, this applies no defaults and no environment
    overrides, so callers see the literal stored values.  It is used to
    restore secret values that the frontend echoes back in masked form.

    Returns:
        The stored configuration dict, or an empty dict when the file is
        missing, unreadable, or does not contain a JSON object.

    """
    try:
        with Path(CONFIG_FILE).open("r", encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return stored if isinstance(stored, dict) else {}


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


def _prune_config_backups(cfg_dir: Path, cfg_name: str) -> None:
    """Delete the oldest rotation backups, keeping the newest few.

    Pruning is best-effort: a failure here must never abort the config save
    that triggered it, so every filesystem error is logged and swallowed.

    Args:
        cfg_dir: Directory holding the config file and its backups.
        cfg_name: File name of the config (e.g. ``"config.json"``).

    """
    prefix = f"{cfg_name}."
    try:
        backups = sorted(
            entry
            for entry in cfg_dir.iterdir()
            if entry.name.startswith(prefix)
            and _BACKUP_SUFFIX_RE.match(entry.name[len(prefix) :])
        )
    except OSError:
        logger.debug("Could not list config backups in %s", cfg_dir, exc_info=True)
        return

    # Names embed a zero-padded UTC timestamp, so lexical order is age order.
    for stale in backups[: max(0, len(backups) - _BACKUP_KEEP)]:
        with contextlib.suppress(OSError):
            stale.unlink()
            logger.debug("Pruned old config backup %s", stale)


def save_config(config: dict[str, Any]) -> None:
    """Persist *config* to :data:`CONFIG_FILE` as pretty-printed JSON.

    The write is **atomic**: content is first written to a temporary file in
    the same directory, then renamed over the target.  If a previous config
    file existed, a timestamped backup is created via ``.bak`` suffix so
    administrators can recover the last-good state.  Only the newest
    :data:`_BACKUP_KEEP` backups are kept so repeated saves cannot fill the
    config directory.

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
            _prune_config_backups(cfg_dir, cfg_file.name)
        tmp_file.rename(cfg_file)
    except Exception:
        # Clean up temp file on failure
        with contextlib.suppress(OSError):
            tmp_file.unlink(missing_ok=True)
        raise
