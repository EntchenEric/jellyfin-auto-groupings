"""Malformed ``groups`` values must not crash the endpoints that read them.

``_fill_defaults`` only replaces a stored value when the *default* is a dict,
so a hand-edited ``"groups": null`` (``42``, ``"text"``, or a list of bare
strings) survived loading untouched.  Consumers then failed on it:

* ``GET /api/health`` raised ``TypeError: object of type 'NoneType' has no
  len()`` from ``len(config.get("groups", []))``.
* ``GET /api/cleanup`` raised ``AttributeError: 'NoneType' object has no
  attribute 'get'`` from ``g.get("name")``.

Both surfaced as HTTP 500 for the whole page even though the rest of the
config was fine.  ``load_config`` now coerces list sections and drops
non-object group entries, so every caller sees the shape it assumes.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from app import app as flask_app

_MALFORMED_SECTIONS = ["null", "42", '"text"', "true", "{}"]


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Point the config module at an isolated directory."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    return tmp_path / "config.json"


@pytest.fixture
def client():
    """Flask test client for the API blueprint."""
    flask_app.config.update(TESTING=False)
    return flask_app.test_client()


@pytest.mark.parametrize("section", _MALFORMED_SECTIONS)
def test_non_list_groups_falls_back_to_empty_list(temp_config, section):
    temp_config.write_text(f'{{"groups": {section}}}', encoding="utf-8")

    cfg = config.load_config()

    assert cfg["groups"] == []


@pytest.mark.parametrize("section", _MALFORMED_SECTIONS)
def test_non_list_groups_does_not_persist_the_bad_value(temp_config, section):
    temp_config.write_text(f'{{"groups": {section}}}', encoding="utf-8")

    config.load_config()

    # The in-memory value is corrected, but a plain load must not rewrite the
    # file: a malformed section is repaired on read rather than silently
    # destroyed on disk, so the administrator's file stays inspectable.
    stored = json.loads(temp_config.read_text(encoding="utf-8"))
    assert stored["groups"] == json.loads(section)


def test_non_object_group_entries_are_dropped(temp_config):
    temp_config.write_text(
        json.dumps({"groups": ["Action", None, 42, {"name": "Drama"}]}),
        encoding="utf-8",
    )

    cfg = config.load_config()

    assert cfg["groups"] == [{"name": "Drama"}]


def test_valid_groups_are_preserved_in_order(temp_config):
    groups = [{"name": "Zeta"}, {"name": "Alpha"}, {"name": "Mid"}]
    temp_config.write_text(json.dumps({"groups": groups}), encoding="utf-8")

    assert config.load_config()["groups"] == groups


@pytest.mark.parametrize("section", _MALFORMED_SECTIONS)
def test_health_reports_zero_groups_instead_of_500(temp_config, client, section):
    temp_config.write_text(f'{{"groups": {section}}}', encoding="utf-8")

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["healthcheck"]["groups"] == 0


def test_health_counts_only_object_entries(temp_config, client):
    temp_config.write_text(
        json.dumps({"groups": [None, {"name": "A"}, "junk"]}),
        encoding="utf-8",
    )

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["healthcheck"]["groups"] == 1


def test_cleanup_ignores_malformed_group_entries(temp_config, client, tmp_path):
    target = tmp_path / "library"
    target.mkdir()
    (target / "Action").mkdir()
    temp_config.write_text(
        json.dumps(
            {"target_path": str(target), "groups": [None, 42, {"name": "Action"}]},
        ),
        encoding="utf-8",
    )

    response = client.get("/api/cleanup")

    assert response.status_code == 200
    items = response.get_json()["items"]
    assert items == [{"name": "Action", "is_configured": True}]
