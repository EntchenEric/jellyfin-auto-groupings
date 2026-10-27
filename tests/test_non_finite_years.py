"""Regression tests for non-finite numeric year values.

Jellyfin payloads are not guaranteed to hold finite numbers. A partially
scanned item can report ``PremiereDate`` as ``NaN`` or ``Infinity``, and a
proxy or corrupt scan can do the same for ``ProductionYear``. Both grouping
paths converted such a value with a bare ``int()``, which raises
``ValueError`` for ``NaN`` and ``OverflowError`` for the infinities, so one
corrupt item aborted the entire grouping pass rather than being skipped.
"""

from __future__ import annotations

import pytest

from jellyfin_auto_groupings.client import get_decade_groups
from jellyfin_auto_groupings.rules import group_by_decade
from jellyfin_groupings import process_groupings

#: Non-finite floats that ``int()`` refuses with an exception.
NON_FINITE = [
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="inf"),
    pytest.param(float("-inf"), id="-inf"),
]


class _StubClient:
    """Minimal client stub returning one collection with fixed items."""

    def __init__(self, items):
        self._items = items

    def get_collections(self):
        return [{"Name": "Saga", "Id": "coll-1"}]

    def get_collection_items(self, _collection_id):
        return self._items


@pytest.mark.parametrize("bad", NON_FINITE)
def test_group_by_decade_skips_non_finite_premiere_date(bad):
    """A non-finite ``PremiereDate`` is ignored, not raised on."""
    groups = group_by_decade([{"Id": "1", "Name": "Corrupt", "PremiereDate": bad}])
    assert groups == {}


def test_group_by_decade_keeps_usable_items_next_to_a_corrupt_one():
    """One corrupt item must not cost the other items their group."""
    groups = group_by_decade(
        [
            {"Id": "bad", "Name": "Corrupt", "PremiereDate": float("nan")},
            {"Id": "good", "Name": "Fine", "PremiereDate": "1999-05-01"},
        ]
    )
    assert groups == {
        "1990s Movies": [
            {"Id": "good", "Name": "Fine", "PremiereDate": "1999-05-01"},
        ]
    }


@pytest.mark.parametrize("bad", NON_FINITE)
def test_get_decade_groups_skips_non_finite_premiere_date(bad):
    """The packaged client's decade helper has the same guard."""
    assert get_decade_groups([{"Id": "1", "PremiereDate": bad}]) == {}


def test_get_decade_groups_keeps_usable_items_next_to_a_corrupt_one():
    groups = get_decade_groups(
        [
            {"Id": "bad", "PremiereDate": float("inf")},
            {"Id": "good", "PremiereDate": 2004},
        ]
    )
    assert groups == {"2000s Movies": [{"Id": "good", "PremiereDate": 2004}]}


@pytest.mark.parametrize("bad", NON_FINITE)
def test_process_groupings_skips_non_finite_premiere_date(bad):
    """Sort-name assignment must survive a corrupt ``PremiereDate``.

    The crash happened inside ``sorted()``, so it aborted the whole collection
    rather than leaving one item unsorted.
    """
    client = _StubClient(
        [
            {"Id": "bad", "Name": "Corrupt", "PremiereDate": bad},
            {"Id": "good", "Name": "Dated", "PremiereDate": "2020-01-01"},
        ]
    )
    changes = process_groupings(client, dry_run=True)

    # Both items still receive a sort name; the corrupt one sorts after the
    # genuinely dated item instead of crashing the pass.
    assert [change[0] for change in changes] == ["good", "bad"]
    assert [change[2] for change in changes] == ["Saga 01", "Saga 02"]


def test_process_groupings_sorts_finite_numeric_premiere_date():
    """A finite numeric year keeps its existing date-ranking behaviour."""
    client = _StubClient(
        [
            {"Id": "later", "Name": "Later", "PremiereDate": 2015},
            {"Id": "earlier", "Name": "Earlier", "PremiereDate": 1999},
        ]
    )
    changes = process_groupings(client, dry_run=True)
    assert [change[0] for change in changes] == ["earlier", "later"]
