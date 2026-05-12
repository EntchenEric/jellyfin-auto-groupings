"""Tests for metadata rule parsing used in grouping filters.

The JS frontend parses filter strings like "Horror AND Action AND NOT Comedy".
These tests verify the Python-side logic for parsing and filtering rules.
"""

import pytest

# Replicating the frontend's parseMetadataValue logic in Python for testing
# the algorithm's correctness (the backend sync engine applies these rules).

import re


def parse_metadata_value(val_str):
    """Python equivalent of parseMetadataValue from metadata.js."""
    if not val_str or val_str.strip() == "":
        return [{"operator": "", "value": ""}]

    pattern = r"\s+(AND NOT|OR NOT|AND|OR)\s+"
    parts = re.split(pattern, val_str, flags=re.IGNORECASE)
    rules = []

    def parse_rule(s):
        s = s.strip()
        match = re.match(r"^(\w+):(.+)$", s)
        if match:
            return {"type": match.group(1), "value": match.group(2).strip()}
        return {"value": s}

    first = parse_rule(parts[0])
    rules.append({"operator": "", **first})

    for i in range(1, len(parts), 2):
        rest = parse_rule(parts[i + 1])
        op = parts[i].strip().upper().replace(r"\s+", " ")
        rules.append({"operator": op, **rest})

    return rules


class TestParseMetadataValue:
    """Tests for the metadata filter string parser."""

    def test_single_value(self):
        result = parse_metadata_value("Horror")
        assert len(result) == 1
        assert result[0]["value"] == "Horror"
        assert result[0]["operator"] == ""

    def test_and_operator(self):
        result = parse_metadata_value("Horror AND Action")
        assert len(result) == 2
        assert result[0]["value"] == "Horror"
        assert result[0]["operator"] == ""
        assert result[1]["value"] == "Action"
        assert result[1]["operator"] == "AND"

    def test_or_operator(self):
        result = parse_metadata_value("Horror OR Comedy")
        assert len(result) == 2
        assert result[0]["value"] == "Horror"
        assert result[1]["value"] == "Comedy"
        assert result[1]["operator"] == "OR"

    def test_and_not_operator(self):
        result = parse_metadata_value("Action AND NOT Romance")
        assert len(result) == 2
        assert result[1]["value"] == "Romance"
        assert result[1]["operator"] == "AND NOT"

    def test_or_not_operator(self):
        result = parse_metadata_value("Action OR NOT Horror")
        assert len(result) == 2
        assert result[1]["value"] == "Horror"
        assert result[1]["operator"] == "OR NOT"

    def test_complex_type_with_prefix(self):
        result = parse_metadata_value("genre:Action AND actor:Tom Hanks")
        assert len(result) == 2
        assert result[0]["type"] == "genre"
        assert result[0]["value"] == "Action"
        assert result[1]["type"] == "actor"
        assert result[1]["value"] == "Tom Hanks"
        assert result[1]["operator"] == "AND"

    def test_complex_mixed(self):
        result = parse_metadata_value("genre:Sci-Fi AND studio:Pixar OR NOT tag:Anime")
        assert len(result) == 3
        assert result[0]["value"] == "Sci-Fi"
        assert result[1]["value"] == "Pixar"
        assert result[1]["operator"] == "AND"
        assert result[2]["value"] == "Anime"
        assert result[2]["operator"] == "OR NOT"

    def test_empty_string(self):
        result = parse_metadata_value("")
        assert len(result) == 1
        assert result[0]["value"] == ""

    def test_none_value(self):
        result = parse_metadata_value(None)
        assert len(result) == 1
        assert result[0]["value"] == ""

    def test_case_insensitive_operators(self):
        result = parse_metadata_value("action and comedy")
        assert len(result) == 2
        assert result[1]["operator"] == "AND"

    def test_whitespace_normalization(self):
        result = parse_metadata_value("Horror    AND     Action")
        assert len(result) == 2
        assert result[0]["value"] == "Horror"
        assert result[1]["value"] == "Action"
        assert result[1]["operator"] == "AND"

    def test_four_terms_chain(self):
        result = parse_metadata_value(
            "Action AND Sci-Fi OR NOT Romance AND Comedy"
        )
        assert len(result) == 4
        assert result[0]["value"] == "Action"
        assert result[1]["value"] == "Sci-Fi"
        assert result[1]["operator"] == "AND"
        assert result[2]["value"] == "Romance"
        assert result[2]["operator"] == "OR NOT"
        assert result[3]["value"] == "Comedy"
        assert result[3]["operator"] == "AND"

    def test_trailing_spaces(self):
        result = parse_metadata_value("  Horror AND Action  ")
        assert len(result) == 2
        assert result[0]["value"] == "Horror"
        assert result[1]["value"] == "Action"


class TestMetadataStringRoundtrip:
    """Verify the filter string can be reconstructed from parsed rules."""

    def build_filter_string(self, rules, source_type="genre"):
        """Python equivalent of getFilterValue for parsed rules."""
        valid = [r for r in rules if r.get("value", "").strip() != ""]
        if not valid:
            return ""
        parts = []
        for i, r in enumerate(valid):
            prefix = ""
            if source_type == "complex":
                prefix = f"{r.get('type', 'genre')}:"
            if i == 0:
                parts.append(f"{prefix}{r['value'].strip()}")
            else:
                parts.append(f"{r['operator']} {prefix}{r['value'].strip()}")
        return " ".join(parts)

    def test_roundtrip_simple(self):
        original = "Horror AND Action"
        parsed = parse_metadata_value(original)
        rebuilt = self.build_filter_string(parsed)
        assert rebuilt == original

    def test_roundtrip_with_not(self):
        original = "Action AND NOT Romance"
        parsed = parse_metadata_value(original)
        rebuilt = self.build_filter_string(parsed)
        assert rebuilt == original

    def test_roundtrip_complex(self):
        original = "genre:Sci-Fi AND actor:Tom Hanks"
        parsed = parse_metadata_value(original)
        rebuilt = self.build_filter_string(parsed, "complex")
        assert rebuilt == original
