"""Tests for external metadata providers (Anilist, Trakt, Mal, TMDB, Letterboxd, IMDB)."""

from http import HTTPStatus
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
import requests

import _common
import anilist
import imdb
import letterboxd
import mal
import tmdb
import trakt


def test_anilist_fetch():
    with patch("anilist.network.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "MediaListCollection": {
                    "lists": [{"name": "Completed", "entries": [{"mediaId": 12345}]}]
                }
            }
        }
        mock_post.return_value = mock_resp
        res = anilist.fetch_anilist_list("testuser")
        assert res == [12345]


def test_trakt_get_headers():
    headers = trakt._build_trakt_headers("test_client_id")
    assert headers.get("trakt-api-key") == "test_client_id"


def test_mal_fetch():
    with patch("mal.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"node": {"id": 1, "title": "Test Anime"}}],
            "paging": {},
        }
        mock_get.return_value = mock_resp
        res = mal.fetch_mal_list("testuser", "test_client_id")
        assert res == [1]


# --- _common.py tests ---


def test_normalize_group_relpath():
    assert _common.normalize_group_relpath("Anime/Action") == "Anime/Action"
    assert _common.normalize_group_relpath("  Anime // Action  ") == "Anime/Action"
    assert _common.normalize_group_relpath("Anime\\Action") == "Anime/Action"
    assert _common.normalize_group_relpath("../outside") is None
    assert _common.normalize_group_relpath(".") is None
    assert _common.normalize_group_relpath("C:\\Windows\\System32") is None
    assert _common.normalize_group_relpath("") is None
    assert _common.normalize_group_relpath(None) is None
    assert _common.normalize_group_relpath("Test\x00Null") is None


# --- tmdb.py tests ---


def test_tmdb_fetch_list():
    with patch("tmdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [{"id": 101}, {"id": 102}],
            "total_pages": 1,
        }
        mock_get.return_value = mock_resp
        ids = tmdb.fetch_tmdb_list("12345", "fake_api_key")
        assert ids == ["101", "102"]


def test_tmdb_fetch_list_validation():
    with pytest.raises(ValueError):
        tmdb.fetch_tmdb_list("12345", "")
    with pytest.raises(ValueError):
        tmdb.fetch_tmdb_list("", "fake_key")


def test_tmdb_recommendations():
    with patch("tmdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": 201}, {"id": 202}]}
        mock_get.return_value = mock_resp
        recs = tmdb.get_tmdb_recommendations([("101", "movie")], "fake_api_key")
        assert recs == ["201", "202"]


# --- imdb.py tests ---


