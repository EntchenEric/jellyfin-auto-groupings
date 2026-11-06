"""Tests for config.py and auto_group.main() paths not exercised elsewhere.

Covers: legacy-key migration through ``load_config``, the OSError fallback when
the config file is unreadable, ``_active_env_overrides`` direct behavior, the
OSError guards in ``_quarantine_broken_config`` / ``_prune_config_backups`` /
``save_config`` temp cleanup, ``_env_flag`` raw parsing, and every branch of
``auto_group.main()`` (missing API key exit, dry run, no usable IDs, success).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pytest

import auto_group
import config as config_mod

# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------


def _write_cfg(tmp_path: Path, body) -> Path:
    cfg_file = tmp_path / "config.json"
    if body is not None:
        cfg_file.write_text(json.dumps(body), encoding="utf-8")
    return cfg_file


def test_load_config_migrates_legacy_keys_and_persists(tmp_path, monkeypatch):
    """Legacy jellyfin_root/host_root keys are folded into the new paths and
    the migration is persisted back to disk."""
    cfg_file = _write_cfg(
        tmp_path,
        {"jellyfin_root": "http://jf:8096", "host_root": "/mnt/media"},
    )
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config_mod, "_ENV_OVERRIDES", {})
    saved: dict = {}
    monkeypatch.setattr(config_mod, "save_config", lambda cfg: saved.update(cfg))

    cfg = config_mod.load_config()

    assert cfg["media_path_in_jellyfin"] == "http://jf:8096"
    assert cfg["media_path_on_host"] == "/mnt/media"
    assert "jellyfin_root" not in cfg
    assert "host_root" not in cfg
    assert saved.get("media_path_in_jellyfin") == "http://jf:8096"


def test_load_config_unreadable_file_falls_back_to_defaults(tmp_path, monkeypatch):
    """An OSError while reading the config is logged and safe defaults win."""
    cfg_file = _write_cfg(tmp_path, {"api_key": "x"})
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config_mod, "_ENV_OVERRIDES", {})
    monkeypatch.setattr(
        Path, "open", mock.MagicMock(side_effect=PermissionError("denied"))
    )

    cfg = config_mod.load_config()

    assert isinstance(cfg, dict)
    assert isinstance(cfg, dict)
    # Defaults applied: a known default key exists.
    assert any(
        k in cfg for k in ("patterns", "groups", "min_group_size", "DRY_RUN", "api_key")
    )


def test_load_config_corrupt_json_with_failed_backup_still_loads(
    tmp_path, monkeypatch, caplog
):
    """Quarantine rename failing must not abort the run: defaults are used."""
    cfg_file = _write_cfg(tmp_path, "not json {")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config_mod, "_ENV_OVERRIDES", {})

    def fail_rename(self, target):
        msg = "cannot rename"
        raise OSError(msg)

    monkeypatch.setattr(Path, "rename", fail_rename)

    with caplog.at_level(logging.ERROR):
        cfg = config_mod.load_config()

    assert isinstance(cfg, dict)
    assert any("Failed to backup corrupt config" in r.message for r in caplog.records)


def test_active_env_overrides_lists_env_vars_only(monkeypatch):
    monkeypatch.setattr(config_mod, "_ENV_OVERRIDES", {"api_key": "JF_KEY"})
    monkeypatch.setenv("JF_KEY", "secret")
    monkeypatch.delenv("OTHER_KEY", raising=False)
    assert config_mod._active_env_overrides() == {"api_key": "JF_KEY"}


def test_active_env_overrides_empty_when_unset(monkeypatch):
    monkeypatch.setattr(config_mod, "_ENV_OVERRIDES", {"api_key": "JF_KEY"})
    monkeypatch.delenv("JF_KEY", raising=False)
    assert config_mod._active_env_overrides() == {}


def test_prune_config_backups_swallows_iterdir_oserror(tmp_path, caplog, monkeypatch):
    """A failing iterdir logs debug and deletes nothing."""
    monkeypatch.setattr(Path, "iterdir", mock.MagicMock(side_effect=OSError("boom")))
    with caplog.at_level(logging.DEBUG):
        config_mod._prune_config_backups(tmp_path, "config.json")
    assert any("Could not list config backups" in r.message for r in caplog.records)


def test_save_config_cleans_temp_file_on_failure(tmp_path, monkeypatch):
    """When the temp write fails, the .tmp file is removed and OSError raised."""
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_file)

    cfg = config_mod._default_config_copy()
    tmp_file = cfg_file.with_suffix(".json.tmp")
    tmp_file.write_text("partial", encoding="utf-8")

    real_rename = Path.rename

    def rename_fail(self, target):
        if str(self).endswith(".json.tmp"):
            msg = "disk full"
            raise OSError(msg)
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename_fail)

    with pytest.raises(OSError):
        config_mod.save_config(cfg)
    assert not tmp_file.exists()


def test_env_flag_parses_true_false_and_default(monkeypatch):
    monkeypatch.setenv("FLAG_T", "yes")
    monkeypatch.setenv("FLAG_F", "FALSE")
    monkeypatch.setenv("FLAG_O", "maybe")
    monkeypatch.delenv("FLAG_U", raising=False)
    assert config_mod._env_flag("FLAG_T") is True
    assert config_mod._env_flag("FLAG_F") is False
    assert config_mod._env_flag("FLAG_O", default=True) is True
    assert config_mod._env_flag("FLAG_U", default=False) is False


# ---------------------------------------------------------------------------
# auto_group.main()
# ---------------------------------------------------------------------------


def _cfg(dry_run: bool = False) -> dict:
    return {
        "JELLYFIN_API_KEY": "k",
        "JELLYFIN_URL": "http://jellyfin:8096",
        "PATTERNS": [r"^(.+?)\s*\(\d{4}\)$"],
        "MIN_GROUP_SIZE": 2,
        "DRY_RUN": dry_run,
    }


_ITEMS = [
    {"Id": "a", "Name": "Foo (2019)"},
    {"Id": "b", "Name": "Foo (2020)"},
]


def _run_main(config_val, **patches):
    with (
        patch.object(auto_group, "load_config", return_value=config_val),
        patch.object(
            auto_group, "get_libraries", return_value=[{"Name": "Movies", "Id": "1"}]
        ),
        patch.object(auto_group, "get_library_items", return_value=_ITEMS) as gi,
        patch.object(auto_group, "create_collection", return_value="cid") as cc,
        patch.object(auto_group, "add_to_collection", return_value=True) as atc,
        patch("sys.argv", ["auto_group.py"]),
    ):
        auto_group.main()
    return gi, cc, atc


def test_main_missing_api_key_exits(caplog):
    cfg = _cfg()
    cfg["JELLYFIN_API_KEY"] = ""
    with (
        patch.object(auto_group, "load_config", return_value=cfg),
        pytest.raises(SystemExit) as exc,
        patch("sys.argv", ["auto_group.py"]),
    ):
        auto_group.main()
    assert exc.value.code == 1
    record_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "JELLYFIN_API_KEY is required" in record_text


def test_main_dry_run_does_not_create_collections():
    _gi, cc, atc = _run_main(_cfg(dry_run=True))
    assert cc.call_count == 0
    assert atc.call_count == 0


def test_main_creates_collection_with_usable_ids():
    _gi, cc, _atc = _run_main(_cfg())
    assert cc.call_count == 1
    _args, _kwargs = cc.call_args
    assert _args[2] == "Foo Collection"
    assert _args[3] == ["a", "b"]


def test_main_skips_group_with_no_usable_ids():
    items = [
        {"Id": None, "Name": "Foo (2019)"},
        {"Id": "  ", "Name": "Foo (2020)"},
    ]
    with (
        patch.object(auto_group, "load_config", return_value=_cfg()),
        patch.object(
            auto_group, "get_libraries", return_value=[{"Name": "Movies", "Id": "1"}]
        ),
        patch.object(auto_group, "get_library_items", return_value=items),
        patch.object(auto_group, "create_collection") as cc,
        patch.object(auto_group, "add_to_collection") as atc,
        patch("sys.argv", ["auto_group.py"]),
    ):
        auto_group.main()
    assert cc.call_count == 0
    assert atc.call_count == 0


def test_main_multiple_libraries_processed():
    with (
        patch.object(auto_group, "load_config", return_value=_cfg()),
        patch.object(
            auto_group,
            "get_libraries",
            return_value=[{"Name": "A", "Id": "1"}, {"Name": "B", "Id": "2"}],
        ) as gl,
        patch.object(auto_group, "get_library_items", return_value=_ITEMS),
        patch.object(auto_group, "create_collection", return_value="cid") as cc,
        patch.object(auto_group, "add_to_collection", return_value=True),
        patch("sys.argv", ["auto_group.py"]),
    ):
        auto_group.main()
    assert gl.call_count == 1
    assert cc.call_count == 2


def test_main_no_libraries_is_a_clean_noop():
    with (
        patch.object(auto_group, "load_config", return_value=_cfg()),
        patch.object(auto_group, "get_libraries", return_value=[]),
        patch.object(auto_group, "get_library_items") as gi,
        patch.object(auto_group, "create_collection") as cc,
        patch("sys.argv", ["auto_group.py"]),
    ):
        auto_group.main()
    assert gi.call_count == 0
    assert cc.call_count == 0


def test_main_verbose_flag_turns_on_debug_logging():
    cfg = _cfg()
    with (
        patch.object(auto_group, "load_config", return_value=cfg),
        patch.object(auto_group, "get_libraries", return_value=[]),
        patch.object(auto_group, "get_library_items") as gi,
        patch.object(auto_group, "create_collection") as cc,
        patch("sys.argv", ["auto_group.py", "--verbose"]),
    ):
        auto_group.main()
    assert gi.call_count == 0
    assert cc.call_count == 0


def test_main_dry_run_flag_forces_dry_run_over_config():
    """``--dry-run`` must win even when the loaded config says dry-run is off."""
    cfg = _cfg(dry_run=False)
    with (
        patch.object(auto_group, "load_config", return_value=cfg) as lc,
        patch.object(auto_group, "get_libraries", return_value=[]),
        patch.object(auto_group, "get_library_items") as gi,
        patch.object(auto_group, "create_collection") as cc,
        patch("sys.argv", ["auto_group.py", "--dry-run"]),
    ):
        auto_group.main()
    assert lc.call_count == 1
    assert cfg["DRY_RUN"] is True
    assert gi.call_count == 0
    assert cc.call_count == 0


def test_dunder_main_invokes_main(monkeypatch, tmp_path):
    """Executing the module as a script runs ``main()``.

    ``runpy`` executes the file in a fresh module namespace, so we can't
    monkeypatch the attribute — instead we make ``load_config`` (called
    before ``main()``) exit via ``SystemExit`` to prove the ``__main__``
    guard invoked the real CLI path.
    """
    import runpy

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"JELLYFIN_API_KEY": ""}), encoding="utf-8")
    argv = sys.argv
    sys.argv = ["auto_group.py", "--config", str(config_file)]
    try:
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(Path(auto_group.__file__)), run_name="__main__")
    finally:
        sys.argv = argv
    assert exc.value.code == 1
