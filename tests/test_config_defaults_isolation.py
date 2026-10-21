"""Regression tests for :func:`config.load_config` default isolation.

``load_config`` must never hand out a config whose nested containers alias
:data:`config.DEFAULT_CONFIG`. A shallow copy previously left the ``scheduler``
dict and the ``groups`` list shared with the module-level defaults, so any
caller that mutated the returned config (for example toggling a scheduler
flag) silently rewrote the process-wide defaults.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


def _use_temp_config(tmp_path, monkeypatch):
    """Point the config module at an isolated directory."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")


def test_first_run_config_does_not_alias_defaults(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)

    cfg = config.load_config()

    assert cfg["scheduler"] is not config.DEFAULT_CONFIG["scheduler"]
    assert cfg["groups"] is not config.DEFAULT_CONFIG["groups"]


def test_mutating_returned_config_leaves_defaults_intact(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)

    cfg = config.load_config()
    cfg["scheduler"]["global_enabled"] = True
    cfg["groups"].append({"name": "leaked"})

    assert config.DEFAULT_CONFIG["scheduler"]["global_enabled"] is False
    assert config.DEFAULT_CONFIG["groups"] == []


def test_repeated_loads_are_independent(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)

    first = config.load_config()
    first["scheduler"]["cleanup_schedule"] = "*/5 * * * *"

    second = config.load_config()

    assert second["scheduler"]["cleanup_schedule"] == "0 * * * *"


def test_corrupt_config_does_not_alias_defaults(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)
    (tmp_path / "config.json").write_text("{ not valid json", encoding="utf-8")

    cfg = config.load_config()
    cfg["scheduler"]["global_enabled"] = True

    assert cfg["scheduler"] is not config.DEFAULT_CONFIG["scheduler"]
    assert config.DEFAULT_CONFIG["scheduler"]["global_enabled"] is False


def test_saved_config_is_persisted_without_aliasing(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)

    cfg = config.load_config()
    cfg["scheduler"]["global_enabled"] = True
    config.save_config(cfg)

    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert on_disk["scheduler"]["global_enabled"] is True
    assert config.DEFAULT_CONFIG["scheduler"]["global_enabled"] is False
