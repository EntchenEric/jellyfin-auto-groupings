"""Regression tests for complex-query parsing and year matching edge cases.

Both helpers sit on the boundary between user-entered rule text and the
filter that decides which media gets linked, so malformed input must degrade
to a sensible filter rather than silently matching nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import sync


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Action", [("AND", "genre", "Action")]),
        ("Action AND Comedy", [("AND", "genre", "Action"), ("AND", "genre", "Comedy")]),
        ("Action OR Comedy", [("AND", "genre", "Action"), ("OR", "genre", "Comedy")]),
        (
            "Action AND NOT Comedy",
            [("AND", "genre", "Action"), ("AND NOT", "genre", "Comedy")],
        ),
        ("NOT Comedy", [("AND NOT", "genre", "Comedy")]),
        (
            "actor:Tom Hanks OR actor:Meryl Streep",
            [("AND", "actor", "Tom Hanks"), ("OR", "actor", "Meryl Streep")],
        ),
    ],
)
def test_parse_complex_query_basic_shapes(query, expected):
    rules = sync.parse_complex_query(query, "genre")

    assert [(r["operator"], r["type"], r["value"]) for r in rules] == expected


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_parse_complex_query_rejects_empty_input(query):
    assert sync.parse_complex_query(query, "genre") == []


@pytest.mark.parametrize("query", ["Action AND", "Action OR", "Action AND NOT"])
def test_trailing_operator_does_not_become_a_filter_value(query):
    """A dangling operator must be dropped, not merged into the value.

    Before this, ``"Action AND NOT"`` produced a rule with value ``"not"``,
    which matches no genre at all — the group silently linked nothing.
    """
    rules = sync.parse_complex_query(query, "genre")

    assert rules == [{"operator": "AND", "type": "genre", "value": "Action"}]


@pytest.mark.parametrize("value", ["Rock", "Sand", "Thunder", "Understand"])
def test_titles_resembling_operators_are_preserved(value):
    """Only a *standalone* operator is stripped; substrings stay intact."""
    rules = sync.parse_complex_query(value, "genre")

    assert rules == [{"operator": "AND", "type": "genre", "value": value}]


def test_parse_complex_query_honours_default_type():
    rules = sync.parse_complex_query("Action AND studio:A24", "genre")

    assert rules[0]["type"] == "genre"
    assert rules[1]["type"] == "studio"


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", ">=", ">abc", "<2001.5", "not-a-year", True, ["x"]],
)
def test_match_year_rejects_malformed_expressions(value):
    """A malformed rule value returns False instead of raising."""
    assert sync._match_year(2001, value) is False


@pytest.mark.parametrize(
    ("rule_value", "expected"),
    [
        ("2001", True),
        (2001, True),
        (">2000", True),
        (">=2001", True),
        ("<2001", False),
        ("<=2001", True),
    ],
)
def test_match_year_accepts_numeric_and_range_forms(rule_value, expected):
    assert sync._match_year(2001, rule_value) is expected


def test_match_year_handles_missing_item_year():
    assert sync._match_year(None, "2001") is False


def test_match_condition_survives_none_rule_value():
    """``_match_condition`` is a public-ish boundary; it must not raise."""
    item = {"ProductionYear": 2001}

    assert sync._match_condition(item, "year", None) is False
