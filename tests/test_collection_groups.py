"""Coverage for the collection (Boxset) group mode.

``sync._process_collection_group`` implements the ``create_as_collection``
option exposed in the UI: instead of writing numbered symlinks, the resolved
items are pushed into a Jellyfin Collection.  The branch had no tests, so the
behaviours pinned here are the ones that silently degrade a user's library:

* a dry run must not touch the Jellyfin API at all,
* an existing collection is extended rather than duplicated,
* a collection is only created once, with its items attached,
* an API failure is reported per group instead of aborting the whole sync,
* a cover upload failure is logged but keeps the already-created collection.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import sync

_URL = "http://jellyfin.test:8096"
_API_KEY = "test-key"


def _items(*ids: str) -> list[dict[str, object]]:
    """Build minimal Jellyfin items, one per ID."""
    return [
        {"Id": item_id, "Name": f"Movie {item_id}", "ProductionYear": 2020}
        for item_id in ids
    ]


def _process(**overrides: object):
    kwargs: dict[str, object] = {
        "group_name": "Action",
        "items": _items("1", "2"),
        "url": _URL,
        "api_key": _API_KEY,
        "target_base": "/library",
        "dry_run": False,
        "auto_set_library_covers": False,
    }
    kwargs.update(overrides)
    return sync._process_collection_group(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Input guards
# ---------------------------------------------------------------------------


def test_items_without_usable_ids_report_an_error():
    result = _process(items=[{}, {"Id": ""}, {"Id": None}, "not-a-dict"])

    assert result["group"] == "Action"
    assert result["links"] == 0
    assert result["error"] == "No item IDs to add to collection"


def test_non_dict_entries_are_skipped_but_valid_ids_still_count():
    with (
        patch.object(sync, "find_collection_by_name", return_value="c1") as find,
        patch.object(sync, "add_to_collection") as add,
    ):
        result = _process(items=[{"Id": "1"}, "junk", None, {"Id": "2"}])

    find.assert_called_once_with(_URL, _API_KEY, "Action")
    add.assert_called_once_with(_URL, _API_KEY, "c1", ["1", "2"])
    assert result == {"group": "Action", "links": 2}


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_previews_without_calling_the_api():
    with (
        patch.object(sync, "find_collection_by_name") as find,
        patch.object(sync, "create_collection") as create,
        patch.object(sync, "add_to_collection") as add,
        patch.object(sync, "set_collection_image") as cover,
    ):
        result = _process(dry_run=True, auto_set_library_covers=True)

    for mocked in (find, create, add, cover):
        mocked.assert_not_called()

    assert result["links"] == 2
    assert result["items"] == [
        {"Name": "Movie 1", "Year": 2020},
        {"Name": "Movie 2", "Year": 2020},
    ]


def test_dry_run_caps_the_preview_at_the_maximum():
    ids = [str(index) for index in range(sync._MAX_PREVIEW_ITEMS + 25)]

    result = _process(items=_items(*ids), dry_run=True)

    assert result["links"] == len(ids)
    assert len(result["items"]) == sync._MAX_PREVIEW_ITEMS


def test_dry_run_reports_zero_links_when_ids_are_missing():
    result = _process(items=[{"Name": "nameless"}], dry_run=True)

    assert result["links"] == 0
    assert result["error"] == "No item IDs to add to collection"


# ---------------------------------------------------------------------------
# Existing vs. new collection
# ---------------------------------------------------------------------------


def test_existing_collection_is_extended_not_recreated():
    with (
        patch.object(sync, "find_collection_by_name", return_value="existing-id"),
        patch.object(sync, "add_to_collection") as add,
        patch.object(sync, "create_collection") as create,
    ):
        result = _process()

    add.assert_called_once_with(_URL, _API_KEY, "existing-id", ["1", "2"])
    create.assert_not_called()
    assert result == {"group": "Action", "links": 2}


def test_missing_collection_is_created_with_its_items():
    with (
        patch.object(sync, "find_collection_by_name", return_value=None),
        patch.object(sync, "create_collection", return_value="new-id") as create,
        patch.object(sync, "add_to_collection") as add,
    ):
        result = _process()

    # create_collection already attaches the items; adding them again would
    # be a wasted round-trip per group.
    create.assert_called_once_with(_URL, _API_KEY, "Action", ["1", "2"])
    add.assert_not_called()
    assert result == {"group": "Action", "links": 2}


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (RuntimeError("Jellyfin exploded"), "Jellyfin exploded"),
        (OSError("disk gone"), "disk gone"),
    ],
)
def test_api_failures_are_reported_per_group(raised, expected):
    with patch.object(sync, "find_collection_by_name", side_effect=raised):
        result = _process()

    assert result["group"] == "Action"
    assert result["links"] == 0
    assert result["error"] == expected


def test_failure_to_create_is_reported_without_a_cover_upload():
    with (
        patch.object(sync, "find_collection_by_name", return_value=None),
        patch.object(sync, "create_collection", side_effect=RuntimeError("boom")),
        patch.object(sync, "set_collection_image") as cover,
    ):
        result = _process(auto_set_library_covers=True)

    cover.assert_not_called()
    assert result["links"] == 0
    assert result["error"] == "boom"


# ---------------------------------------------------------------------------
# Cover handling
# ---------------------------------------------------------------------------


def test_existing_cover_is_uploaded_to_the_collection(tmp_path):
    cover_file = tmp_path / "poster.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff")

    with (
        patch.object(sync, "find_collection_by_name", return_value="c1"),
        patch.object(sync, "add_to_collection"),
        patch.object(sync, "get_cover_path", return_value=str(cover_file)),
        patch.object(sync, "set_collection_image") as set_image,
    ):
        result = _process(auto_set_library_covers=True)

    set_image.assert_called_once_with(_URL, _API_KEY, "c1", str(cover_file))
    assert result == {"group": "Action", "links": 2}


def test_cover_is_not_uploaded_when_the_option_is_off(tmp_path):
    cover_file = tmp_path / "poster.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff")

    with (
        patch.object(sync, "find_collection_by_name", return_value="c1"),
        patch.object(sync, "add_to_collection"),
        patch.object(sync, "get_cover_path", return_value=str(cover_file)),
        patch.object(sync, "set_collection_image") as set_image,
    ):
        _process(auto_set_library_covers=False)

    set_image.assert_not_called()


def test_cover_path_that_vanished_is_skipped(tmp_path):
    missing = tmp_path / "deleted.jpg"

    with (
        patch.object(sync, "find_collection_by_name", return_value="c1"),
        patch.object(sync, "add_to_collection"),
        patch.object(sync, "get_cover_path", return_value=str(missing)),
        patch.object(sync, "set_collection_image") as set_image,
    ):
        result = _process(auto_set_library_covers=True)

    set_image.assert_not_called()
    assert result == {"group": "Action", "links": 2}


def test_cover_upload_oserror_keeps_the_collection_result(tmp_path, caplog):
    cover_file = tmp_path / "poster.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff")

    with (
        patch.object(sync, "find_collection_by_name", return_value="c1"),
        patch.object(sync, "add_to_collection"),
        patch.object(sync, "get_cover_path", return_value=str(cover_file)),
        patch.object(sync, "set_collection_image", side_effect=OSError("unreadable")),
    ):
        result = _process(auto_set_library_covers=True)

    assert result == {"group": "Action", "links": 2}
    assert "Failed to set collection image" in caplog.text


# ---------------------------------------------------------------------------
# Wiring through _process_group
# ---------------------------------------------------------------------------


def _run_group(group: dict[str, object], **overrides: object):
    kwargs: dict[str, object] = {
        "group": group,
        "target_base": "/library",
        "url": _URL,
        "api_key": _API_KEY,
        "jellyfin_root": "",
        "host_root": "",
        "trakt_client_id": "",
        "tmdb_api_key": "",
        "mal_client_id": "",
    }
    kwargs.update(overrides)
    return sync._process_group(**kwargs)  # type: ignore[arg-type]


def test_process_group_routes_collections_away_from_symlinks(tmp_path):
    group = {"name": "Action", "create_as_collection": True}

    with (
        patch.object(sync, "_prepare_group_directory"),
        patch.object(
            sync, "_resolve_group_source", return_value=(_items("1"), None, 200)
        ),
        patch.object(
            sync,
            "_process_collection_group",
            return_value={"group": "Action", "links": 1},
        ) as collection,
        patch.object(sync, "_create_group_symlinks") as symlinks,
    ):
        result = _run_group(group, target_base=str(tmp_path))

    collection.assert_called_once()
    symlinks.assert_not_called()
    assert result == {"group": "Action", "links": 1}


def test_collection_group_does_not_create_a_library_directory(tmp_path):
    """A Boxset group writes no symlinks, so a folder would only be clutter.

    Preparing the directory for it left an empty ``<target>/Action`` behind
    that Jellyfin then scanned as an extra (always empty) library folder.
    """
    group = {"name": "Action", "create_as_collection": True}

    with (
        patch.object(
            sync, "_resolve_group_source", return_value=(_items("1"), None, 200)
        ),
        patch.object(sync, "find_collection_by_name", return_value="cid"),
        patch.object(sync, "add_to_collection"),
    ):
        result = _run_group(group, target_base=str(tmp_path))

    assert result == {"group": "Action", "links": 1}
    assert list(tmp_path.iterdir()) == []


def test_process_group_still_uses_symlinks_without_the_flag(tmp_path):
    group = {"name": "Action"}

    with (
        patch.object(sync, "_prepare_group_directory", return_value=None),
        patch.object(
            sync, "_resolve_group_source", return_value=(_items("1"), None, 200)
        ),
        patch.object(sync, "_process_collection_group") as collection,
        patch.object(sync, "_create_group_symlinks", return_value=(1, [])) as symlinks,
        patch.object(
            sync, "_auto_create_library", side_effect=lambda result, *a, **k: result
        ),
        patch.object(sync, "_auto_set_library_cover"),
    ):
        result = _run_group(group, target_base=str(tmp_path))

    collection.assert_not_called()
    symlinks.assert_called_once()
    assert result == {"group": "Action", "links": 1}


def test_process_group_reports_source_errors_before_creating_anything(tmp_path):
    group = {"name": "Action", "create_as_collection": True}

    with (
        patch.object(sync, "_prepare_group_directory", return_value=None),
        patch.object(sync, "_resolve_group_source", return_value=([], "nope", 400)),
        patch.object(sync, "_process_collection_group") as collection,
    ):
        result = _run_group(group, target_base=str(tmp_path))

    collection.assert_not_called()
    assert result == {"group": "Action", "links": 0, "error": "nope"}
