"""``POST /api/config`` must enforce the group-name rules it documents.

``docs/API.md`` states that ``groups`` must hold "unique non-empty names" and
is capped at 200 entries. Only the *type* of each field was validated, so all
three rules were unenforced:

* **Duplicate names.** Two groups called ``Dup`` resolve to the same target
  directory, so the second overwrites the first. The per-group scheduler also
  registers its job as ``group_sync_<name>`` and skips the later duplicate, so
  one of the two definitions never runs at all — and nothing said so.
* **Empty / whitespace-only names.** There is no directory to write into, so
  the group failed at sync time rather than at save time, long after the user
  could connect it to what they typed.
* **No count limit.** One save could queue an unbounded amount of sync work.

These tests pin the rules, and pin that ordinary configurations still save.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes
from app import app as flask_app


@pytest.fixture
def client():
    """Flask test client that sends the CSRF marker header."""
    flask_app.config.update(TESTING=False)
    test_client = flask_app.test_client()
    test_client.environ_base["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
    return test_client


def _group(name: object, **overrides: object) -> dict:
    """Return one group entry, valid apart from *name*."""
    group: dict[str, object] = {
        "name": name,
        "source_type": "genre",
        "source_value": "Action",
    }
    group.update(overrides)
    return group


def _post(client, groups: list) -> object:
    """POST *groups* and skip the on-disk write and scheduler refresh."""
    with patch("routes.save_config"), patch("routes.update_scheduler_jobs"):
        return client.post("/api/config", json={"groups": groups})


# ---------------------------------------------------------------------------
# Duplicate names
# ---------------------------------------------------------------------------


def test_duplicate_names_are_rejected(client):
    response = _post(client, [_group("Dup"), _group("Dup")])

    assert response.status_code == 400, response.get_json()
    errors = response.get_json()["errors"]
    assert any("duplicates" in error for error in errors), errors


def test_duplicate_detection_ignores_surrounding_whitespace(client):
    """``"Action"`` and ``" Action "`` share one target directory."""
    response = _post(client, [_group("Action"), _group(" Action ")])

    assert response.status_code == 400, response.get_json()
    assert any("duplicates" in error for error in response.get_json()["errors"])


def test_duplicate_error_names_both_indices(client):
    response = _post(client, [_group("A"), _group("B"), _group("A")])

    errors = response.get_json()["errors"]
    message = next(error for error in errors if "duplicates" in error)
    assert "groups[2]" in message
    assert "groups[0]" in message


def test_distinct_names_are_accepted(client):
    response = _post(client, [_group("Action"), _group("Comedy")])

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["status"] == "success"


def test_case_differences_are_not_duplicates(client):
    """Names are case-sensitive directories; both are usable."""
    response = _post(client, [_group("Action"), _group("action")])

    assert response.status_code == 200, response.get_json()


# ---------------------------------------------------------------------------
# Empty names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_empty_name_is_rejected(client, name):
    response = _post(client, [_group(name)])

    assert response.status_code == 400, response.get_json()
    assert any("must not be empty" in error for error in response.get_json()["errors"])


def test_missing_name_is_left_to_the_type_check(client):
    """A ``null`` name is a type problem, not an emptiness problem.

    Reporting both would double-report the same field, and ``null`` is how the
    UI represents "not filled in yet", so it must keep its existing message.
    """
    response = _post(client, [_group(None)])

    assert response.status_code == 200, response.get_json()


# ---------------------------------------------------------------------------
# Count cap
# ---------------------------------------------------------------------------


def test_more_than_200_groups_is_rejected(client):
    groups = [_group(f"G{i}") for i in range(routes._MAX_GROUPS + 1)]

    response = _post(client, groups)

    assert response.status_code == 400, response.get_json()
    assert any("at most" in error for error in response.get_json()["errors"])


def test_exactly_200_groups_is_accepted(client):
    groups = [_group(f"G{i}") for i in range(routes._MAX_GROUPS)]

    response = _post(client, groups)

    assert response.status_code == 200, response.get_json()


# ---------------------------------------------------------------------------
# The validator itself
# ---------------------------------------------------------------------------


def test_validator_skips_non_dict_entries():
    """Non-dict entries are reported by the type validator, not here."""
    assert routes._validate_group_names(["bare string", None, 42]) == []


def test_validator_ignores_non_string_names():
    """A number is a type error; ``_validate_group_names`` stays silent."""
    assert routes._validate_group_names([{"name": 42}]) == []


def test_validator_reports_every_problem():
    errors = routes._validate_group_names(
        [
            {"name": "A"},
            {"name": "A"},
            {"name": ""},
            {"name": "B"},
            {"name": "B"},
        ],
    )

    assert len(errors) == 3, errors


# ---------------------------------------------------------------------------
# Normalised duplicates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Anime/Action", "Anime//Action"),
        ("Anime/Action", "Anime / Action "),
        ("Action", "Action/"),
        ("A\\B", "A/B"),
    ],
)
def test_names_resolving_to_one_directory_are_duplicates(client, first, second):
    """The comparison must use the folder path, not the trimmed name.

    ``"Anime//Action"`` trims to itself and differs from ``"Anime/Action"``,
    yet both create ``<target>/Anime/Action``, so the second overwrote the
    first while the trimmed-name check reported no problem.
    """
    response = _post(client, [_group(first), _group(second)])

    assert response.status_code == 400, response.get_json()
    assert any("duplicates" in error for error in response.get_json()["errors"])


def test_duplicate_error_names_the_original_index_after_normalisation():
    """The reported index must point at the group that claimed the path."""
    errors = routes._validate_group_names(
        [{"name": "Anime/Action"}, {"name": "Other"}, {"name": "Anime//Action"}],
    )

    assert len(errors) == 1, errors
    assert "groups[2]" in errors[0]
    assert "groups[0]" in errors[0]


# ---------------------------------------------------------------------------
# Names the sync would always reject
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["..", ".", "Anime/../etc", "C:/windows", "a\x00b"],
)
def test_unusable_folder_names_are_rejected_at_save_time(client, name):
    """A save must not accept a name every sync will reject.

    ``normalize_group_relpath`` refuses these so the group directory stays
    inside the target path. Saving them anyway meant each sync answered
    "Invalid group name" with nothing tying it to the configuration.
    """
    response = _post(client, [_group(name)])

    assert response.status_code == 400, response.get_json()
    assert any("not a usable folder name" in e for e in response.get_json()["errors"])


def test_name_with_an_oversized_segment_is_rejected(client):
    """A 256-byte component cannot be created on ext4; fail at save time."""
    response = _post(client, [_group("A" * 256)])

    assert response.status_code == 400, response.get_json()
    assert any("255 bytes" in error for error in response.get_json()["errors"])


def test_leading_slash_names_a_nested_folder_inside_the_target(client):
    """A leading slash is dropped, not rejected: it is a nested folder name."""
    response = _post(client, [_group("/etc/passwd")])

    assert response.status_code == 200, response.get_json()


def test_name_with_a_255_byte_segment_is_accepted(client):
    """The limit is the filesystem's, so exactly 255 bytes stays usable."""
    response = _post(client, [_group("A" * 255)])

    assert response.status_code == 200, response.get_json()


def test_long_rejected_name_is_elided_in_the_error(client):
    """A multi-kilobyte name must not be echoed back in full."""
    response = _post(client, [_group("../" + "A" * 5000)])

    errors = response.get_json()["errors"]
    assert any("not a usable folder name" in error for error in errors)
    assert all(len(error) < 400 for error in errors), [len(e) for e in errors]
