"""Regression tests for year-source routing and the Jellyfin ``years`` filter.

A ``year`` group is documented as selecting by release year, and
:func:`sync._match_year` implements ``<``, ``<=``, ``>`` and ``>=``
expressions for it.  But the routing only consulted the logical-operator
regex, which never matches a comparison, so ``>=2000`` was forwarded verbatim
to Jellyfin as ``years=>=2000``.  Jellyfin only understands literal years and
comma-separated year lists, so it ignored the unrecognised value and answered
with the unrestricted library — the group silently linked every movie on the
server instead of the ones from 2000 onwards.

Those expressions now route through the local matcher, which already had the
comparison logic.
"""

from __future__ import annotations

import pytest

import sync


def test_year_comparison_never_reaches_the_years_filter(monkeypatch):
    """Neither entry point may forward a comparison as a ``years`` value.

    Jellyfin only understands literal years and comma-separated lists in
    ``years``; anything else is ignored, which silently returns the whole
    library. This asserts on the parameter actually handed to the metadata
    fetcher, which is the layer that builds the ``years`` query value.
    """
    forwarded: list[str] = []

    def _fake_meta(url, source_type, source_value, *args, **kwargs):
        forwarded.append(source_value)
        return [], None, 200

    def _fake_complex(*args, **kwargs):
        return [], None, 200

    monkeypatch.setattr(sync, "_fetch_items_for_metadata_group", _fake_meta)
    monkeypatch.setattr(sync, "_fetch_items_for_complex_group", _fake_complex)

    for value in (">=2000", "<=2010", ">1990", "<2000"):
        sync.preview_group("year", value, "http://jellyfin", "key")
        sync._resolve_group_source(
            {},
            "g",
            "year",
            value,
            "",
            "http://jellyfin",
            "key",
            "",
            "",
            "",
            "",
            None,
        )

    assert forwarded == []


@pytest.mark.parametrize(
    "value",
    [">=2000", "<=2010", ">1990", "<2000", "year:>=2000", "year:1999"],
)
def test_year_expressions_route_to_local_matcher(value):
    """Expressions are evaluated in memory, where operators are understood."""
    assert sync._year_value_needs_local_match("year", value) is True


@pytest.mark.parametrize("value", ["2000", "2000,2001", "2000, 2001", ""])
def test_plain_year_values_stay_server_side(value):
    """Literal years and year lists are exactly what Jellyfin accepts."""
    assert sync._year_value_needs_local_match("year", value) is False


@pytest.mark.parametrize("source_type", ["genre", "tag", "studio", "actor"])
def test_other_source_types_are_unaffected(source_type):
    """Only ``year`` groups are rerouted; the filter stays server-side."""
    assert sync._year_value_needs_local_match(source_type, ">=2000") is False


def test_preview_group_uses_local_matcher_for_year_expression(monkeypatch):
    """The preview must agree with what sync would actually link."""
    seen: dict[str, object] = {}

    def _fake_meta(*args, **kwargs):
        seen["meta"] = (args[1], args[2])
        return [], None, 200

    def _fake_complex(group_name, rules, *args, **kwargs):
        seen["complex"] = rules
        return [], None, 200

    monkeypatch.setattr(sync, "_fetch_items_for_metadata_group", _fake_meta)
    monkeypatch.setattr(sync, "_fetch_items_for_complex_group", _fake_complex)

    sync.preview_group("year", ">=2000", "http://jellyfin", "key")

    assert "meta" not in seen
    assert seen["complex"] == [{"operator": "AND", "type": "year", "value": ">=2000"}]


def test_preview_group_keeps_plain_year_server_side(monkeypatch):
    """A literal year still uses the server-side filter it was written for."""
    seen: dict[str, object] = {}

    def _fake_meta(*args, **kwargs):
        seen["meta"] = (args[1], args[2])
        return [], None, 200

    def _fake_complex(*args, **kwargs):
        seen["complex"] = True
        return [], None, 200

    monkeypatch.setattr(sync, "_fetch_items_for_metadata_group", _fake_meta)
    monkeypatch.setattr(sync, "_fetch_items_for_complex_group", _fake_complex)

    sync.preview_group("year", "2000", "http://jellyfin", "key")

    assert seen == {"meta": ("year", "2000")}


def test_resolve_group_source_uses_local_matcher_for_year_expression(monkeypatch):
    """Sync and preview must resolve a year expression the same way."""
    seen: dict[str, object] = {}

    def _fake_meta(*args, **kwargs):
        seen["meta"] = True
        return [], None, 200

    def _fake_complex(group_name, rules, *args, **kwargs):
        seen["complex"] = rules
        return [], None, 200

    monkeypatch.setattr(sync, "_fetch_items_for_metadata_group", _fake_meta)
    monkeypatch.setattr(sync, "_fetch_items_for_complex_group", _fake_complex)

    sync._resolve_group_source(
        {},
        "g",
        "year",
        ">=2000",
        "",
        "http://jellyfin",
        "key",
        "",
        "",
        "",
        "",
        None,
    )

    assert "meta" not in seen
    assert seen["complex"] == [{"operator": "AND", "type": "year", "value": ">=2000"}]


def test_year_expression_matches_the_documented_semantics():
    """The locally evaluated expression selects exactly the intended years."""
    rules = sync.parse_complex_query(">=2000", "year")

    assert sync._eval_item({"ProductionYear": 2000}, rules) is True
    assert sync._eval_item({"ProductionYear": 2015}, rules) is True
    assert sync._eval_item({"ProductionYear": 1999}, rules) is False
    # A missing year cannot satisfy a range, and must not match by accident.
    assert sync._eval_item({}, rules) is False
