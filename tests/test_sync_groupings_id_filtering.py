"""Regression tests for unusable item IDs in :func:`sync_groupings`.

``sync_groupings`` used to build its ``Ids`` list with
``str(item["Id"]) for item in items if "Id" in item``. An item whose ``Id``
was present but ``None`` or empty therefore contributed the literal strings
``"None"`` or ``""`` to the request. Jellyfin rejects the whole ``Ids``
parameter when it contains one bad entry, so a single malformed item blocked
every item in the collection. This is the same class of bug that was already
fixed for the prefix-grouping paths of ``process_groupings`` and
``create_groupings``.
"""

from unittest.mock import MagicMock

import pytest

from jellyfin_auto_groupings.client import sync_groupings
from utils.helpers import parse_media_tags


def _client(existing=None):
    client = MagicMock()
    client.get_all_items.return_value = existing or []
    return client


def test_none_and_empty_ids_are_not_sent_to_jellyfin():
    client = _client()

    summary = sync_groupings(
        client, {"Bad": [{"Id": None}, {"Id": ""}, {"Id": "ok"}]}, dry_run=False
    )

    assert summary == {"Bad": ["ok"]}
    client.create_collection.assert_called_once_with("Bad", ["ok"])


def test_group_with_only_unusable_ids_is_never_created():
    client = _client()

    summary = sync_groupings(
        client, {"Bad": [{"Id": None}, {"Id": ""}, {}]}, dry_run=False
    )

    assert summary == {}
    client.create_collection.assert_not_called()
    client.add_to_collection.assert_not_called()


def test_missing_id_key_is_skipped_like_before():
    client = _client()

    summary = sync_groupings(
        client, {"Mixed": [{"Name": "no id"}, {"Id": "1"}]}, dry_run=False
    )

    assert summary == {"Mixed": ["1"]}
    client.create_collection.assert_called_once_with("Mixed", ["1"])


def test_non_dict_group_entries_are_skipped():
    """Duck-typed callers may hand in junk; it must not abort the group."""
    client = _client()

    summary = sync_groupings(
        client, {"Mixed": ["notadict", 7, {"Id": "1"}]}, dry_run=False
    )

    assert summary == {"Mixed": ["1"]}
    client.create_collection.assert_called_once_with("Mixed", ["1"])


def test_min_items_counts_usable_ids_not_raw_entries():
    """Two entries with one unusable id is a one-item collection, not two."""
    client = _client()

    summary = sync_groupings(
        client, {"Thin": [{"Id": None}, {"Id": "1"}]}, dry_run=False, min_items=2
    )

    assert summary == {}
    client.create_collection.assert_not_called()


def test_dry_run_summary_reflects_only_usable_ids():
    client = _client()

    summary = sync_groupings(client, {"Dry": [{"Id": "1"}, {"Id": None}]}, dry_run=True)

    assert summary == {"Dry": ["1"]}
    client.create_collection.assert_not_called()


def test_existing_collection_receives_only_usable_ids():
    client = _client([{"Id": "col_1", "Name": "Existing"}])

    summary = sync_groupings(
        client, {"Existing": [{"Id": "a"}, {"Id": ""}, {"Id": "b"}]}, dry_run=False
    )

    assert summary == {"Existing": ["a", "b"]}
    client.add_to_collection.assert_called_once_with("col_1", ["a", "b"])


@pytest.mark.parametrize("bad_id", [None, ""])
def test_no_literal_none_string_reaches_the_request(bad_id):
    """The literal "None" id was the observable symptom of the old bug."""
    client = _client()

    sync_groupings(client, {"G": [{"Id": bad_id}, {"Id": "real"}]}, dry_run=False)

    sent = client.create_collection.call_args.args[1]
    assert "None" not in sent
    assert "" not in sent


def test_parse_media_tags_ignores_non_string_entries():
    tags = [None, 42, {"bad": "tag"}, " Action ", "action", "Sci-Fi", ""]

    assert parse_media_tags(tags) == ["Action", "Sci-Fi"]


def test_parse_media_tags_tolerates_an_all_garbage_list():
    assert parse_media_tags([None, 1, b"bytes"]) == []
