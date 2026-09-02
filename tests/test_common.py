"""Tests for the _common module (shared constants and utilities)."""

import pytest

from _common import (
    COMPLEX_QUERY_SOURCE_TYPES,
    DEFAULT_LIST_FETCH_TIMEOUT,
    DEFAULT_LIST_MAX_PAGES,
    DEFAULT_LIST_PAGE_LIMIT,
    DEFAULT_SCRAPING_HEADERS,
    DEFAULT_SEARCH_ROOTS,
    LIST_SOURCE_TYPES,
    SOURCE_TYPES,
    normalize_group_relpath,
)


class TestNormalizeGroupRelpath:
    """Tests for nested group-name normalisation."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Simple", "Simple"),
            ("Anime/Action", "Anime/Action"),
            ("A/B/C", "A/B/C"),
            ("Anime//Action", "Anime/Action"),
            ("Anime/ Action ", "Anime/Action"),
            ("  Spaced  ", "Spaced"),
            ("Anime\\Action", "Anime/Action"),
            ("/leading/slash", "leading/slash"),
            ("trailing/slash/", "trailing/slash"),
        ],
    )
    def test_accepts_and_normalises(self, raw: str, expected: str) -> None:
        """Valid names normalise to a relative, slash-separated path."""
        assert normalize_group_relpath(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            ".",
            "..",
            "../etc",
            "../../etc/passwd",
            "a/../b",
            "a/./b",
            "with\x00null",
            "/",
            "///",
            # Windows drive-letter absolute paths are rejected rather than
            # being misread as a relative ``C:`` folder.
            "C:\\foo",
            "C:/foo",
            "D:\\a\\b",
            "e:/media/movies",
        ],
    )
    def test_rejects_unsafe_names(self, raw: str) -> None:
        """Empty, relative-traversal and NUL-containing names are rejected."""
        assert normalize_group_relpath(raw) is None

    @pytest.mark.parametrize(
        "raw",
        [
            # A bare drive letter (ambiguous, harmless on POSIX) and names
            # with a colon inside a single segment are still valid relative
            # names and must not be rejected.
            "C:",
            "a:b",
            "A:B",
            "a:b/c",
            "C:foo",
        ],
    )
    def test_accepts_colon_names(self, raw: str) -> None:
        """Colon-containing relative names are not mistaken for drive paths."""
        assert normalize_group_relpath(raw) is not None

    def test_rejects_non_string(self) -> None:
        """Non-string input is rejected rather than raising."""
        assert normalize_group_relpath(None) is None  # type: ignore[arg-type]
        assert normalize_group_relpath(123) is None  # type: ignore[arg-type]

    def test_result_never_escapes_base(self, tmp_path) -> None:
        """Joining the result onto a base never leaves that base."""
        base = tmp_path / "groupings"
        base.mkdir()
        for raw in ("Anime/Action", "/abs/path", "a/b/c", "Anime\\Action"):
            rel = normalize_group_relpath(raw)
            assert rel is not None
            joined = base.joinpath(*rel.split("/")).resolve()
            assert base.resolve() in joined.parents or joined.parent == base.resolve()


class TestSourceTypes:
    """Tests for source type constants."""

    def test_source_types_contains_all_list_types(self) -> None:
        """Every LIST_SOURCE_TYPES entry should also be in SOURCE_TYPES."""
        assert LIST_SOURCE_TYPES.issubset(SOURCE_TYPES)

    def test_source_types_contains_all_complex_types(self) -> None:
        """Every COMPLEX_QUERY_SOURCE_TYPES entry should also be in SOURCE_TYPES."""
        assert COMPLEX_QUERY_SOURCE_TYPES.issubset(SOURCE_TYPES)

    def test_list_and_complex_are_disjoint(self) -> None:
        """List source types and complex-query source types should not overlap."""
        assert LIST_SOURCE_TYPES.isdisjoint(COMPLEX_QUERY_SOURCE_TYPES)

    def test_source_types_contains_general(self) -> None:
        assert "general" in SOURCE_TYPES

    def test_source_types_contains_complex(self) -> None:
        assert "complex" in SOURCE_TYPES

    def test_list_source_types_contains_imdb(self) -> None:
        assert "imdb_list" in LIST_SOURCE_TYPES

    def test_list_source_types_contains_trakt(self) -> None:
        assert "trakt_list" in LIST_SOURCE_TYPES

    def test_list_source_types_contains_tmdb(self) -> None:
        assert "tmdb_list" in LIST_SOURCE_TYPES

    def test_list_source_types_contains_anilist(self) -> None:
        assert "anilist_list" in LIST_SOURCE_TYPES

    def test_list_source_types_contains_mal(self) -> None:
        assert "mal_list" in LIST_SOURCE_TYPES

    def test_list_source_types_contains_letterboxd(self) -> None:
        assert "letterboxd_list" in LIST_SOURCE_TYPES

    def test_list_source_types_contains_recommendations(self) -> None:
        assert "recommendations" in LIST_SOURCE_TYPES

    def test_complex_query_types_contains_genre(self) -> None:
        assert "genre" in COMPLEX_QUERY_SOURCE_TYPES

    def test_complex_query_types_contains_actor(self) -> None:
        assert "actor" in COMPLEX_QUERY_SOURCE_TYPES

    def test_complex_query_types_contains_studio(self) -> None:
        assert "studio" in COMPLEX_QUERY_SOURCE_TYPES

    def test_complex_query_types_contains_tag(self) -> None:
        assert "tag" in COMPLEX_QUERY_SOURCE_TYPES

    def test_complex_query_types_contains_year(self) -> None:
        assert "year" in COMPLEX_QUERY_SOURCE_TYPES

    def test_source_types_are_frozenset(self) -> None:
        """SOURCE_TYPES should be a frozenset (immutable)."""
        assert isinstance(SOURCE_TYPES, frozenset)

    def test_list_source_types_are_frozenset(self) -> None:
        assert isinstance(LIST_SOURCE_TYPES, frozenset)

    def test_complex_query_types_are_frozenset(self) -> None:
        assert isinstance(COMPLEX_QUERY_SOURCE_TYPES, frozenset)


class TestScrapingHeaders:
    """Tests for DEFAULT_SCRAPING_HEADERS."""

    def test_headers_contain_user_agent(self) -> None:
        assert "User-Agent" in DEFAULT_SCRAPING_HEADERS

    def test_headers_contain_accept_language(self) -> None:
        assert "Accept-Language" in DEFAULT_SCRAPING_HEADERS

    def test_user_agent_is_chrome(self) -> None:
        ua = DEFAULT_SCRAPING_HEADERS["User-Agent"]
        assert "Chrome/131" in ua

    def test_headers_are_dict(self) -> None:
        assert isinstance(DEFAULT_SCRAPING_HEADERS, dict)

    def test_headers_are_mutable(self) -> None:
        """The dict itself is mutable (callers can add extra keys like Referer)."""
        headers = dict(DEFAULT_SCRAPING_HEADERS)
        headers["Referer"] = "https://example.com/"
        assert "Referer" in headers


class TestSearchRoots:
    """Tests for DEFAULT_SEARCH_ROOTS."""

    def test_search_roots_is_tuple(self) -> None:
        assert isinstance(DEFAULT_SEARCH_ROOTS, tuple)

    def test_search_roots_contains_home(self) -> None:
        assert any("home" in root for root in DEFAULT_SEARCH_ROOTS)

    def test_search_roots_contains_media(self) -> None:
        assert "/media" in DEFAULT_SEARCH_ROOTS

    def test_search_roots_contains_mnt(self) -> None:
        assert "/mnt" in DEFAULT_SEARCH_ROOTS

    def test_search_roots_are_strings(self) -> None:
        assert all(isinstance(r, str) for r in DEFAULT_SEARCH_ROOTS)


class TestNetworkDefaults:
    """Tests for network/timeout default constants."""

    def test_list_fetch_timeout_is_positive(self) -> None:
        assert DEFAULT_LIST_FETCH_TIMEOUT > 0

    def test_list_fetch_timeout_is_int(self) -> None:
        assert isinstance(DEFAULT_LIST_FETCH_TIMEOUT, int)

    def test_list_max_pages_is_positive(self) -> None:
        assert DEFAULT_LIST_MAX_PAGES > 0

    def test_list_max_pages_is_int(self) -> None:
        assert isinstance(DEFAULT_LIST_MAX_PAGES, int)

    def test_list_page_limit_is_positive(self) -> None:
        assert DEFAULT_LIST_PAGE_LIMIT > 0

    def test_list_page_limit_is_int(self) -> None:
        assert isinstance(DEFAULT_LIST_PAGE_LIMIT, int)

    def test_list_page_limit_is_reasonable(self) -> None:
        """Page limit should be large enough for efficient pagination."""
        assert DEFAULT_LIST_PAGE_LIMIT >= 100


class TestProductionYearAscending:
    """The ascending year sort added for franchise watch order."""

    def test_sort_map_contains_ascending_year(self) -> None:
        """SORT_MAP exposes an oldest-first production year order."""
        from jellyfin import SORT_MAP

        assert "ProductionYearAsc" in SORT_MAP
        key, direction = SORT_MAP["ProductionYearAsc"]
        assert key.split(",")[0] == "ProductionYear"
        assert direction.split(",")[0] == "Ascending"

    def test_sorts_oldest_first(self) -> None:
        """_sort_items puts the earliest release first."""
        from sync import _sort_items_in_memory

        items = [
            {"Name": "Endgame", "ProductionYear": 2019},
            {"Name": "Iron Man", "ProductionYear": 2008},
            {"Name": "Avengers", "ProductionYear": 2012},
        ]

        result = _sort_items_in_memory(items, "ProductionYearAsc")

        assert [i["Name"] for i in result] == ["Iron Man", "Avengers", "Endgame"]

    def test_items_without_year_sort_last(self) -> None:
        """Items missing ProductionYear still end up at the end."""
        from sync import _sort_items_in_memory

        items = [
            {"Name": "Unknown"},
            {"Name": "Iron Man", "ProductionYear": 2008},
        ]

        result = _sort_items_in_memory(items, "ProductionYearAsc")

        assert [i["Name"] for i in result] == ["Iron Man", "Unknown"]
