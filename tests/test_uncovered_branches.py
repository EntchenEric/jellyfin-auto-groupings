"""Tests for the remaining defensive branches in the grouping package.

Each case here guards a path that deliberately avoids an exception a real
Jellyfin payload can trigger: a user list whose first entry carries no ``Id``,
a boolean ``ProductionYear``, and a ``PremiereDate`` value that is neither a
number nor a date string.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from jellyfin_auto_groupings.client import JellyfinClient, _resolve_release_year
from jellyfin_auto_groupings.rules import _numeric_premiere_year, group_by_decade


def test_first_admin_lookup_raises_when_no_user_has_an_id():
    """A user list with no admin and no usable ``Id`` is an error, not ``None``.

    ``get_first_admin_user_id`` promises a ``str``; returning the ``None`` the
    first entry lacks would push the failure into the first request that
    interpolates the id into a URL.
    """
    client = JellyfinClient("http://localhost:8096", "key")
    users = [{"Name": "no-id"}, {"Id": None, "Policy": {"IsAdministrator": False}}]

    with (
        patch.object(client, "get_users", return_value=users),
        pytest.raises(RuntimeError, match="No users found"),
    ):
        client.get_first_admin_user_id()


def test_first_admin_skips_null_policy_before_a_valid_user():
    """A ``null`` ``Policy`` must not stop the scan from reaching the admin."""
    client = JellyfinClient("http://localhost:8096", "key")
    users = [
        {"Id": "u1", "Policy": None},
        {"Id": "u2", "Policy": {"IsAdministrator": True}},
    ]

    with patch.object(client, "get_users", return_value=users):
        assert client.get_first_admin_user_id() == "u2"


@pytest.mark.parametrize("value", [True, False])
def test_boolean_production_year_is_not_a_release_year(value):
    """``bool`` is an ``int`` subclass, so ``True`` would read as year 1."""
    assert _resolve_release_year({"ProductionYear": value}) is None


def test_boolean_production_year_falls_back_to_premiere_date():
    """Rejecting a boolean ``ProductionYear`` must not skip the date fallback."""
    item = {"ProductionYear": True, "PremiereDate": "1994-03-01T00:00:00.0000000Z"}
    assert _resolve_release_year(item) == 1994


@pytest.mark.parametrize("value", ["1999", {"year": 1999}, [1999], None])
def test_numeric_premiere_year_rejects_non_numbers(value):
    """Only non-bool numbers are years; anything else is reported as unknown."""
    assert _numeric_premiere_year(value) is None


def test_numeric_premiere_year_survives_an_int_that_refuses_conversion():
    """An ``int`` subclass whose ``__int__`` raises must not abort grouping."""

    class HostileInt(int):
        def __int__(self):
            msg = "no conversion for you"
            raise ValueError(msg)

    assert _numeric_premiere_year(HostileInt(1999)) is None


def test_group_by_decade_keeps_a_usable_item_next_to_a_non_numeric_date():
    """A corrupt ``PremiereDate`` skips its own item only."""
    groups = group_by_decade(
        [
            {"Id": "bad", "Name": "Corrupt", "PremiereDate": {"unexpected": True}},
            {"Id": "good", "Name": "Fine", "PremiereDate": 1999},
        ]
    )

    assert groups == {
        "1990s Movies": [{"Id": "good", "Name": "Fine", "PremiereDate": 1999}],
    }
