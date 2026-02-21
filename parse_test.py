"""
parse_test.py - Unit tests for complex query parsing.
"""

from sync import parse_complex_query

def test_parse_complex_query():
    """Verify that complex textual queries are correctly parsed into structured rules."""
    expected = [
        {"operator": "AND", "type": "genre", "value": "Horror"},
        {"operator": "AND", "type": "genre", "value": "animation"},
        {"operator": "AND NOT", "type": "genre", "value": "comedy"}
    ]
    result = parse_complex_query("Horror AND animation AND NOT comedy", "genre")
    assert result == expected

if __name__ == "__main__":
    test_parse_complex_query()
    print("Test passed!")
