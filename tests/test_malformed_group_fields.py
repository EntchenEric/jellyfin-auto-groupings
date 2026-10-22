"""Regression tests for malformed per-group and preview request fields.

``config.json`` is user-editable and every ``/api`` body is client-controlled,
so a field the web form always writes as a string can hold a number, a list or
an object.  Two paths turned that into an HTTP 500 instead of a validation
error:

* ``POST /api/grouping/preview`` called ``.strip()`` on ``watch_state`` and
  ``item_type`` straight from the JSON body, and on ``anilist_api_url`` from a
  hand-edited config.
* ``run_sync`` called ``.strip()`` on ``groups[].name`` and passed
  ``sort_order`` / ``source_type`` into dict and set lookups.  A list there
  raised ``TypeError: unhashable type: 'list'``, which aborted the whole run —
  one bad entry stopped every other group from syncing.

Both now degrade to a 400 or a per-group error while the rest of the request
or run still succeeds.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import sync
from app import app as flask_app

_CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client whose config is isolated to *tmp_path*."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    # Every request in this module posts a JSON body, so CSRF must not be the
    # reason a request is rejected; the assertions are about field handling.
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as test_client:
        yield test_client


def _preview(client, **fields):
    body = {"type": "genre", "value": "Action", **fields}
    return client.post(
        "/api/grouping/preview",
        data=json.dumps(body),
        content_type="application/json",
        headers=_CSRF_HEADERS,
    )


@pytest.fixture
def stubbed_preview(monkeypatch):
    """Replace the Jellyfin lookups so the route's own validation is exercised."""
    import routes

    monkeypatch.setattr(routes, "_get_jellyfin_config", lambda: ("http://jf", "key"))
    captured: list[dict[str, object]] = []

    def _fake_preview(*args, **kwargs):
        captured.append({"args": args, "kwargs": kwargs})
        return ([{"Name": "Example", "ProductionYear": 2000}], None, 200)

    monkeypatch.setattr(routes, "preview_group", _fake_preview)
    return captured


@pytest.mark.parametrize("field", ["watch_state", "item_type"])
@pytest.mark.parametrize(
    "bad_value", [42, 4.5, True, ["watched"], {"state": "watched"}]
)
def test_non_string_preview_filter_is_a_400(client, stubbed_preview, field, bad_value):
    response = _preview(client, **{field: bad_value})

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"
    assert field in response.get_json()["message"]
    assert stubbed_preview == []


@pytest.mark.parametrize("field", ["watch_state", "item_type"])
def test_preview_null_filter_is_treated_as_absent(client, stubbed_preview, field):
    response = _preview(client, **{field: None})

    assert response.status_code == 200
    assert len(stubbed_preview) == 1


def test_preview_filters_are_trimmed_and_lowercased(client, stubbed_preview):
    response = _preview(client, watch_state="  WATCHED ", item_type=" Movies ")

    assert response.status_code == 200
    kwargs = stubbed_preview[0]["kwargs"]
    # ``watch_state`` is passed positionally to ``preview_group``; ``item_type``
    # is keyword-only in practice, so assert both shapes.
    assert stubbed_preview[0]["args"][4] == "watched"
    assert kwargs["item_type"] == "movies"


def test_preview_ignores_non_string_anilist_url_in_config(
    client, tmp_path, stubbed_preview
):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"anilist_api_url": 42}), encoding="utf-8")

    response = _preview(client, type="anilist_list")

    assert response.status_code == 200
    assert stubbed_preview[0]["kwargs"]["anilist_api_url"] is None


def _sync_config(tmp_path, groups):
    return {
        "jellyfin_url": "http://jellyfin.invalid",
        "api_key": "key",
        "target_path": str(tmp_path / "virtual"),
        "groups": groups,
    }


def test_non_string_group_name_does_not_abort_the_run(tmp_path):
    """A malformed *other* group must not stop a valid group from syncing."""
    groups = [
        {"name": 42, "source_type": "genre", "source_value": "Action"},
        {"name": "Valid", "source_type": "genre", "source_value": "Action"},
    ]

    with patch(
        "sync._process_group",
        return_value={"group": "Valid", "links": 3},
    ) as process:
        results = sync.run_sync(_sync_config(tmp_path, groups), dry_run=True)

    assert process.call_count == 1
    assert results[0] == {
        "group": "(unnamed)",
        "links": 0,
        "error": "Invalid group name",
    }
    assert results[1] == {"group": "Valid", "links": 3}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sort_order", ["SortName"]),
        ("source_type", ["genre"]),
        ("source_value", {"value": "Action"}),
        ("watch_state", ["watched"]),
    ],
)
def test_non_string_group_field_is_reported_per_group(tmp_path, field, value):
    group = {"name": "Bad", "source_type": "genre", "source_value": "Action"}
    group[field] = value

    # ``_process_group`` rejects the field before it touches the network, so no
    # stubbing is needed: the assertion is that the run completes at all.
    results = sync.run_sync(_sync_config(tmp_path, [group]), dry_run=True)

    assert len(results) == 1
    assert results[0]["group"] == "Bad"
    assert results[0]["links"] == 0
    assert results[0]["error"]


def test_missing_group_fields_still_sync(tmp_path):
    """``null`` and absent fields stay equivalent to the previous defaults."""
    group = {
        "name": "Plain",
        "source_type": None,
        "source_value": None,
        "sort_order": None,
        "watch_state": None,
    }

    with patch(
        "sync._process_group",
        return_value={"group": "Plain", "links": 0},
    ) as process:
        results = sync.run_sync(_sync_config(tmp_path, [group]), dry_run=True)

    assert process.call_count == 1
    assert results == [{"group": "Plain", "links": 0}]
