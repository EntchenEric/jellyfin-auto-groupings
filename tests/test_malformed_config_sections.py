"""Malformed ``config.json`` sections must not crash the app.

``config.json`` is user-editable and the ``POST /api/config`` body is
untrusted client JSON, so ``scheduler`` may be ``null``, ``groups`` may be a
string, and a cron field may be a number.  Those used to raise
``AttributeError``/``TypeError`` from ``.get()``, ``.strip()`` or iteration,
which surfaced as an HTTP 500 (or crashed scheduler startup) instead of the
expected 400 with a validation message.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler

import config
import routes
import scheduler

_CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client whose config is isolated to *tmp_path*."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    # routes delegates persistence to config.load_config/save_config, which
    # read the module-level paths at call time — patching the config module
    # is enough to isolate the request.

    from app import app

    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def _post_config(client, payload):
    return client.post(
        "/api/config",
        data=json.dumps(payload),
        content_type="application/json",
        headers=_CSRF_HEADERS,
    )


# ---------------------------------------------------------------------------
# validate_cron
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, 5, 5.5, [], {}, True])
def test_validate_cron_rejects_non_string_values(value):
    """A non-string cron value is reported, not raised."""
    error = scheduler.validate_cron(value)

    assert error is not None
    assert "must be a string" in error


@pytest.mark.parametrize(
    "expr",
    ["", "   ", "* * * *", "* * * * * *", "not a cron"],
)
def test_validate_cron_still_rejects_bad_strings(expr):
    """Existing string validation is unchanged."""
    assert scheduler.validate_cron(expr) is not None


def test_validate_cron_accepts_valid_expression():
    assert scheduler.validate_cron("0 0 * * *") is None


# ---------------------------------------------------------------------------
# update_scheduler_jobs with a hand-edited config.json
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_config",
    [
        {"scheduler": None, "groups": []},
        {"scheduler": "nope", "groups": []},
        {"scheduler": {}, "groups": None},
        {"scheduler": {}, "groups": "abc"},
        {"scheduler": {}, "groups": {"a": 1}},
        {"scheduler": {"global_enabled": True, "global_schedule": 5}, "groups": []},
        {"scheduler": {"cleanup_enabled": True, "cleanup_schedule": 7}, "groups": []},
        {"scheduler": {}, "groups": ["not-a-dict"]},
        {
            "scheduler": {},
            "groups": [{"name": "x", "schedule_enabled": True, "schedule": 5}],
        },
    ],
)
def test_update_scheduler_jobs_survives_malformed_config(bad_config):
    """A malformed section is logged and skipped instead of crashing."""
    with patch.object(scheduler, "load_config", return_value=bad_config):
        scheduler.update_scheduler_jobs()  # must not raise


def test_update_scheduler_jobs_ignores_non_list_exclude_ids():
    """A non-list ``global_exclude_ids`` must not reach the job arguments."""
    fresh = BackgroundScheduler()
    scheduler._schedule_global_sync(
        fresh,
        {
            "global_enabled": True,
            "global_schedule": "0 0 * * *",
            "global_exclude_ids": "not-a-list",
        },
    )

    job = fresh.get_job("global_sync")
    assert job is not None
    assert job.args[0] == []
    fresh.remove_all_jobs()


# ---------------------------------------------------------------------------
# POST /api/config with malformed sections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        # Wrong-typed cron values are a 400 with a message.
        ({"scheduler": {"global_enabled": True, "global_schedule": None}}, 400),
        ({"scheduler": {"global_enabled": True, "global_schedule": 5}}, 400),
        ({"scheduler": {"cleanup_enabled": True, "cleanup_schedule": 7}}, 400),
        (
            {"groups": [{"name": "x", "schedule_enabled": True, "schedule": 5}]},
            400,
        ),
        # Wrong-typed sections are a 400 from the type validator.
        ({"scheduler": "nope"}, 400),
        ({"groups": "abc"}, 400),
        ({"groups": ["not-a-dict"]}, 400),
    ],
)
def test_post_config_returns_400_for_malformed_sections(
    client,
    payload,
    expected_status,
):
    """Malformed payloads are rejected, never answered with a 500."""
    response = _post_config(client, payload)

    assert response.status_code == expected_status, response.get_json()
    body = response.get_json()
    assert body["status"] == "error"
    assert body.get("errors")


def test_post_config_accepts_null_scheduler_and_groups(client):
    """Explicit nulls fall back to defaults and still save successfully."""
    response = _post_config(client, {"scheduler": None, "groups": None})

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["status"] == "success"


def test_validate_cron_expressions_skips_non_dict_scheduler():
    """The validator itself tolerates a wrong-typed ``scheduler``."""
    assert routes._validate_cron_expressions({"scheduler": None}) == []
    assert routes._validate_cron_expressions({"scheduler": "nope"}) == []


def test_validate_cron_expressions_skips_non_dict_group_entries():
    """A string entry inside ``groups`` must not raise from ``.get()``."""
    assert routes._validate_cron_expressions({"groups": ["abc"]}) == []
    assert routes._validate_cron_expressions({"groups": None}) == []


def test_validate_cron_expressions_reports_bad_types():
    """A non-string cron value is reported as a validation error."""
    errors = routes._validate_cron_expressions(
        {"scheduler": {"global_enabled": True, "global_schedule": 5}},
    )

    assert len(errors) == 1
    assert "must be a string" in errors[0]
