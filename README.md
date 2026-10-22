# Jellyfin Auto Groupings

Automated media grouping, tagging, and collection management for Jellyfin.

## Features

- Automated collection and grouping synchronization
- Integrations with TMDB, Trakt, IMDb, AniList, MyAnimeList, and Letterboxd
- Configurable scheduling and CLI support
- Comprehensive test suite
- Enhanced error handling, logging, and robust type hints

## Installation

```bash
pip install jellyfin-groupings
```

## Quick Start

```python
from jellyfin_auto_groupings import (
    JellyfinClient,
    sync_groupings,
    group_items_by_pattern,
)

client = JellyfinClient("http://localhost:8096", "your-api-key")
items = client.get_all_items(item_types=["Movie"])
groups = group_items_by_pattern(items, r"^(.*)")
sync_groupings(client, groups)
```

## CLI Usage

```bash
python -m jellyfin_auto_groupings.cli --url http://localhost:8096 --api-key YOUR_KEY --dry-run
```

Options:
- `--url` / `--server` - Jellyfin server URL (default: `$JELLYFIN_URL`, else `http://localhost:8096`)
- `--api-key` - Jellyfin API key (default: `$JELLYFIN_API_KEY`; required from one or the other)
- `--dry-run` - Preview changes without applying them
- `--pattern` - Regex pattern used to derive group names from item names (default: `^(.*)`)

Prefer the environment variable so the key stays out of your shell history and
the process list:

```bash
export JELLYFIN_API_KEY=your-api-key
python -m jellyfin_auto_groupings.cli --url http://localhost:8096 --dry-run
```

Exit codes: `0` on success, `1` for a missing API key, an invalid `--pattern`
regex, a connection/timeout failure, or a sync error, and `2` for a malformed
command line. `main()` returns the code instead of raising `SystemExit`, so it
can be called in-process; the `python -m` entry point still exits with it.

## Configuration

Set environment variables:
- `JELLYFIN_URL` - Jellyfin server URL (default: `http://localhost:8096`)
- `JELLYFIN_API_KEY` - Jellyfin API key
- `DRY_RUN` - Set to `true` to preview changes without applying them

## API

### JellyfinClient

Main client for interacting with Jellyfin.

```python
client = JellyfinClient("http://localhost:8096", "api-key", user_id="optional-user-id")
```

**Methods:**
- `get_users()` - List all users
- `get_first_admin_user_id()` - Get the first admin user's ID
- `get_all_items(item_types, parent_id)` - Get items with optional filtering
- `get_items(library_id)` - Get items from a specific library
- `get_collections()` - Get all collections (BoxSets)
- `get_collection_items(collection_id)` - Get items in a collection
- `get_movies()` - Get all movies
- `create_collection(name, item_ids)` - Create a new collection. Returns the
  response metadata, or `{}` when Jellyfin sends no body, or `{}` for an empty
  `item_ids` list.
- `add_to_collection(collection_id, item_ids)` - Add items to existing collection
- `remove_from_collection(collection_id, item_ids)` - Remove items from collection
- `update_item_sort_name(item_id, sort_name)` - Update an item's sort name

### Grouping Functions

- `group_items_by_pattern(items, pattern, attribute)` - Group items by regex pattern
- `sync_groupings(client, groups, dry_run, min_items)` - Sync groups with Jellyfin collections
- `get_decade_groups(items)` - Group items by decade
- `get_year_groups(items)` - Group items by release year
- `get_movies_by_query(items, query, tags)` - Filter items by query string
- `group_movies_by_tag(items, min_group_size)` - Group items by tag
- `group_movies_by_genre(items, min_group_size)` - Group items by genre
- `process_groupings(client, library_id, items, dry_run)` - Main processing function
- `create_groupings(client_or_items, library_id, items, min_group_size)` - Create groupings

All grouping helpers tolerate the shapes Jellyfin actually returns: a `null`
`Tags`, `Genres`, or `Studios` value, non-string entries inside those lists,
and items without a `PremiereDate`. Such items are skipped rather than
aborting the sync.

The same applies to the fields the sync engine reads to *match* items. Jellyfin
sends `"ProviderIds": null` for an item it never matched to a provider, and
`"Policy": null` for a user it has not fully configured; a `null` there is
treated as "no data" rather than as a mapping, so one such item cannot fail a
whole group. A Jellyfin response whose body is valid JSON but not the expected
shape (an object for item pages, an array for `/Users` and
`/Library/VirtualFolders`) is reported as a Jellyfin error naming the type that
arrived, instead of surfacing as an `AttributeError` mid-sync.

