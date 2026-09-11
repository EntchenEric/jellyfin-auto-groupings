# Jellyfin Auto Groupings

Automatically organize your Jellyfin media items into collections based on shared metadata such as tags, genres, studios, or directors.

## Features

- **Automatic Collections**: Group items into collections by `tag`, `genre`, `studio`, or `director`.
- **Min Threshold**: Set minimum item count per group (e.g., only create collections for groups with $\ge 2$ items).
- **Dry-run Mode**: Inspect created collections and items without changing your Jellyfin library.
- **Clean Up / Prune**: Remove managed collections that no longer meet minimum size requirements.
- **Robust Error Handling**: Graceful network and API failure reporting.

## Installation

Install from source using `pip`:

```bash
pip install .
```

Or using `uv` / `pip install -e .` for development.

## Usage

### Command Line Options

```text
usage: jellyfin-auto-groupings [-h] --server SERVER --api-key API_KEY
                                [--group-by {tag,genre,studio,director}]
                                [--min-items MIN_ITEMS] [--dry-run]
                                [--user-id USER_ID]
```

| Option | Description | Default |
| --- | --- | --- |
| `--server` | Jellyfin server base URL (e.g. `http://localhost:8096`) | **Required** |
| `--api-key` | Jellyfin API Key / Access Token | **Required** |
| `--group-by` | Metadata attribute to group by (`tag`, `genre`, `studio`, `director`) | `tag` |
| `--min-items` | Minimum number of items required to form a collection | `2` |
| `--dry-run` | Preview actions without creating/modifying collections | `False` |
| `--user-id` | Optional Jellyfin User ID | `None` |

### Examples

#### Group by Genre (Dry Run)

```bash
jellyfin-auto-groupings \
  --server http://localhost:8096 \
  --api-key YOUR_API_KEY \
  --group-by genre \
  --min-items 3 \
  --dry-run
```

#### Group by Studio

```bash
jellyfin-auto-groupings \
  --server http://localhost:8096 \
  --api-key YOUR_API_KEY \
  --group-by studio \
  --min-items 2
```

## Development & Testing

Run test suite and check coverage:

```bash
pytest --cov=jellyfin_auto_groupings
```

Run linter and type checker:

```bash
python3 -m ruff check .
python3 -m mypy --ignore-missing-imports src tests
```

## License

MIT