def test_imdb_fetch_list():
    with patch("imdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<html><a href="/title/tt1234567/">Movie</a></html>'
        mock_get.return_value = mock_resp
        ids = imdb.fetch_imdb_list("ls0000000")
        assert ids == ["tt1234567"]


def test_imdb_fetch_list_invalid():
    with pytest.raises(ValueError):
        imdb.fetch_imdb_list("")


# --- letterboxd.py tests ---


def test_letterboxd_fetch_list():
    with patch("letterboxd.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = (
            '<html><div data-film-slug="test-movie" data-tmdb-id="12345"></div></html>'
        )
        mock_get.return_value = mock_resp
        res = letterboxd.fetch_letterboxd_list(
            "https://letterboxd.com/user/list/test-list/"
        )
        assert res == ["12345"]


# Real Letterboxd markup wraps a film's attributes over several lines, and each
# film block is preceded by attributes of its own. Non-DOTALL patterns silently
# found nothing there, so every film fell back to an extra HTTP request.
_MULTILINE_LIST_HTML = """
<ul>
  <li class="poster-container">
    <div class="film-poster" data-film-slug="the-godfather"
         data-film-id="1">
      <a href="https://www.themoviedb.org/movie/238/">x</a>
    </div>
  </li>
  <li class="poster-container">
    <div class="film-poster" data-film-slug="parasite-2019"
         data-tmdb-id="496243"></div>
  </li>
  <li class="poster-container">
    <div class="film-poster" data-film-slug="imdb-only">
      <a href="https://www.imdb.com/title/tt0111161/">x</a>
    </div>
  </li>
</ul>
"""


def test_letterboxd_extract_ids_multiline_markup():
    found = letterboxd._extract_ids_from_list_page(_MULTILINE_LIST_HTML)
    assert found == {
        "the-godfather": "238",
        "parasite-2019": "496243",
        "imdb-only": "tt0111161",
    }


def test_letterboxd_extract_ids_does_not_bleed_between_films():
    html = (
        '<div data-film-slug="no-id-film"></div>'
        '<div data-film-slug="later-film" data-tmdb-id="999"></div>'
    )
    found = letterboxd._extract_ids_from_list_page(html)
    assert "no-id-film" not in found
    assert found == {"later-film": "999"}


def test_letterboxd_extract_ids_keeps_first_block_for_a_repeated_slug():
    """A slug that appears twice keeps the ID from its first block."""
    html = (
        '<div data-film-slug="dup" data-tmdb-id="111"></div>'
        '<div data-film-slug="dup" data-tmdb-id="222"></div>'
    )

    assert letterboxd._extract_ids_from_list_page(html) == {"dup": "111"}


def test_letterboxd_extract_ids_prefers_tmdb_attribute_over_links():
    html = (
        '<div data-film-slug="both" data-tmdb-id="555">'
        '<a href="https://www.imdb.com/title/tt0000001/">x</a></div>'
    )
    assert letterboxd._extract_ids_from_list_page(html) == {"both": "555"}


def test_letterboxd_list_page_ids_skip_per_film_fetch():
    with patch("letterboxd.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _MULTILINE_LIST_HTML
        mock_get.return_value = mock_resp
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")

    assert ids == ["238", "496243", "tt0111161"]
    assert mock_get.call_count == 1, "list-page IDs must not trigger film fetches"


# --- Letterboxd pagination -------------------------------------------------
# Letterboxd writes the next-page control as ``class="next "`` (trailing
# space) and disables it with ``class="next  is-disabled"``. Comparing the
# attribute against the literal ``class="next"`` therefore never matched, and
# every multi-page list was silently cut down to its first page.


def _letterboxd_page(number: int, pagination: str = "") -> str:
    """Build a one-film list page with the given pagination markup."""
    return (
        f'<div data-film-slug="film-{number}" data-tmdb-id="{number}"></div>'
        f"{pagination}"
    )


def _fetch_with_pages(pages: dict[int, str]) -> tuple[list[str], MagicMock]:
    """Serve *pages* by request order and return the fetched IDs and mock."""
    with (
        patch("letterboxd.network.get") as mock_get,
        # Pagination pauses 0.5 s between pages to be polite to Letterboxd;
        # a multi-page test should not spend real time on it.
        patch("letterboxd.time.sleep"),
    ):
        responses = []
        for page in sorted(pages):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = pages[page]
            responses.append(resp)
        mock_get.side_effect = responses
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")
    return ids, mock_get


def test_letterboxd_paginates_on_class_with_trailing_space():
    """A trailing space in ``class="next "`` must not end pagination."""
    ids, mock_get = _fetch_with_pages(
        {
            1: _letterboxd_page(1, '<a class="next " href="/page/2/">Next</a>'),
            2: _letterboxd_page(2),
        },
    )

    assert ids == ["1", "2"]
    assert mock_get.call_count == 2


def test_letterboxd_paginates_on_class_with_extra_tokens():
    """State classes next to ``next`` must not end pagination either."""
    ids, mock_get = _fetch_with_pages(
        {
            1: _letterboxd_page(1, '<a class="next button" href="/page/2/">Next</a>'),
            2: _letterboxd_page(2),
        },
    )

    assert ids == ["1", "2"]
    assert mock_get.call_count == 2


def test_letterboxd_stops_on_disabled_next_control():
    """A disabled next control marks the last page and must stop the walk."""
    ids, mock_get = _fetch_with_pages(
        {
            1: _letterboxd_page(
                1,
                '<a class="next  is-disabled" href="/page/2/">Next</a>',
            ),
            2: _letterboxd_page(2),
        },
    )

    assert ids == ["1"]
    assert mock_get.call_count == 1


def test_letterboxd_ignores_unrelated_class_containing_next():
    """``class="next-door"`` is not a pagination control."""
    ids, mock_get = _fetch_with_pages(
        {1: _letterboxd_page(1, '<a class="next-door" href="/x/">x</a>')},
    )

    assert ids == ["1"]
    assert mock_get.call_count == 1


def test_letterboxd_pagination_respects_page_limit(caplog):
    """Hitting the page cap is reported instead of looking like the list end."""
    endless = '<a class="next " href="/page/2/">Next</a>'
    pages = {
        page: _letterboxd_page(page, endless)
        for page in range(1, letterboxd._MAX_PAGES + 1)
    }

    with caplog.at_level("WARNING", logger="letterboxd"):
        _, mock_get = _fetch_with_pages(pages)

    assert mock_get.call_count == letterboxd._MAX_PAGES
    assert "safety limit" in caplog.text


def test_letterboxd_disabled_control_beats_rel_next():
    """A disabled next control ends the list even if ``rel="next"`` appears."""
    html = (
        '<a class="next  is-disabled" href="/page/2/" rel="next">Next</a>'
        '<div data-film-slug="only" data-tmdb-id="7"></div>'
    )

    assert letterboxd._has_next_page(html) is False


# --- Letterboxd URL canonicalisation --------------------------------------
# A URL pasted from a browser carries a query string, a fragment, or an
# explicit ``/page/N/`` segment. Only the path identifies the list, and the
# page walk appends ``/page/<n>/`` to whatever ``_validate_list_url`` returns,
# so the query string ended up in front of the page segment:
# ``…/x?utm_source=tw/page/2/`` resolved back to page 1. The walk then
# re-read page 1 until the 50-page cap and returned only its films.


@pytest.mark.parametrize(
    "supplied",
    [
        "https://letterboxd.com/u/list/x/?page=2",
        "https://letterboxd.com/u/list/x?utm_source=tw",
        "https://letterboxd.com/u/list/x/#comments",
        "https://letterboxd.com/u/list/x/page/3/",
        "https://letterboxd.com/u/list/x/page/3",
        "https://letterboxd.com/u/list/x/",
    ],
)
def test_letterboxd_url_normalises_to_page_one(supplied):
    """Every spelling of a list URL yields the same page-one base URL."""
    assert letterboxd._validate_list_url(supplied) == "https://letterboxd.com/u/list/x"


def test_letterboxd_scheme_less_url_gets_https():
    """A pasted host-and-path is completed with ``https://``."""
    assert (
        letterboxd._validate_list_url("letterboxd.com/u/list/x")
        == "https://letterboxd.com/u/list/x"
    )


@pytest.mark.parametrize("supplied", ["ftp://letterboxd.com/u/list/x", "https://"])
def test_letterboxd_rejects_unsupported_scheme(supplied):
    """Only http(s) URLs on Letterboxd may be fetched."""
    with pytest.raises(ValueError, match="Invalid Letterboxd URL"):
        letterboxd._validate_list_url(supplied)


def test_letterboxd_query_string_does_not_break_pagination():
    """A tracking query must not turn page 2 into a second read of page 1.

    The fake server routes on the URL *path* the way Letterboxd does, so a
    page segment that lands after ``?utm_source=tw`` is not seen as a page.
    """
    seen_urls: list[str] = []

    def serve(url: str, **_kwargs: object) -> MagicMock:
        seen_urls.append(url)
        path = urlparse(url).path
        page = int(path.rstrip("/").rsplit("/", 1)[1]) if "/page/" in path else 1
        resp = MagicMock()
        resp.status_code = 200
        resp.text = _letterboxd_page(page)
        if page == 1:
            resp.text += '<a class="next " href="/page/2/">Next</a>'
        return resp

    with (
        patch("letterboxd.network.get", side_effect=serve),
        patch("letterboxd.time.sleep"),
    ):
        ids = letterboxd.fetch_letterboxd_list(
            "https://letterboxd.com/u/list/x?utm_source=tw",
        )

    assert ids == ["1", "2"]
    assert seen_urls == [
        "https://letterboxd.com/u/list/x/",
        "https://letterboxd.com/u/list/x/page/2/",
    ]


# --- Letterboxd per-film detail pages -------------------------------------
# List-page HTML does not always embed an ID, so the slug is resolved from
# the film's own page. Each fallback order and each failure mode was
# previously untested, leaving the whole per-film path uncovered.


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        # An IMDb link wins over a TMDb link on the same page.
        (
            (
                '<a href="https://www.imdb.com/title/tt0111161/">i</a>'
                '<a href="https://www.themoviedb.org/movie/278/">t</a>'
            ),
            "tt0111161",
        ),
        # A TMDb link is used when no IMDb link is present.
        ('<a href="https://www.themoviedb.org/movie/278/">t</a>', "278"),
        # The data attribute is the last resort.
        ('<div data-tmdb-id="496243"></div>', "496243"),
        # A page with no recognisable ID yields None rather than raising.
        ("<html><body>nothing here</body></html>", None),
    ],
)
def test_letterboxd_film_page_id_extraction(html, expected):
    """A film page resolves to the best available ID."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html

    with patch("letterboxd.network.get", return_value=resp):
        assert letterboxd._fetch_id_for_slug("some-film") == expected


def test_letterboxd_film_page_http_error_returns_none(caplog):
    """One unreachable film page skips that film instead of failing the list."""
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

    with (
        patch("letterboxd.network.get", return_value=resp),
        caplog.at_level("WARNING", logger="letterboxd"),
    ):
        assert letterboxd._fetch_id_for_slug("some-film") is None

    assert "some-film" in caplog.text


def test_letterboxd_film_fetch_error_does_not_abort_list():
    """A failing per-film fetch leaves the other films' IDs intact."""

    def serve(url: str, **_kwargs: object) -> MagicMock:
        resp = MagicMock()
        if url.endswith("/film/broken/"):
            resp.raise_for_status.side_effect = requests.ConnectionError("boom")
            return resp
        resp.status_code = 200
        resp.text = '<a href="https://www.imdb.com/title/tt0000001/">i</a>'
        return resp

    list_page = '<div data-film-slug="good"></div><div data-film-slug="broken"></div>'

    def route(url: str, **kwargs: object) -> MagicMock:
        if "/film/" in url:
            return serve(url, **kwargs)
        resp = MagicMock()
        resp.status_code = 200
        resp.text = list_page
        return resp

    with (
        patch("letterboxd.network.get", side_effect=route),
        patch("letterboxd.time.sleep"),
    ):
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")

    assert ids == ["tt0000001"]


