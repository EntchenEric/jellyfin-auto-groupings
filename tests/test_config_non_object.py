"""``config.json`` must be a JSON object; anything else is quarantined.

``json.load`` happily returns ``[]``, ``"text"``, ``null`` or ``42`` for a
syntactically valid document.  ``load_config`` then called ``_fill_defaults``
on that value, which raised::

    TypeError: list indices must be integers or slices, not str

Only ``json.JSONDecodeError`` was handled, so every endpoint that loads the
config (including app startup and the scheduler) failed with an unhandled
exception instead of recovering with defaults.  These tests pin the recovery
path: defaults are returned, the original bytes are preserved in a
``.corrupt.bak`` file, and the caller never sees an exception.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

_NON_OBJECT_DOCUMENTS = ["[]", '"text"', "null", "42", "3.5", "true"]


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Point the config module at an isolated directory."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    return tmp_path / "config.json"


@pytest.mark.parametrize("document", _NON_OBJECT_DOCUMENTS)
def test_non_object_config_falls_back_to_defaults(temp_config, document):
    temp_config.write_text(document, encoding="utf-8")

    cfg = config.load_config()

    assert isinstance(cfg, dict)
    assert set(cfg) == set(config.DEFAULT_CONFIG)
    assert cfg["scheduler"] == config.DEFAULT_CONFIG["scheduler"]


@pytest.mark.parametrize("document", _NON_OBJECT_DOCUMENTS)
def test_non_object_config_is_quarantined_not_destroyed(temp_config, document):
    temp_config.write_text(document, encoding="utf-8")

    config.load_config()

    backup = temp_config.with_name(temp_config.name + ".corrupt.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == document
    assert not temp_config.exists()


def test_non_object_config_returns_independent_defaults(temp_config):
    temp_config.write_text("[]", encoding="utf-8")

    cfg = config.load_config()
    cfg["scheduler"]["global_enabled"] = True
    cfg["groups"].append({"name": "mutated"})

    assert config.DEFAULT_CONFIG["scheduler"]["global_enabled"] is False
    assert config.DEFAULT_CONFIG["groups"] == []


def test_empty_json_object_still_loads(temp_config):
    temp_config.write_text("{}", encoding="utf-8")

    cfg = config.load_config()

    assert cfg["target_path"] == ""
    assert cfg["groups"] == []
    # A valid object is left in place: nothing to quarantine.
    assert not temp_config.with_name(temp_config.name + ".corrupt.bak").exists()


def test_non_object_config_is_not_persisted_over(temp_config):
    """The broken document must survive untouched for the administrator."""
    temp_config.write_text('["still", "mine"]', encoding="utf-8")

    config.load_config()

    # load_config writes nothing but the quarantine copy; no fresh config.json
    # is created, so a later fix by hand is still possible from the backup.
    assert not temp_config.exists()


def test_repeated_loads_after_quarantine_create_a_fresh_config(temp_config):
    temp_config.write_text("42", encoding="utf-8")
    config.load_config()

    second = config.load_config()

    # Second call finds no config file and writes defaults, so the app keeps
    # running normally after one broken startup.
    assert second["setup_done"] is False
    assert json.loads(temp_config.read_text(encoding="utf-8"))["groups"] == []
