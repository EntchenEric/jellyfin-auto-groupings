import pytest
from sync import sanitize_filename, build_filename, clean_library_name, convert_language_codes

def test_sanitize_filename_edge_cases():
    assert sanitize_filename("") == ""
    assert sanitize_filename(None) == ""
    assert sanitize_filename("   ") == ""
    # Test path traversal prevention
    assert ".." not in sanitize_filename("../../../etc/passwd")
    # Test invalid characters removal
    assert sanitize_filename('Movie: Subtitle / Title? * < > | "') == "Movie_ Subtitle _ Title_ _ _ _ _"

def test_clean_library_name_edge_cases():
    assert clean_library_name("") == ""
    assert clean_library_name("  Action / Sci-Fi  ") == "Action Sci-Fi"
    assert clean_library_name("Sub/Folder/Name") == "Sub/Folder/Name"

def test_build_filename_edge_cases():
    item = {"Name": "Test Movie", "ProductionYear": 2024, "IndexNumber": 1}
    filename = build_filename(item)
    assert "Test Movie (2024) [1].strm" in filename

def test_convert_language_codes_edge_cases():
    assert convert_language_codes([]) == []
    assert convert_language_codes(["en", "de"]) == ["eng", "ger"]