def test_letterboxd_film_results_tolerate_executor_errors():
    """An unexpected worker failure records None instead of propagating."""
    with patch.object(
        letterboxd,
        "_fetch_id_for_slug",
        side_effect=RuntimeError("worker died"),
    ):
        results = letterboxd._fetch_ids_for_slugs(["a", "b"])

    assert results == {"a": None, "b": None}


def test_letterboxd_fetch_ids_for_slugs_empty_input():
    """No slugs means no thread pool and an empty mapping."""
    with patch.object(letterboxd, "ThreadPoolExecutor") as executor:
        assert letterboxd._fetch_ids_for_slugs([]) == {}

    executor.assert_not_called()


# --- Letterboxd list-page failures ---------------------------------------


def test_letterboxd_list_page_http_error_raises_runtime_error():
    """An HTTP error on a list page names the page and the cause."""
    resp = MagicMock()
    resp.status_code = 500
    resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

    with (
        patch("letterboxd.network.get", return_value=resp),
        pytest.raises(RuntimeError, match="page 1"),
    ):
        letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")


def test_letterboxd_missing_later_page_ends_list():
    """A 404 on page 2 is the end of the list, not an error."""
    page_one = MagicMock()
    page_one.status_code = 200
    page_one.text = _letterboxd_page(1, '<a class="next " href="/page/2/">n</a>')
    page_two = MagicMock()
    page_two.status_code = HTTPStatus.NOT_FOUND

    with (
        patch("letterboxd.network.get", side_effect=[page_one, page_two]),
        patch("letterboxd.time.sleep"),
    ):
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")

    assert ids == ["1"]


def test_letterboxd_falls_back_to_film_href_slugs():
    """Markup without ``data-film-slug`` still yields the film hrefs."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '<a href="/film/parasite-2019/">x</a>'

    with (
        patch("letterboxd.network.get", return_value=resp),
        patch.object(
            letterboxd,
            "_fetch_ids_for_slugs",
            return_value={"parasite-2019": "496243"},
        ) as fetch_slugs,
    ):
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")

    assert ids == ["496243"]
    fetch_slugs.assert_called_once_with(["parasite-2019"])


def test_letterboxd_empty_pages_stop_at_the_guard(caplog):
    """Three consecutive slug-less pages stop the walk instead of walking on."""
    empty_page = MagicMock()
    empty_page.status_code = 200
    empty_page.text = "<html>no films</html>"

    with (
        patch("letterboxd.network.get", return_value=empty_page),
        patch("letterboxd.time.sleep"),
        caplog.at_level("INFO", logger="letterboxd"),
    ):
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")

    assert ids == []
    assert "empty consecutive pages" in caplog.text
