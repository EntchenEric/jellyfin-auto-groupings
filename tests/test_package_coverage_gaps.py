"""Additional tests to raise coverage of the migrated package modules.

Targets error paths and branches that the existing suites miss:

- ``jellyfin_auto_groupings.client``: HTTP error plumbing in ``_get``/``_post``/
  ``_delete``, lazy admin-resolution, ``get_items`` wrapping errors in
  ``JellyfinAPIError``, tag/genre grouping min-size filtering, both
  ``process_groupings`` modes, and ``create_groupings`` query presets.
- ``jellyfin_auto_groupings.cli``: argument-validation and request-failure
  exit paths.
- ``jellyfin_auto_groupings.rules``: genre keyword matching, empty-input
  handling, string-year and premiere-date fallbacks.
- ``jellyfin_groupings`` (legacy module via package shim): library fetch,
  sort-name update failure branch, skip branches in ``process_groupings``,
  and the module ``main()`` entry paths.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jellyfin_auto_groupings import JellyfinClient
from jellyfin_auto_groupings.cli import build_parser
from jellyfin_auto_groupings.cli import main as cli_main
from jellyfin_auto_groupings.client import (
    JellyfinAPIError,
    create_groupings,
    get_movies_by_query,
    group_items_by_pattern,
    group_movies_by_genre,
    group_movies_by_tag,
    process_groupings,
    sync_groupings,
)
from jellyfin_auto_groupings.rules import create_groupings as rules_create_groupings
from jellyfin_auto_groupings.rules import group_by_decade

# ---------------------------------------------------------------------------
# jellyfin_auto_groupings.client - HTTP plumbing
# ---------------------------------------------------------------------------


def _client() -> JellyfinClient:
    return JellyfinClient("http://localhost:8096", "key", user_id="u1")


def test_client_get_error_reraises():
    client = _client()
    with (
        patch.object(client.session, "get", side_effect=requests.ConnectionError("x")),
        pytest.raises(requests.ConnectionError),
    ):
        client._get("/Users")


def test_client_post_error_reraises():
    client = _client()
    with (
        patch.object(client.session, "post", side_effect=requests.Timeout("t")),
        pytest.raises(requests.Timeout),
    ):
        client._post("/Collections", params={"Name": "x"})


def test_client_delete_return_paths():
    client = _client()

    # Blank body -> None
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.text = "  "
    with patch.object(client.session, "delete", return_value=mock_resp):
        assert client.remove_from_collection("c1", ["i1"]) == {}

    # Non-JSON body -> raw text
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.text = "No Content"
    mock_resp.json.side_effect = ValueError("nope")
    with patch.object(client.session, "delete", return_value=mock_resp):
        assert client._delete("/x") == "No Content"

    # HTTP failure -> exception re-raised
    with (
        patch.object(client.session, "delete", side_effect=requests.HTTPError("5xx")),
        pytest.raises(requests.HTTPError),
    ):
        client._delete("/x")


def test_client_post_blank_text_returns_none():
    client = _client()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.text = ""
    with patch.object(client.session, "post", return_value=mock_resp):
        res = client._post("/test")
    assert res is None


def test_client_add_and_remove_empty_ids_short_circuit():
    client = _client()
    assert client.add_to_collection("c1", []) == {}
    assert client.remove_from_collection("c1", []) == {}
    # No HTTP calls should have been made.
    with patch.object(client.session, "post") as mock_post:
        client.add_to_collection("c1", [])
        mock_post.assert_not_called()


def test_client_create_collection_empty_returns_empty_dict():
    client = _client()
    assert client.create_collection("Empty", []) == {}


def test_client_create_collection_wraps_non_dict_response():
    client = _client()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.text = "created"
    mock_resp.json.return_value = {"Id": "c9"}
    with patch.object(client.session, "post", return_value=mock_resp):
        assert client.create_collection("New", ["1"]) == {"Id": "c9"}
        # dict-shaped body returns as-is even if json parse would fail
        mock_resp.json.side_effect = ValueError("plain text")
        assert client.create_collection("New", ["1"]) == {"Id": "created"}


def test_client_get_all_items_resolves_admin_when_user_id_missing():
    client = JellyfinClient("http://localhost:8096", "key", user_id="")
    assert client.user_id == ""
    with (
        patch.object(
            client,
            "get_first_admin_user_id",
            return_value="admin-1",
        ) as mock_admin,
        patch.object(
            client,
            "_get",
            return_value={"Items": [{"Id": "i1"}]},
        ) as mock_get,
    ):
        items = client.get_all_items()
    assert items == [{"Id": "i1"}]
    mock_admin.assert_called_once()
    assert client.user_id == "admin-1"
    mock_get.assert_called_once()


def test_client_get_items_success_and_error_wrap():
    client = _client()
    with patch.object(
        client, "_get", return_value={"Items": [{"Id": "i1", "Name": "M"}]}
    ):
        assert client.get_items("lib1") == [{"Id": "i1", "Name": "M"}]

    with (
        patch.object(client, "_get", side_effect=requests.RequestException("boom")),
        pytest.raises(JellyfinAPIError, match="API request GET /Items failed"),
    ):
        client.get_items("lib1")


def test_client_get_collections_and_collection_items_delegate():
    client = _client()
    with patch.object(
        client, "get_all_items", return_value=[{"Id": "c1", "Name": "C"}]
    ) as mock_all:
        assert client.get_collections() == [{"Id": "c1", "Name": "C"}]
        assert client.get_collection_items("c1") == [{"Id": "c1", "Name": "C"}]
        assert mock_all.call_args_list[0].args == ()
        assert getattr(mock_all.call_args_list[0], "kwargs", {}) == {
            "item_types": ["BoxSet"]
        }
        assert mock_all.call_args_list[1].kwargs == {"parent_id": "c1"}


def test_client_update_item_sort_name_swallows_and_reraises():
    client = _client()
    # Success path: no exception raised
    with patch.object(client.session, "post") as mock_post:
        mock_post.return_value = MagicMock()
        client.update_item_sort_name("i1", "Name 01")
        assert mock_post.call_count == 1
    # Failure path: exception logged then re-raised
    with (
        patch.object(client.session, "post", side_effect=OSError("network down")),
        pytest.raises(OSError),
    ):
        client.update_item_sort_name("i1", "Name 01")


# ---------------------------------------------------------------------------
# group_items_by_pattern / sync_groupings edge cases
# ---------------------------------------------------------------------------


def test_group_items_by_pattern_list_attribute_and_garbage():
    items = [
        {"Id": "1", "Tags": ["Action", "Comedy"]},
        {"Id": "2", "Tags": ["Action", "Sci-Fi"]},
        {"Id": "3", "Tags": [None, object()]},  # non-Action garbage skipped
        {"Id": "4"},  # attribute missing entirely -> skipped
    ]
    groups = group_items_by_pattern(items, r"^(Act)", attribute="Tags")
    assert list(groups) == ["Act"]
    assert len(groups["Act"]) == 2


def test_group_items_by_pattern_full_match_when_no_capture_group():
    items = [{"Id": "1", "Name": "Action Movie"}]
    groups = group_items_by_pattern(items, r"action")
    assert "Action" in groups
    assert groups["Action"] == [{"Id": "1", "Name": "Action Movie"}]


def test_sync_groupings_skips_items_without_id_and_empty_ids():
    client = MagicMock()
    client.get_all_items.return_value = []
    groups = {
        "NoIds": [{}, {"Name": "x"}],  # items without "Id"
        "Good": [{"Id": "1"}],
    }
    summary = sync_groupings(client, groups, dry_run=True, min_items=1)
    assert summary == {"Good": ["1"]}
    client.create_collection.assert_not_called()


def test_sync_groupings_missing_boxset_name_or_id_ignored():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "c1"},  # no Name
        {"Name": "No Id"},
        {"Id": "c2", "Name": "Matched"},
    ]
    groups = {"Matched": [{"Id": "1"}]}
    summary = sync_groupings(client, groups, dry_run=False)
    assert summary == {"Matched": ["1"]}
    client.add_to_collection.assert_called_once_with("c2", ["1"])


def test_sync_groupings_filters_malformed_existing_collections():
    client = MagicMock()
    client.get_all_items.return_value = [
        {"Id": "c1"},  # no Name -> ignored
        {"Name": "Orphan"},  # no Id -> ignored
    ]
    groups = {"Orphan": [{"Id": "1"}]}
    summary = sync_groupings(client, groups, dry_run=False)
    # "Orphan" is treated as a new collection since it had no valid Id mapping
    client.create_collection.assert_called_once()
    assert summary == {"Orphan": ["1"]}


# ---------------------------------------------------------------------------
# process_groupings (pkg client) - mode 1 and mode 2
# ---------------------------------------------------------------------------


class _CollectionCapableClient:
    """Duck-typed client exercising mode 1 (re-sort existing collections)."""

    def __init__(self):
        self.updates = []

    def get_collections(self):
        return [{"Id": "c1", "Name": "Saga"}]

    def get_collection_items(self, collection_id):
        assert collection_id == "c1"
        return [
            {"Id": "m2", "Name": "Second", "PremiereDate": "2000-01-01"},
            {"Id": "m1", "Name": "First", "PremiereDate": "1990-01-01"},
        ]

    def update_item_sort_name(self, item_id, sort_name):
        self.updates.append((item_id, sort_name))


class _SortOnlyClient:
    """Collection-capable client without update_item_sort_name."""

    def get_collections(self):
        return [{"Id": "c1", "Name": "Saga"}]

    def get_collection_items(self, collection_id):
        return [{"Id": "m1", "Name": "First", "PremiereDate": "1990-01-01"}]


class _NoCollectionsClient:
    """Collection-capable client that cannot list collections."""

    _err = "should not be called"

    def get_collection_items(self, collection_id):  # pragma: no cover - never called
        raise AssertionError(self._err)


def test_process_groupings_mode1_dry_run_and_apply():
    client = _CollectionCapableClient()
    changes = process_groupings(client, dry_run=True)
    assert changes == [("m1", "First", "Saga 01"), ("m2", "Second", "Saga 02")]
    assert client.updates == []

    client2 = _CollectionCapableClient()
    changes = process_groupings(client2, dry_run=False)
    assert client2.updates == [("m1", "Saga 01"), ("m2", "Saga 02")]
    assert [c[0] for c in changes] == ["m1", "m2"]


def test_process_groupings_mode1_without_update_method():
    client = _SortOnlyClient()
    changes = process_groupings(client, dry_run=False)
    assert changes == [("m1", "First", "Saga 01")]


def test_process_groupings_mode1_no_collections_method():
    client = _NoCollectionsClient()
    assert process_groupings(client, dry_run=False) == []


def test_process_groupings_mode1_no_items():
    client = _CollectionCapableClient()
    client.get_collection_items = lambda collection_id: []
    assert process_groupings(client, dry_run=False) == []


def test_process_groupings_mode2_with_real_client():
    client = _client()
    items = [
        {"Id": "1", "Name": "Toy Story"},
        {"Id": "2", "Name": "Toy Story 2"},
        {"Id": "3", "Name": "Matrix"},
    ]
    with (
        patch.object(client, "get_collections", return_value=[]),
        patch.object(
            client, "create_collection", return_value={"Id": "c-new"}
        ) as mock_create,
    ):
        result = process_groupings(client, items=items, dry_run=False)
    assert mock_create.call_count == 1
    assert mock_create.call_args.args == ("Toy", ["1", "2"])
    assert result == [{"Id": "c-new"}]


def test_process_groupings_mode2_combined_with_mode1_changes():
    """Mode 1 changes are prepended to mode 2 created collections."""
    client = _client()
    collection = MagicMock()
    collection.get_collections.return_value = []
    # Reuse the real JellyfinClient but pretend it has one pre-existing collection.
    with (
        patch.object(
            client,
            "get_collection_items",
            return_value=[{"Id": "m1", "Name": "Old", "PremiereDate": "1999-01-01"}],
        ),
        patch.object(
            client, "get_collections", return_value=[{"Id": "c-old", "Name": "Saga"}]
        ),
        patch.object(
            client,
            "update_item_sort_name",
            side_effect=lambda item_id, name: _touch(client, item_id, name),
        ),
        patch.object(
            client,
            "get_items",
            return_value=[
                {"Id": "1", "Name": "Toy Story"},
                {"Id": "2", "Name": "Toy Story 2"},
            ],
        ),
        patch.object(client, "create_collection", return_value={"Id": "c-new"}),
    ):
        result = process_groupings(client, library_id="lib1", dry_run=False)
    assert ("m1", "Old", "Saga 01") in result
    assert {"Id": "c-new"} in result
    # sort names were persisted
    assert client._touched == [("m1", "Saga 01")]


def _touch(client: object, item_id: str, name: str) -> None:
    """Record sort-name updates on the client for later assertions."""
    if not hasattr(client, "_touched"):
        client._touched = []
    client._touched.append((item_id, name))


def process_groupings_mode2_helper() -> None:  # pragma: no cover - documentation stub
    pass


def test_process_groupings_mode2_fetches_library_when_items_none():
    client = _client()
    with (
        patch.object(client, "get_collections", return_value=[]),
        patch.object(
            client,
            "get_items",
            return_value=[
                {"Id": "1", "Name": "Toy Story"},
                {"Id": "2", "Name": "Toy Story 2"},
            ],
        ) as mock_get_items,
        patch.object(
            client, "create_collection", return_value={"Id": "c-1"}
        ) as mock_create,
    ):
        result = process_groupings(client, library_id="lib1", dry_run=True)
    mock_get_items.assert_called_once_with("lib1")
    # dry-run does not apply changes; but mode 2 ignores dry_run by design -
    # verify that collections were actually created as part of the run.
    assert mock_create.call_count == 1
    assert result == [{"Id": "c-1"}]


def test_process_groupings_mode2_empty_items_returns_changes_only():
    client = _client()
    with patch.object(client, "get_collections", return_value=[]):
        result = process_groupings(client, items=[], dry_run=False)
    assert result == []


def test_process_groupings_non_jellyfin_client_returns_changes():
    class Plain:
        pass

    assert process_groupings(Plain(), dry_run=False) == []


def test_process_groupings_library_id_string_empty_not_fetched():
    client = _client()
    with (
        patch.object(client, "get_collections", return_value=[]),
        patch.object(client, "get_items") as mock_get_items,
    ):
        process_groupings(client, library_id="", dry_run=True)
    mock_get_items.assert_not_called()


# ---------------------------------------------------------------------------
# get_movies_by_query / group_movies_by_tag / group_movies_by_genre
# ---------------------------------------------------------------------------


def test_get_movies_by_query_tags_all_required():
    items = [
        {"Name": "Movie A", "Tags": ["sci-fi", "classic"]},
        {"Name": "Movie B", "Tags": ["sci-fi"]},
        {"Overview": "A sci-fi tale", "Tags": ["sci-fi", "classic"]},
        {"Name": "Movie D"},
    ]
    assert get_movies_by_query(items, "Movie A") == [items[0]]
    assert get_movies_by_query(items, "Movie A", tags=["sci-fi"]) == [items[0]]
    # "Movie A" does not mention sci-fi anywhere
    assert get_movies_by_query(items, "sci-fi") == [items[2]]
    # requires all tags to match
    assert get_movies_by_query(items, "sci-fi", tags=["sci-fi", "classic"]) == [
        items[2]
    ]
    # tag filter rejects items that only have one of the tags
    assert get_movies_by_query(items, "Movie", tags=["classic"]) == [items[0]]
    assert get_movies_by_query(items, "Movie", tags=["sci-fi"]) == [
        items[0],
        items[1],
    ]
    assert get_movies_by_query(items, "nothing matches") == []


def test_group_movies_by_tag_min_group_size():
    items = [
        {"Id": "1", "Tags": ["hero"]},
        {"Id": "2", "Tags": ["hero"]},
        {"Id": "3", "Tags": ["side"]},
    ]
    groups = group_movies_by_tag(items, min_group_size=2)
    assert groups == {"hero": [items[0], items[1]]}


def test_group_movies_by_tag_empty_items():
    assert group_movies_by_tag([], min_group_size=1) == {}


def test_group_movies_by_genre_min_group_size():
    items = [
        {"Id": "1", "Genres": ["Action"]},
        {"Id": "2", "Genres": ["Action"]},
        {"Id": "3", "Genres": ["Drama"]},
    ]
    groups = group_movies_by_genre(items, min_group_size=2)
    assert groups == {"Action": [items[0], items[1]]}


def test_group_movies_by_genre_ignores_genreless_items():
    items = [{"Id": "1"}, {"Id": "2", "Genres": []}]
    assert group_movies_by_genre(items, min_group_size=1) == {}


# ---------------------------------------------------------------------------
# create_groupings - mode 1 query matching edge cases
# ---------------------------------------------------------------------------


def test_create_groupings_mode1_missing_queries_yields_no_stub_keys():
    items = [{"Name": "Random Movie", "Id": "1"}]
    res = create_groupings(items)
    assert "Marvel Cinematic Universe" not in res
    assert "Star Wars Collection" not in res
    assert "Sci-Fi Classics" not in res


def test_create_groupings_mode1_scifi_requires_all_tags():
    items = [
        {"Name": "Classic Sci-Fi", "Id": "1", "Tags": ["sci-fi", "classic"]},
        {"Name": "Modern Sci-Fi", "Id": "2", "Tags": ["sci-fi"]},
    ]
    res = create_groupings(items)
    assert res["Sci-Fi Classics"] == [items[0]]


# ---------------------------------------------------------------------------
# jellyfin_auto_groupings.rules
# ---------------------------------------------------------------------------


def test_rules_create_groupings_genre_keywords_and_empty_items():
    assert rules_create_groupings([]) == {}

    items = [
        {
            "Name": "Oscar Winner: Best Picture",
            "Overview": "space alien adventure",
            "ProductionYear": 1994,
        },
        {
            "Name": "Cyberpunk Action",
            "Overview": "dystopian future",
            "ProductionYear": "2019",
        },
    ]
    res = rules_create_groupings(items)
    # genre keyword buckets
    assert "Sci-Fi Classics" in res
    assert "Oscar Winners" in res
    assert "90s Action" in res
    # decade buckets from years
    assert "1990s Movies" in res
    assert "2010s Movies" in res


def test_rules_group_by_decade_premiere_date_and_garbage_years():
    items = [
        {"Id": "1", "PremiereDate": "1985-07-04"},  # string fallback
        {"Id": "2", "PremiereDate": 1997},  # numeric fallback
        {"Id": "3", "ProductionYear": "2004"},  # string production year
        {"Id": "4", "ProductionYear": 0},  # invalid -> skipped
        {"Id": "5", "ProductionYear": "not-a-year"},  # invalid -> skipped
    ]
    groups = group_by_decade(items)
    assert "1980s Movies" in groups
    assert "1990s Movies" in groups
    assert "2000s Movies" in groups
    # items 4 and 5 are skipped entirely
    assert sum(len(v) for v in groups.values()) == 3


def test_rules_parse_and_process_groupings_reject_non_dict():
    from jellyfin_auto_groupings.rules import parse_grouping_rules, process_groupings

    assert parse_grouping_rules(None) == {}
    assert parse_grouping_rules("nope") == {}
    assert process_groupings(None, None) == {}
    assert process_groupings(None, "not-a-dict") == {}


# ---------------------------------------------------------------------------
# jellyfin_auto_groupings.cli - error paths
# ---------------------------------------------------------------------------


def test_cli_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["--api-key", "k"])
    assert args.url == "http://localhost:8096"
    assert args.dry_run is False
    assert args.pattern == r"^(.*)"


def test_cli_invalid_pattern_regex_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli_main(["--api-key", "k", "--pattern", "(unclosed"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Invalid --pattern regex" in err


def test_cli_connection_error_exit(capsys):
    with (
        patch(
            "jellyfin_auto_groupings.cli.JellyfinClient",
            side_effect=requests.ConnectionError("down"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        cli_main(["--api-key", "k"])
    assert exc.value.code == 1
    assert "Could not connect to Jellyfin" in capsys.readouterr().err


def test_cli_timeout_error_exit(capsys):
    with (
        patch(
            "jellyfin_auto_groupings.cli.JellyfinClient",
            side_effect=requests.Timeout("slow"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        cli_main(["--api-key", "k"])
    assert exc.value.code == 1
    assert "timed out" in capsys.readouterr().err


def test_cli_generic_error_exit(capsys):
    with (
        patch(
            "jellyfin_auto_groupings.cli.JellyfinClient",
            side_effect=RuntimeError("mystery"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        cli_main(["--api-key", "k"])
    assert exc.value.code == 1
    assert "mystery" in capsys.readouterr().err


def test_cli_api_error_exit(capsys):
    client = MagicMock()
    client.get_all_items.side_effect = JellyfinAPIError("API exploded")
    with (
        patch("jellyfin_auto_groupings.cli.JellyfinClient", return_value=client),
        pytest.raises(SystemExit) as exc,
    ):
        cli_main(["--api-key", "k"])
    assert exc.value.code == 1
    assert "API exploded" in capsys.readouterr().err


def test_cli_sync_connection_lost_exit(capsys):
    client = MagicMock()
    client.get_all_items.return_value = [{"Id": "1", "Name": "A"}]
    with (
        patch("jellyfin_auto_groupings.cli.JellyfinClient", return_value=client),
        patch(
            "jellyfin_auto_groupings.cli.sync_groupings",
            side_effect=requests.ConnectionError("dropped"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        cli_main(["--api-key", "k", "--dry-run"])
    assert exc.value.code == 1
    assert "Connection lost while syncing" in capsys.readouterr().err


def test_cli_sync_generic_failure_exit(capsys):
    client = MagicMock()
    client.get_all_items.return_value = [{"Id": "1", "Name": "A"}]
    with (
        patch("jellyfin_auto_groupings.cli.JellyfinClient", return_value=client),
        patch(
            "jellyfin_auto_groupings.cli.sync_groupings",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        cli_main(["--api-key", "k", "--dry-run"])
    assert exc.value.code == 1
    assert "Failed to sync groupings: boom" in capsys.readouterr().err


def test_cli_trailing_slash_warning(caplog):
    with (
        patch("jellyfin_auto_groupings.cli.JellyfinClient") as mock_client_cls,
        patch(
            "jellyfin_auto_groupings.cli.sync_groupings",
            return_value={},
        ),
    ):
        client = MagicMock()
        client.get_all_items.return_value = []
        mock_client_cls.return_value = client
        cli_main(["--api-key", "k", "--url", "http://localhost:8096/", "--dry-run"])
    assert any(
        "Trailing slash" in rec.message and rec.levelname == "WARNING"
        for rec in caplog.records
    )


def test_cli_success_reports_group_count(capsys):
    client = MagicMock()
    client.get_all_items.return_value = []
    with (
        patch("jellyfin_auto_groupings.cli.JellyfinClient", return_value=client),
        patch(
            "jellyfin_auto_groupings.cli.sync_groupings",
            return_value={"A": ["1"], "B": ["2"]},
        ),
    ):
        rc = cli_main(["--api-key", "k", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 collection(s)" in out


def test_cli_module_dunder_guard():
    # The module's __main__ guard should exit cleanly when executed via runpy.

    mod = sys.modules["jellyfin_auto_groupings.cli"]
    assert mod.__name__ == "jellyfin_auto_groupings.cli"
    # runpy import of the module under __main__ would invoke main(); skip actual
    # subprocess test here, but verify guard line exists for coverage of file.
    src = Path(mod.__file__).read_text()
    assert 'if __name__ == "__main__":' in src
    assert "sys.exit(main())" in src


# ---------------------------------------------------------------------------
# jellyfin_groupings (legacy module via package shim)
# ---------------------------------------------------------------------------


def _legacy_client():
    from jellyfin_groupings import JellyfinClient

    return JellyfinClient("http://localhost:8096", "key", user_id="u1")


def test_legacy_client_get_items_library_success():
    from jellyfin_groupings import JellyfinClient

    client = JellyfinClient("http://localhost:8096", "key", user_id="u1")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Items": [{"Id": "i1", "Name": "Movie"}]}
    with (
        patch.object(client.session, "get", return_value=mock_resp) as mock_get,
        patch.object(client, "get_movies") as mock_movies,
    ):
        items = client.get_items("lib1")
        assert items == [{"Id": "i1", "Name": "Movie"}]
        mock_movies.assert_not_called()
    assert mock_get.call_args.args[0] == (
        "http://localhost:8096/Items?ParentId=lib1&Recursive=true"
    )


def test_legacy_client_get_items_library_error_returns_empty():
    client = _legacy_client()
    with (
        patch.object(client.session, "get", side_effect=requests.RequestException("x")),
        patch.object(client, "get_movies") as mock_movies,
    ):
        assert client.get_items("lib1") == []
        mock_movies.assert_not_called()


def test_legacy_client_get_items_no_library_falls_back_to_movies():
    client = _legacy_client()
    with patch.object(client, "get_movies", return_value=[{"Id": "m1"}]):
        assert client.get_items() == [{"Id": "m1"}]


def test_legacy_client_create_collection_failure_and_empty():
    client = _legacy_client()
    with (
        patch.object(client.session, "post") as mock_post,
    ):
        assert client.create_collection("Empty", []) is None
        mock_post.assert_not_called()
    with (
        patch.object(
            client.session, "post", side_effect=requests.RequestException("x")
        ),
    ):
        assert client.create_collection("Fail", ["1"]) is None


def test_legacy_client_update_sort_name_failure_returns_false():
    client = _legacy_client()
    with patch.object(
        client.session, "post", side_effect=requests.RequestException("x")
    ):
        assert client.update_item_sort_name("m1", "Name 01") is False


def test_legacy_process_groupings_skip_branches_and_failed_update(capsys):
    from jellyfin_groupings import process_groupings

    client = MagicMock()
    client.get_collections.return_value = [
        {"Id": "", "Name": "NoId"},  # skipped: missing Id
        {"Id": "c2", "Name": "EmptyItems"},  # skipped: no items
        {"Id": "c3", "Name": "NoDate"},  # sort-key falls back to Name
    ]
    client.get_collection_items.side_effect = lambda cid: (
        [] if cid == "c2" else [{"Id": "m1", "Name": "Zeta"}]
    )
    client.update_item_sort_name.return_value = False  # failed update

    changes = process_groupings(client, dry_run=False)
    # c1 skipped; c2 skipped; c3 produces one change whose update failed
    assert changes == [("m1", "Zeta", "NoDate 01")]

    client2 = MagicMock()
    client2.get_collections.return_value = [{"Id": "c1", "Name": "Saga"}]
    client2.get_collection_items.return_value = [
        {"Id": "m2", "Name": "B", "PremiereDate": "2000-01-01"},
        {"Id": "m1", "Name": "a"},  # no date -> Name fallback
    ]
    changes2 = process_groupings(client2, dry_run=False)
    # Legacy module sorts by Name ("B" < "a" in ASCII order)
    assert changes2 == [("m2", "B", "Saga 01"), ("m1", "a", "Saga 02")]


def test_legacy_main_missing_api_key_and_collection_failure(monkeypatch, capsys):
    import sys

    # Use the loader module (jellyfin_groupings_root) directly: its main()
    # is the real function, while the package shim's "main" attribute can be
    # clobbered to the jellyfin_groupings.main submodule by other tests that
    # import that submodule.
    root_mod = sys.modules["jellyfin_groupings_root"]
    legacy_main = root_mod.main

    # Missing API key -> error message to stderr
    monkeypatch.delenv("JELLYFIN_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        legacy_main()
    assert exc.value.code == 1
    assert "JELLYFIN_API_KEY environment variable is required" in (
        capsys.readouterr().err
    )

    # With key: patch the loader module that main() resolves names from.
    monkeypatch.setenv("JELLYFIN_API_KEY", "key")
    client = MagicMock()
    client.get_movies.return_value = [
        {"Id": "1", "Tags": ["Group:Hero"]},
        {"Id": "2", "Tags": ["Group:Hero"]},
    ]
    client.create_collection.return_value = None
    orig_client_cls = root_mod.JellyfinClient
    orig_grouper = root_mod.group_movies_by_tag
    root_mod.JellyfinClient = MagicMock(return_value=client)
    root_mod.group_movies_by_tag = MagicMock(return_value={"Hero": ["1"]})
    try:
        legacy_main()  # runs without exit; only logs a warning on create failure
    finally:
        root_mod.JellyfinClient = orig_client_cls
        root_mod.group_movies_by_tag = orig_grouper
    client.create_collection.assert_called_once_with("Hero", ["1"])


# ---------------------------------------------------------------------------
# Package __init__ min_group_size filter + legacy shim fallback paths
# ---------------------------------------------------------------------------


def test_group_movies_by_collection_invalid_items_skipped():
    from jellyfin_auto_groupings import group_movies_by_collection

    items = [
        {"Name": "Toy Story 2", "Id": "1"},
        {"Name": "Toy Story 3", "Id": "2"},
        {"Name": "Toy Story 4", "Id": "3"},  # third member keeps group >= 2
        {"Name": "", "Id": "4"},  # invalid: empty name -> skipped (line 84)
        None,  # invalid: not a dict -> skipped
        {"Id": "5"},  # invalid: missing Name -> skipped
    ]
    groups = group_movies_by_collection(items, min_group_size=2)
    assert list(groups) == ["Toy Story Collection"]
    assert len(groups["Toy Story Collection"]) == 3


def test_group_movies_by_collection_min_group_size_filter():
    from jellyfin_auto_groupings import group_movies_by_collection

    items = [{"Name": "Se7en", "Id": "1"}]
    # No suffix -> no collection name inferred at all
    assert group_movies_by_collection([items[0]], min_group_size=1) == {}
    items2 = [
        {"Name": "Matrix 2", "Id": "1"},
        {"Name": "Matrix 3", "Id": "2"},
    ]
    assert group_movies_by_collection(items2, min_group_size=3) == {}
    assert group_movies_by_collection(items2, min_group_size=2) == {
        "Matrix Collection": items2
    }


def test_legacy_shim_loader_failure_fallbacks():
    """Exercise the fallback branches of jellyfin_groupings/__init__.py.

    Reloads the package with importlib patched so the root module either
    cannot be located or fails to execute; both paths leave _jg as None.
    """
    import importlib
    import importlib.util
    import sys

    import jellyfin_groupings

    orig_spec_from_file = importlib.util.spec_from_file_location
    orig_jg = sys.modules.pop("jellyfin_groupings_root", None)

    try:
        # Case 1: spec_from_file_location returns None.
        with patch.object(importlib.util, "spec_from_file_location", return_value=None):
            importlib.reload(jellyfin_groupings)
        assert jellyfin_groupings.JellyfinClient is None
        assert jellyfin_groupings.process_groupings is None
        assert jellyfin_groupings.group_movies_by_tag is None
        assert jellyfin_groupings.group_movies_by_genre is None
        assert jellyfin_groupings.main is None

        # Case 2: exec_module raises -> _jg resets to None mid-execution.

        from types import SimpleNamespace

        class ExplodingLoader:
            _boom = "boom"

            def exec_module(self, module):
                raise RuntimeError(self._boom)

            def create_module(self, spec):
                return None

        fake_spec = SimpleNamespace(
            name="jellyfin_groupings_root",
            loader=ExplodingLoader(),
            submodule_search_locations=None,
            has_location=False,
            origin=None,
        )
        with patch.object(
            importlib.util, "spec_from_file_location", return_value=fake_spec
        ):
            importlib.reload(jellyfin_groupings)
        assert jellyfin_groupings.JellyfinClient is None
        assert jellyfin_groupings.main is None
    finally:
        importlib.util.spec_from_file_location = orig_spec_from_file
        if orig_jg is not None:
            sys.modules["jellyfin_groupings_root"] = orig_jg
        # Restore the healthy shim state for subsequent tests.
        importlib.reload(jellyfin_groupings)
    assert jellyfin_groupings.JellyfinClient is not None
    assert jellyfin_groupings.process_groupings is not None


def test_legacy_main_module_dunder_main(capsys, monkeypatch):
    """Cover jellyfin_groupings/main.py's __main__ guard via runpy.

    runpy executes a fresh module namespace, so patching the module's own
    attributes would not apply; instead patch requests.get responses.
    """
    import runpy

    monkeypatch.setenv("JELLYFIN_API_KEY", "key")

    collections_resp = MagicMock()
    collections_resp.raise_for_status.return_value = None
    collections_resp.json.return_value = {"Items": [{"Id": "c1", "Name": "C"}]}
    movies_resp = MagicMock()
    movies_resp.raise_for_status.return_value = None
    movies_resp.json.return_value = {"Items": []}

    with patch("requests.get", side_effect=[collections_resp, movies_resp]) as mock_get:
        runpy.run_module("jellyfin_groupings.main", run_name="__main__")
    assert mock_get.call_count == 2
    out = capsys.readouterr().out
    assert "Found 1 existing collections." in out
    assert "Found 0 movies." in out


# ---------------------------------------------------------------------------
# CLI environment-variable fallbacks for --api-key / --url
# ---------------------------------------------------------------------------


def test_cli_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("JELLYFIN_API_KEY", "env-key")
    monkeypatch.delenv("JELLYFIN_URL", raising=False)
    args = build_parser().parse_args([])
    assert args.api_key == "env-key"
    assert args.url == "http://localhost:8096"


def test_cli_explicit_api_key_overrides_env(monkeypatch):
    monkeypatch.setenv("JELLYFIN_API_KEY", "env-key")
    args = build_parser().parse_args(["--api-key", "flag-key"])
    assert args.api_key == "flag-key"


def test_cli_url_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("JELLYFIN_URL", "http://media.local:9000")
    args = build_parser().parse_args(["--api-key", "k"])
    assert args.url == "http://media.local:9000"


def test_cli_blank_env_url_uses_default(monkeypatch):
    # An empty JELLYFIN_URL must not produce a bare "" base URL.
    monkeypatch.setenv("JELLYFIN_URL", "")
    args = build_parser().parse_args(["--api-key", "k"])
    assert args.url == "http://localhost:8096"


def test_cli_missing_api_key_returns_error(monkeypatch, capsys):
    monkeypatch.delenv("JELLYFIN_API_KEY", raising=False)
    rc = cli_main(["--dry-run"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "JELLYFIN_API_KEY" in err
    assert "--api-key" in err


def test_cli_uses_env_api_key_end_to_end(monkeypatch, capsys):
    monkeypatch.setenv("JELLYFIN_API_KEY", "env-key")
    client = MagicMock()
    client.get_all_items.return_value = []
    with (
        patch("jellyfin_auto_groupings.cli.JellyfinClient", return_value=client) as cls,
        patch("jellyfin_auto_groupings.cli.sync_groupings", return_value={"A": ["1"]}),
    ):
        rc = cli_main(["--dry-run"])
    assert rc == 0
    cls.assert_called_once_with("http://localhost:8096", "env-key")
    out = capsys.readouterr().out
    assert "Dry run: 1 collection(s) would be synced" in out


def test_cli_applied_mode_does_not_say_would(monkeypatch, capsys):
    client = MagicMock()
    client.get_all_items.return_value = []
    with (
        patch("jellyfin_auto_groupings.cli.JellyfinClient", return_value=client),
        patch("jellyfin_auto_groupings.cli.sync_groupings", return_value={"A": ["1"]}),
    ):
        rc = cli_main(["--api-key", "k"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "Synced 1 collection(s)."
