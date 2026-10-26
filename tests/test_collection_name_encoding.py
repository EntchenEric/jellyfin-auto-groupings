"""Regression tests: collection names must be URL-encoded, not interpolated.

The legacy clients in ``jellyfin_groupings.py`` and ``main.py`` built their
request URLs with f-strings, so a group name that contained a query-string
metacharacter changed the request instead of the collection name:

* ``"Tom & Jerry"`` split into ``Name=Tom `` plus a stray ``Jerry`` parameter,
  so Jellyfin created a collection called ``"Tom "``.
* ``"Best of 2024 #1"`` put a ``#`` in the URL, which starts a fragment. The
  ``Ids`` parameter was never sent at all, so the collection was created
  empty — the sync then reported success while nothing was added.
* ``"C++"`` turned the ``+`` into a space, and a literal ``%`` could make the
  server reject the query as malformed percent-encoding.

The fix routes every user-supplied value through ``params=``, which lets
``requests`` escape it. These tests assert on the *prepared* URL, which is
what the server actually receives, rather than on the argument string.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

#: Names that used to produce a different request than the caller asked for.
_HOSTILE_NAMES = [
    "Tom & Jerry",
    "Best of 2024 #1",
    "C++",
    "100% Anime",
    "Sci-Fi + Fantasy",
    "Film: Noir",
    "A=B",
    "Query?Mark",
]


def _prepared_params(session_method_call) -> dict[str, list[str]]:
    """Return the query params ``requests`` would send for a recorded call."""
    from urllib.parse import parse_qs, urlparse

    url = session_method_call.args[0]
    params = session_method_call.kwargs.get("params")
    prepared = requests.Request("POST", url, params=params).prepare().url
    return parse_qs(urlparse(prepared).query)


@pytest.mark.parametrize("name", _HOSTILE_NAMES)
def test_legacy_client_create_collection_escapes_name(name):
    """``jellyfin_groupings.JellyfinClient`` keeps the name and the ids intact."""
    from jellyfin_groupings import JellyfinClient

    client = JellyfinClient("http://localhost:8096", "key")
    response = MagicMock()
    response.json.return_value = {"Id": "new_id"}
    response.raise_for_status.return_value = None

    with patch.object(client.session, "post", return_value=response) as mock_post:
        client.create_collection(name, ["a1", "b2"])

    params = _prepared_params(mock_post.call_args)
    assert params["Name"] == [name]
    assert params["Ids"] == ["a1,b2"]


@pytest.mark.parametrize("name", _HOSTILE_NAMES)
def test_root_main_client_create_collection_escapes_name(name):
    """The root ``main.JellyfinGroupings`` client behaves the same way."""
    import main as root_main

    client = root_main.JellyfinGroupings("http://localhost:8096", "key")
    response = MagicMock()
    response.json.return_value = {"Id": "new_id"}
    response.raise_for_status.return_value = None

    with patch.object(client.session, "post", return_value=response) as mock_post:
        client.create_collection(name)

    params = _prepared_params(mock_post.call_args)
    assert params["Name"] == [name]


def test_fragment_in_name_no_longer_drops_ids():
    """A ``#`` used to truncate the URL before ``Ids`` was sent.

    This is the case that failed silently: Jellyfin answered 200 with an
    empty collection, so the sync counted it as a success.
    """
    from jellyfin_groupings import JellyfinClient

    client = JellyfinClient("http://localhost:8096", "key")
    response = MagicMock()
    response.json.return_value = {"Id": "new_id"}
    response.raise_for_status.return_value = None

    with patch.object(client.session, "post", return_value=response) as mock_post:
        client.create_collection("Best of 2024 #1", ["a1"])

    prepared = (
        requests.Request(
            "POST",
            mock_post.call_args.args[0],
            params=mock_post.call_args.kwargs["params"],
        )
        .prepare()
        .url
    )
    assert "#" not in prepared
    assert "Ids=a1" in prepared


@pytest.mark.parametrize("name", _HOSTILE_NAMES)
def test_root_main_add_to_collection_escapes_ids(name):
    """``Ids`` is built from caller data too, so it must also be escaped.

    The ids here are item identifiers rather than names, but the same
    interpolation applied, and a caller passing a value with ``&`` produced
    a request for a different item.
    """
    import main as root_main

    client = root_main.JellyfinGroupings("http://localhost:8096", "key")
    response = MagicMock()
    response.raise_for_status.return_value = None

    item_ids = ["a1", name]
    with patch.object(client.session, "post", return_value=response) as mock_post:
        client.add_to_collection("col1", item_ids)

    params = _prepared_params(mock_post.call_args)
    assert params["Ids"] == [",".join(item_ids)]
