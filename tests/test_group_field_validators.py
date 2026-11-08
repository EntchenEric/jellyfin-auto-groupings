"""Direct unit tests for the ``POST /api/config`` group-field validators.

``_validate_group_types`` and ``_validate_group_rules`` run on every config
save, but only their happy path was exercised: a typo in ``source_type``,
``sort_order``, a seasonal date or a complex-query rule used to be saved
silently and fail later at sync time. Calling the validators directly pins
each rejection without staging a full HTTP save.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes


def _collect(group: dict) -> list[str]:
    errors: list[str] = []
    routes._validate_group_types(group, "groups[0]", errors)
    return errors


def test_an_unknown_source_type_is_rejected():
    errors = _collect({"source_type": "pLEX_LIST"})

    assert any("source_type must be one of" in e for e in errors)


def test_a_known_source_type_passes():
    assert _collect({"source_type": "genre"}) == []


def test_an_unknown_sort_order_is_rejected():
    errors = _collect({"sort_order": "newest_first_please"})

    assert any("sort_order must be one of" in e for e in errors)


def test_a_known_sort_order_passes():
    assert _collect({}) == []


def test_a_non_string_seasonal_date_is_rejected():
    errors = _collect({"seasonal_start": 1031})

    assert any("seasonal_start must be a string" in e for e in errors)


def test_an_impossible_seasonal_date_is_rejected():
    errors = _collect({"seasonal_end": "13-45"})

    assert any("seasonal_end" in e for e in errors)


def test_a_real_seasonal_date_passes():
    assert _collect({"seasonal_start": "10-31", "seasonal_end": "02-29"}) == []


def test_a_non_list_rules_field_is_rejected():
    errors = _collect({"rules": {"operator": "AND"}})

    assert errors == ["groups[0].rules must be a list"]


def test_a_non_dict_rule_entry_is_rejected():
    errors: list[str] = []
    routes._validate_group_rules([42], "groups[0]", errors)

    assert errors == ["groups[0].rules[0] must be an object"]


def test_a_rule_with_wrong_field_types_is_rejected():
    errors: list[str] = []
    routes._validate_group_rules(
        [{"type": 1, "operator": [], "not": "yes"}],
        "groups[0]",
        errors,
    )

    joined = " | ".join(errors)
    for field in (".type", ".operator", ".not"):
        assert f"rules[0]{field}" in joined


def test_a_well_formed_rule_passes():
    errors: list[str] = []
    routes._validate_group_rules(
        [{"operator": "AND", "type": "genre", "value": "Action", "not": True}],
        "groups[0]",
        errors,
    )

    assert errors == []