`process_groupings(..., dry_run=True)` never mutates the server: it reports the
planned sort-name changes and creates no collections. Items without a usable
`Id` are skipped in both modes, because Jellyfin would reject the request for
the whole collection rather than just that item.

## Standalone `auto_group.py` script

The repository also ships `auto_group.py`, a self-contained script that walks
every Jellyfin library, derives base titles with regex patterns, and creates one
collection per group. It predates the package and is independent of it.

```bash
python auto_group.py --config myconfig.json --dry-run --verbose
```

Options:
- `--config` - Path to a JSON config file (default: `config.json`)
- `--dry-run` - Print the groups without creating collections
- `--verbose` - Enable debug logging

Environment variables override nothing in the file but supply defaults:
`JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DRY_RUN`, and `MIN_GROUP_SIZE` (default 2).
A JSON file may set any of these plus `PATTERNS`, a list of regex strings.

Patterns are user-supplied, so they are not required to declare a capture group.
The first group that participated in the match is the collection name; a pattern
with no groups falls back to the whole match, and an invalid regex is logged and
skipped. Items with a `null` or blank `Name` never form a group. A malformed
`MIN_GROUP_SIZE` or non-list `PATTERNS` logs a warning and falls back to the
default instead of aborting the run.

For the package CLI (`--url`, `--api-key`, `--pattern`) see
[CLI Usage](#cli-usage) above.

## External list sources

Every `*_list` source resolves an ordered list of external IDs and matches them
against your Jellyfin library by `ProviderIds`. Four behaviours are worth
knowing before you build a group on a long list:

- **Pagination is followed to the end of the list.** IMDb, Trakt and
  Letterboxd, TMDb, AniList and MyAnimeList lists all return more than one
  page; the fetchers walk every page and stop at the first one without a usable
  next-page control. A list longer than the safety cap (50 pages) is truncated
  at the cap and logged as a warning, so a partial result is never mistaken for
  the whole list. A next-page URL returned by an API is followed only when it
  still points at that provider's own API host, so a malformed or tampered
  response cannot redirect the request (with your API key) somewhere else.
- **Items the library cannot match are skipped, not fatal.** A film with no
  IMDb or TMDb ID in Jellyfin simply does not appear in the group; the rest of
  the list still syncs. Duplicates (the same item matched through both ID
  types) are collapsed so a file is never linked twice.
- **A malformed upstream response fails one group, not the run.** Each
  fetcher validates the shape of the payload it parses: entries that are not
  objects, IDs that are missing or boolean, and pagination fields of the
  wrong type are skipped rather than raising. A response that cannot be used
  at all raises the error type the sync layer catches, so the group records a
  fetch error and the remaining groups still sync.
- **A list identifier must match its source exactly.** The IMDb source accepts
  a bare `ls000024390` ID or an `imdb.com` URL containing `/list/ls000024390`;
  the Letterboxd source accepts an HTTP(S) URL on `letterboxd.com` (a missing
  scheme is filled in); the TMDb source accepts a numeric list ID or a
  `themoviedb.org/list/<id>` URL, and reads the ID from the URL rather than its
  trailing name, so `…/list/8204231/my-list` uses `8204231`; the Trakt source
  accepts `username/list-slug` or a `trakt.tv/users/<user>/lists/<slug>` URL.
  Anything else is rejected with an error on that group instead of being
  trimmed into a different, valid-looking list — a typo such as `ls123abc`
  would otherwise silently sync the list `ls123`.

  A MyAnimeList source names a username (optionally followed by `/status`);
  the username must be letters, digits, `-` and `_`, because it is placed in
  the request path.

## Library pagination

The Jellyfin item walk requests pages with `StartIndex` / `Limit` and stops as
soon as a page comes back shorter than the requested limit. Two guards keep a
misbehaving server from hanging a sync run:

- **A repeated page ends the walk.** If a proxy strips `StartIndex`, or the
  server ignores it for a query, every request returns the same items. The
  walk compares each page's item IDs with the previous page and stops with a
  warning instead of appending the same items forever.
- **The walk is capped at 1000 pages.** A server that keeps returning fresh
  full pages is truncated at the cap, again with a warning, so a partial
  result is never mistaken for the whole library.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest

# Frontend tests (vitest, jsdom) + node smoke test
npm install
npm test

# Lint
python -m ruff check .
python -m ruff format --check .
```

## Documentation

- [docs/API.md](docs/API.md) - every HTTP endpoint, its request fields, and
  its error responses
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - module responsibilities and
  the sync pipeline

## License

MIT
