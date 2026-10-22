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


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("AND Action", [("AND", "Action")]),
        ("OR Action", [("OR", "Action")]),
        ("AND NOT Comedy", [("AND NOT", "Comedy")]),
        ("OR NOT Comedy", [("OR NOT", "Comedy")]),
        ("  AND  Action", [("AND", "Action")]),
    ],
)
def test_leading_operator_is_dropped_without_becoming_a_value(query, expected):
    """A leading operator has no left operand, so it must not be a filter value.

    Before this, ``"AND Action"`` became the genre ``"AND Action"``, which
    matched nothing while looking like a valid rule in the UI.
    """
    rules = sync.parse_complex_query(query, "genre")

    assert [(r["operator"], r["value"]) for r in rules] == expected


@pytest.mark.parametrize(
    "query",
    ["Action AND AND Comedy", "Action AND NOT OR Comedy", "Action AND  AND  Comedy"],
)
def test_stacked_operators_collapse_to_the_one_nearest_the_operand(query):
    """Two operators with no operand between them must not make a bogus value."""
    rules = sync.parse_complex_query(query, "genre")

    assert [r["value"] for r in rules] == ["Action", "Comedy"]
    assert all(not r["value"].upper().startswith(("AND", "OR")) for r in rules)


def test_dangling_not_negates_the_preceding_condition_only():
    """``"Action AND NOT"`` has no operand for the NOT, so the NOT is dropped."""
    rules = sync.parse_complex_query("Action AND NOT", "genre")

    assert rules == [{"operator": "AND", "type": "genre", "value": "Action"}]


@pytest.mark.parametrize(
    ("query", "expected_operator"),
    [
        ("NOT NOT Comedy", "AND"),
        ("NOT NOT NOT Comedy", "AND NOT"),
    ],
)
def test_stacked_not_toggles(query, expected_operator):
    """Two negations cancel; three leave the condition negated."""
    rules = sync.parse_complex_query(query, "genre")

    assert rules == [
        {"operator": expected_operator, "type": "genre", "value": "Comedy"},
    ]


@pytest.mark.parametrize("query", ["NOT", "genre:", "AND", "AND NOT", "   OR   "])
def test_operator_only_queries_produce_no_rules(query):
    """A query carrying no operand must not emit an empty filter value."""
    assert sync.parse_complex_query(query, "genre") == []


@pytest.mark.parametrize("value", ["Andor", "Coronation", "Rock and Roll"])
def test_values_containing_operator_substrings_are_not_split(value):
    """``"and"`` inside a word, or an ``and`` in a title, is not an operator."""
    rules = sync.parse_complex_query(value, "genre")

    if " and " in value:
        # A standalone lowercase "and" *is* the operator, matching the
        # case-insensitive behaviour the UI documents.
        assert [r["value"] for r in rules] == ["Rock", "Roll"]
    else:
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
