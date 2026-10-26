"""Regression tests for the account/status split of list-backed groups.

AniList and MyAnimeList groups name an account, optionally followed by
``/status``.  The value is typed into the grouping form by hand, so it
arrives padded: ``"jane / completed"`` or ``"jane/ completed"``.  The split
used to run on the raw value, so the provider validator received
``" completed"`` and rejected it as an unknown status — a group the user had
filled in correctly failed with a message listing statuses that looked
identical to the one they typed.  A space in the account half failed the
username check the same way.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import sync


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("jane", ("jane", None)),
        ("jane/completed", ("jane", "completed")),
        (" jane / completed", ("jane", "completed")),
        ("jane/ completed", ("jane", "completed")),
        ("jane /completed ", ("jane", "completed")),
        # An absent status must not become an empty string, which the
        # provider would look up as a status name.
        ("jane/", ("jane", None)),
        ("jane/   ", ("jane", None)),
    ],
)
def test_split_account_and_status_trims_both_halves(value, expected):
    assert sync._split_account_and_status(value) == expected


def test_split_keeps_a_nested_status_token_verbatim():
    """Only surrounding whitespace is trimmed; validation stays with the provider."""
    assert sync._split_account_and_status("jane/ not a status") == (
        "jane",
        "not a status",
    )


def test_anilist_group_trims_padded_account_and_status():
    """The padded value must reach the fetcher already split and trimmed."""
    with patch("sync.fetch_anilist_list", return_value=[]) as fetch:
        sync._fetch_items_for_anilist_group(
            "Anime",
            " jane / completed ",
            "",
            "http://jellyfin",
            "key",
        )

    fetch.assert_called_once()
    username, status = fetch.call_args.args[0], fetch.call_args.args[1]
    assert username == "jane"
    assert status == "completed"


def test_mal_group_trims_padded_account_and_status():
    with patch("sync.fetch_mal_list", return_value=[]) as fetch:
        sync._fetch_items_for_mal_group(
            "Anime",
            " jane / completed ",
            "",
            "http://jellyfin",
            "key",
            "client-id",
        )

    fetch.assert_called_once()
    assert fetch.call_args.args[0] == "jane"
    assert fetch.call_args.args[2] == "completed"


def test_mal_group_without_status_passes_none():
    with patch("sync.fetch_mal_list", return_value=[]) as fetch:
        sync._fetch_items_for_mal_group(
            "Anime",
            "jane",
            "",
            "http://jellyfin",
            "key",
            "client-id",
        )

    assert fetch.call_args.args[2] is None


def test_padded_status_is_accepted_by_the_mal_validator():
    """A padded status used to be rejected as unknown even when valid."""
    mal = pytest.importorskip("mal")
    _, status = sync._split_account_and_status("jane/ completed")
    assert mal._normalize_mal_status(status) == "completed"


def test_padded_status_is_accepted_by_the_anilist_validator():
    anilist = pytest.importorskip("anilist")
    _, status = sync._split_account_and_status("jane/ COMPLETED")
    assert anilist._resolve_anilist_status(status) == "COMPLETED"
