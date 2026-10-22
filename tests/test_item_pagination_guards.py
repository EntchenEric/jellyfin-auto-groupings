"""Regression tests for the bounded Jellyfin item walkers.

Both walkers advance ``StartIndex`` and trust the server to honour it. When it
does not — a reverse proxy that strips the query parameter, or a Jellyfin build
that ignores it for a query — every request returns the same page and the walk
never terminates: the sync run hangs while the accumulated list grows without
bound. These tests pin the two guards that turn that hang into a truncated
result plus a warning.
"""

import logging

import pytest

import jellyfin
from jellyfin import (
    _MAX_ITEM_PAGES,
    _page_signature,
    _paginate_jellyfin,
    fetch_all_jellyfin_items,
)


def _items(*ids: str) -> list[dict[str, object]]:
    return [{"Id": item_id, "Name": f"Item {item_id}"} for item_id in ids]


# ---------------------------------------------------------------------------
# _page_signature
# ---------------------------------------------------------------------------


def test_page_signature_uses_item_ids():
    assert _page_signature(_items("a", "b")) == ("a", "b")


def test_page_signature_is_none_without_any_id():
    # A page that carries no usable identifier cannot be compared, so the
    # repeat guard must not trip on it.
    assert _page_signature([{"Name": "no id"}, {"Id": ""}]) is None


def test_page_signature_ignores_non_dict_items():
    assert _page_signature([{"Id": "a"}, "junk", None]) == ("a",)  # type: ignore[list-item]


def test_page_signature_empty_page_is_none():
    assert _page_signature([]) is None


# ---------------------------------------------------------------------------
# fetch_all_jellyfin_items
# ---------------------------------------------------------------------------


def test_walk_stops_when_server_repeats_a_page(caplog):
    """A server that ignores ``StartIndex`` must not loop forever."""
    repeated = _items("a", "b")

    def fake_fetch(*_args, **_kwargs):
        return [dict(item) for item in repeated]

    with caplog.at_level(logging.WARNING):
        result = fetch_all_jellyfin_items(
            "http://jf",
            "key",
            limit=2,
            _fetch_page=fake_fetch,
        )

    # The first page is kept; the identical second page ends the walk.
    assert [item["Id"] for item in result] == ["a", "b"]
    assert "same page again" in caplog.text


def test_walk_honours_start_index_across_pages():
    pages = {
        0: _items("a", "b"),
        2: _items("c", "d"),
        4: _items("e"),
    }

    def fake_fetch(_base, _key, params, *, timeout=0):
        # ``fetch_all_jellyfin_items`` builds string-valued query params.
        return pages[int(params["StartIndex"])]

    result = fetch_all_jellyfin_items(
        "http://jf", "key", limit=2, _fetch_page=fake_fetch
    )

    assert [item["Id"] for item in result] == ["a", "b", "c", "d", "e"]


def test_walk_stops_at_page_cap(caplog):
    """A server returning always-new full pages is capped, not unbounded."""
    counter = {"n": 0}

    def fake_fetch(*_args, **_kwargs):
        counter["n"] += 1
        # Unique IDs per call, so the repeat guard never fires and only the
        # page cap can end the walk.
        return _items(*[f"id{counter['n']}-{i}" for i in range(1)])

    with caplog.at_level(logging.WARNING):
        result = fetch_all_jellyfin_items(
            "http://jf",
            "key",
            limit=1,
            _fetch_page=fake_fetch,
        )

    assert len(result) == _MAX_ITEM_PAGES
    assert counter["n"] == _MAX_ITEM_PAGES
    assert "safety limit" in caplog.text


def test_walk_returns_empty_for_empty_first_page():
    def fake_fetch(*_args, **_kwargs):
        return []

    assert fetch_all_jellyfin_items("http://jf", "key", _fetch_page=fake_fetch) == []


# ---------------------------------------------------------------------------
# _paginate_jellyfin
# ---------------------------------------------------------------------------


def _patch_get_json(monkeypatch, responses):
    """Serve *responses* by ``StartIndex`` and record the requested indexes."""
    seen: list[int] = []

    def fake_get_json(_url, *, headers=None, params=None, timeout=0):
        start = params["StartIndex"]
        seen.append(start)
        return responses[start]

    monkeypatch.setattr(jellyfin, "_get_json", fake_get_json)
    return seen


def test_paginate_yields_pages_until_total_record_count(monkeypatch):
    responses = {
        0: {"Items": _items("a", "b"), "TotalRecordCount": 3},
        2: {"Items": _items("c"), "TotalRecordCount": 3},
    }
    seen = _patch_get_json(monkeypatch, responses)

    pages = list(_paginate_jellyfin("http://jf", "key", "Genres", limit=2))

    assert [[item["Id"] for item in page] for page in pages] == [["a", "b"], ["c"]]
    assert seen == [0, 2]


def test_paginate_stops_when_server_repeats_a_page(monkeypatch, caplog):
    """``StartIndex`` being ignored must end the walk, not repeat forever."""
    page = {"Items": _items("a", "b"), "TotalRecordCount": 100}

    def fake_get_json(_url, *, headers=None, params=None, timeout=0):
        return page

    monkeypatch.setattr(jellyfin, "_get_json", fake_get_json)

    with caplog.at_level(logging.WARNING):
        pages = list(_paginate_jellyfin("http://jf", "key", "Genres", limit=2))

    assert len(pages) == 1
    assert "same page again" in caplog.text


def test_paginate_stops_at_page_cap(monkeypatch, caplog):
    counter = {"n": 0}

    def fake_get_json(_url, *, headers=None, params=None, timeout=0):
        counter["n"] += 1
        return {"Items": _items(f"id{counter['n']}"), "TotalRecordCount": 10**9}

    monkeypatch.setattr(jellyfin, "_get_json", fake_get_json)

    with caplog.at_level(logging.WARNING):
        pages = list(_paginate_jellyfin("http://jf", "key", "Genres", limit=1))

    assert len(pages) == _MAX_ITEM_PAGES
    assert "safety limit" in caplog.text


def test_paginate_stops_on_non_list_items(monkeypatch, caplog):
    """A malformed ``Items`` value ends the walk instead of yielding junk."""
    responses = {0: {"Items": "not-a-list", "TotalRecordCount": 5}}
    _patch_get_json(monkeypatch, responses)

    with caplog.at_level(logging.WARNING):
        pages = list(_paginate_jellyfin("http://jf", "key", "Genres", limit=2))

    assert pages == []
    assert "is not a list" in caplog.text


def test_paginate_stops_on_empty_page(monkeypatch):
    responses = {0: {"Items": [], "TotalRecordCount": 0}}
    _patch_get_json(monkeypatch, responses)

    # The walker yields the empty page it saw, then stops — callers already
    # tolerate a trailing empty page.
    assert list(_paginate_jellyfin("http://jf", "key", "Genres", limit=2)) == [[]]


@pytest.mark.parametrize("total", [0, None])
def test_paginate_tolerates_missing_total(monkeypatch, total):
    """Without a usable ``TotalRecordCount`` the short-page rule still ends it."""
    responses = {
        0: {"Items": _items("a", "b"), "TotalRecordCount": total},
        2: {"Items": [], "TotalRecordCount": total},
    }
    _patch_get_json(monkeypatch, responses)

    pages = list(_paginate_jellyfin("http://jf", "key", "Genres", limit=2))

    assert [[item["Id"] for item in page] for page in pages] == [["a", "b"], []]
