"""Regression tests for collection re-sorting when an item has no usable ``Id``.

Mode 1 of :func:`process_groupings` walks every collection and posts a
``ForcedSortName`` per item. It read the id with ``item.get("Id")`` but never
checked it, so an item without an ``Id`` produced a request to
``/Items/None``. Jellyfin answers that with a 404, which raises out of
``update_item_sort_name`` and aborts the remaining items in every later
collection.
"""

from unittest.mock import MagicMock

import pytest

from jellyfin_auto_groupings.client import JellyfinClient, process_groupings


class _CollectionClient:
    """Minimal collection-capable client recording sort-name writes."""

    def __init__(self, items, collections=None):
        self._items = items
        self._collections = (
            collections if collections is not None else [{"Id": "c1", "Name": "Saga"}]
        )
        self.updates: list[tuple[object, object]] = []

    def get_collections(self):
        return self._collections

    def get_collection_items(self, collection_id):
        return self._items

    def update_item_sort_name(self, item_id, sort_name):
        self.updates.append((item_id, sort_name))


def test_dry_run_skips_items_without_id():
    client = _CollectionClient(
        [
            {"Name": "NoId", "PremiereDate": "1999-01-01"},
            {"Id": "m2", "Name": "HasId", "PremiereDate": "2000-01-01"},
        ]
    )

    changes = process_groupings(client, dry_run=True)

    assert [change[0] for change in changes] == ["m2"]
    assert client.updates == []


def test_real_run_never_posts_a_none_id():
    client = _CollectionClient(
        [
            {"Name": "NoId", "PremiereDate": "1999-01-01"},
            {"Id": "m2", "Name": "HasId", "PremiereDate": "2000-01-01"},
        ]
    )

    process_groupings(client, dry_run=False)

    assert client.updates == [("m2", "Saga 02")]


@pytest.mark.parametrize("bad_id", [None, "", 0, False])
def test_falsy_ids_are_treated_as_missing(bad_id):
    client = _CollectionClient(
        [{"Id": bad_id, "Name": "Broken", "PremiereDate": "1999-01-01"}]
    )

    assert process_groupings(client, dry_run=False) == []
    assert client.updates == []


def test_missing_id_keeps_later_positions_stable():
    """The skipped item still consumes a position, so names do not shift."""
    client = _CollectionClient(
        [
            {"Name": "NoId", "PremiereDate": "1990-01-01"},
            {"Id": "m2", "Name": "Second", "PremiereDate": "1991-01-01"},
            {"Id": "m3", "Name": "Third", "PremiereDate": "1992-01-01"},
        ]
    )

    process_groupings(client, dry_run=False)

    assert client.updates == [("m2", "Saga 02"), ("m3", "Saga 03")]


def test_a_failing_update_still_aborts_the_sync():
    """A genuine server error must not be swallowed as a missing id."""
    client = _CollectionClient(
        [{"Id": "m1", "Name": "A", "PremiereDate": "1999-01-01"}]
    )
    client.update_item_sort_name = MagicMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        process_groupings(client, dry_run=False)


def test_client_object_mode_is_unaffected_by_the_guard():
    """A real JellyfinClient still reports planned changes for valid ids."""
    client = JellyfinClient("http://localhost:8096", "key", user_id="u1")
    client.get_collections = MagicMock(return_value=[{"Id": "c1", "Name": "Saga"}])
    client.get_collection_items = MagicMock(
        return_value=[{"Id": "m1", "Name": "A", "PremiereDate": "1999-01-01"}]
    )
    client.update_item_sort_name = MagicMock()

    changes = process_groupings(client, dry_run=True)

    assert changes == [("m1", "A", "Saga 01")]
    client.update_item_sort_name.assert_not_called()
