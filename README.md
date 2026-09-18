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
from jellyfin_auto_groupings import JellyfinClient, sync_groupings, group_items_by_pattern

client = JellyfinClient("http://localhost:8096", "your-api-key")
items = client.get_all_items(item_types=["Movie"])
groups = group_items_by_pattern(items, r"^(.*)")
sync_groupings(client, groups)
```

## CLI Usage

```bash
python -m jellyfin_auto_groupings.cli --url http://localhost:8096 --api-key YOUR_KEY --dry-run
```

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
- `create_collection(name, item_ids)` - Create a new collection
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

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest

# Lint
python -m ruff check .
python -m ruff format --check .
```

## License

MIT
