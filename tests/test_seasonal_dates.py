"""Seasonal ``MM-DD`` dates must be validated against a real calendar.

A seasonal group is deleted when its window ends, and the window is decided by
:func:`sync._is_in_season`.  That helper treats an unparseable date as "always
in season" (deliberate: a broken rule should not delete a library), so a
window the app accepted but could not parse never ends — the group is synced
forever and its directory is never cleaned up.

``POST /api/config`` only checked the *shape* ``MM-DD``, so ``02-31``,
``02-30``, and ``04-31`` were stored happily while
:func:`sync._parse_mmdd` rejected them.  Validation now rejects days that do
not exist in the given month.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from _common import is_valid_mmdd
from sync import _is_in_season, _parse_mmdd

_CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client whose config file lives under *tmp_path*."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")

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


def _config_with_seasonal(start: str, end: str) -> dict:
    cfg = config.load_config()
    cfg["groups"] = [
        {
            "name": "Winter",
            "source_type": "genre",
            "source_value": "Action",
            "seasonal_enabled": True,
            "seasonal_start": start,
            "seasonal_end": end,
        },
    ]
    return cfg


# ---------------------------------------------------------------------------
# is_valid_mmdd
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["01-01", "02-29", "02-28", "04-30", "06-15", "12-31", "10-31"],
)
def test_valid_dates_accepted(value):
    assert is_valid_mmdd(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "02-30",
        "02-31",
        "04-31",
        "06-31",
        "09-31",
        "11-31",
        "00-10",
        "13-01",
        "00-00",
        "12-00",
    ],
)
def test_impossible_dates_rejected(value):
    assert is_valid_mmdd(value) is False


def test_february_allows_leap_day():
    # 2024 is a leap year and the helper assumes one, so a Feb-29 boundary is
    # meaningful without knowing which year the sync runs in.
    assert is_valid_mmdd("02-29") is True


@pytest.mark.parametrize(
    "value",
    [None, 5, 2.5, True, [], {}, "02-31-01", "2-1", "02/31", "", "  ", "ab-cd"],
)
def test_non_date_values_rejected(value):
    assert is_valid_mmdd(value) is False


def test_surrounding_whitespace_tolerated():
    assert is_valid_mmdd(" 12-01 ") is True


def test_validator_agrees_with_sync_parser():
    """Anything accepted for saving must be parseable at sync time.

    This is the actual invariant: when the two disagree, a saved window is
    silently treated as "always in season" and never cleaned up.
    """
    for month in range(1, 13):
        for day in range(1, 32):
            value = f"{month:02d}-{day:02d}"
            assert is_valid_mmdd(value) is (_parse_mmdd(value) != (0, 0)), value


# ---------------------------------------------------------------------------
# POST /api/config
# ---------------------------------------------------------------------------


def test_config_rejects_february_31(client):
    response = _post_config(client, _config_with_seasonal("02-31", "03-15"))

    assert response.status_code == 400
    body = response.get_json()
    assert body["status"] == "error"
    assert any("seasonal_start" in error for error in body["errors"]), body
    assert any("02-31" in error for error in body["errors"]), body


def test_config_rejects_impossible_end_date(client):
    response = _post_config(client, _config_with_seasonal("11-01", "04-31"))

    assert response.status_code == 400
    body = response.get_json()
    assert any("seasonal_end" in error for error in body["errors"]), body


def test_config_accepts_real_dates(client):
    response = _post_config(client, _config_with_seasonal("10-01", "11-01"))

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["status"] == "success"


def test_config_accepts_leap_day(client):
    response = _post_config(client, _config_with_seasonal("02-29", "03-15"))

    assert response.status_code == 200, response.get_json()


def test_config_accepts_empty_dates(client):
    # An absent/blank window is not an error; the seasonal toggle alone is
    # harmless and the group stays in season.
    response = _post_config(client, _config_with_seasonal("", ""))

    assert response.status_code == 200, response.get_json()


# ---------------------------------------------------------------------------
# Why it matters: an unparseable window never ends
# ---------------------------------------------------------------------------


def test_unparseable_window_is_treated_as_always_in_season():
    # This is the behaviour that made the validation bug consequential: a
    # rejected date silently disables seasonal cleanup instead of erroring.
    assert _is_in_season("02-31", "03-15") is True


def test_rejected_date_would_have_saved_before_the_fix():
    """Guard against a regression to shape-only validation."""
    import re

    old_pattern = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
    assert old_pattern.match("02-31") is not None
    assert is_valid_mmdd("02-31") is False


# ---------------------------------------------------------------------------
# Out-of-season cleanup must not wipe nested child groups
# ---------------------------------------------------------------------------


def test_out_of_season_parent_keeps_nested_child_group(tmp_path, monkeypatch):
    """An out-of-season parent group must not delete a child group's folder.

    ``Anime`` may hold its own links *and* the directory of the nested group
    ``Anime/Action``.  Cleanup used ``shutil.rmtree`` on the whole tree, so the
    in-season child's links were deleted and only came back if the child
    happened to sync afterwards.
    """
    import sync

    monkeypatch.setattr(sync, "_is_in_season", lambda start, end: False)

    parent = tmp_path / "Anime"
    child = parent / "Action"
    child.mkdir(parents=True)
    (parent / "01 - Parent Movie.mkv").symlink_to("/tmp/parent-movie")
    (child / "01 - Child Movie.mkv").symlink_to("/tmp/child-movie")

    result = sync._maybe_handle_seasonal(
        {"seasonal_enabled": True, "seasonal_start": "01-01", "seasonal_end": "01-02"},
        "Anime",
        str(tmp_path),
        dry_run=False,
    )

    assert result == {"group": "Anime", "links": 0, "status": "out_of_season"}
    assert parent.is_dir(), "the parent directory still holds a nested group"
    assert [entry.name for entry in parent.iterdir()] == ["Action"]
    assert (child / "01 - Child Movie.mkv").is_symlink()


def test_out_of_season_leaf_group_is_removed_entirely(tmp_path, monkeypatch):
    """A group with no nested children still leaves nothing behind."""
    import sync

    monkeypatch.setattr(sync, "_is_in_season", lambda start, end: False)

    leaf = tmp_path / "Winter"
    leaf.mkdir()
    (leaf / "01 - Movie.mkv").symlink_to("/tmp/movie")

    sync._maybe_handle_seasonal(
        {"seasonal_enabled": True, "seasonal_start": "01-01", "seasonal_end": "01-02"},
        "Winter",
        str(tmp_path),
        dry_run=False,
    )

    assert not leaf.exists()


def test_out_of_season_dry_run_touches_nothing(tmp_path, monkeypatch):
    """A dry run resolves the window but never deletes files."""
    import sync

    monkeypatch.setattr(sync, "_is_in_season", lambda start, end: False)

    group_dir = tmp_path / "Winter"
    group_dir.mkdir()
    (group_dir / "01 - Movie.mkv").symlink_to("/tmp/movie")

    sync._maybe_handle_seasonal(
        {"seasonal_enabled": True, "seasonal_start": "01-01", "seasonal_end": "01-02"},
        "Winter",
        str(tmp_path),
        dry_run=True,
    )

    assert (group_dir / "01 - Movie.mkv").is_symlink()


# ---------------------------------------------------------------------------
# A symlinked group directory must never be cleared through
# ---------------------------------------------------------------------------


def test_prepare_group_directory_does_not_clear_a_symlink_target(tmp_path):
    """The target directory's contents are the user's media, not our links.

    ``_clear_group_directory`` walked ``iterdir()``, which follows a symlink,
    so a group folder that was a link deleted every file at the other end and
    then recreated the folder as an empty real directory.
    """
    import sync

    media = tmp_path / "real-media"
    media.mkdir()
    (media / "movie.mkv").write_text("real media", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()
    (target / "Anime").symlink_to(media)

    sync._prepare_group_directory(str(target / "Anime"), "Anime", str(target), False)

    assert (media / "movie.mkv").is_file(), "the link target's files must survive"
    assert not (target / "Anime").is_symlink()
    assert (target / "Anime").is_dir()


def test_prepare_group_directory_recovers_from_a_broken_symlink(tmp_path):
    """A dangling link occupies the name even though ``exists()`` says no.

    ``Path.exists()`` follows links, so a leftover ``<target>/<group>`` link
    whose destination was deleted reported "not there". The cleanup was then
    skipped and ``mkdir()`` failed with ``FileExistsError``, aborting the whole
    sync for that group. The link must be cleared and a real directory made.
    """
    import sync

    target = tmp_path / "target"
    target.mkdir()
    (target / "Anime").symlink_to(tmp_path / "deleted-media")

    assert not (target / "Anime").exists()
    assert (target / "Anime").is_symlink()

    sync._prepare_group_directory(str(target / "Anime"), "Anime", str(target), False)

    group_dir = target / "Anime"
    assert not group_dir.is_symlink()
    assert group_dir.is_dir()
