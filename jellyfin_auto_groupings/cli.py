import argparse
import sys
from typing import Optional, Sequence

from jellyfin_auto_groupings.client import (
    JellyfinClient,
    group_items_by_pattern,
    sync_groupings,
)


def group_movies(items, pattern: str = r"^(.*)"):
    return group_items_by_pattern(items, pattern)


def main(args: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Jellyfin Auto Groupings CLI")
    parser.add_argument("--url", "--server", dest="url", default="http://localhost:8096", help="Jellyfin Server URL")
    parser.add_argument("--api-key", dest="api_key", required=True, help="Jellyfin API Key")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--pattern", default=r"^(.*)", help="Grouping regex pattern")
    
    parsed = parser.parse_args(args)
    try:
        client = JellyfinClient(parsed.url, parsed.api_key)
        movies = client.get_all_items(item_types=["Movie"]) if hasattr(client, "get_all_items") else []
        groups = group_movies(movies, parsed.pattern)
        sync_groupings(client, groups, dry_run=parsed.dry_run)
    except Exception as e:
        msg = f"Error: {e}"
        sys.stderr.write(msg + "\n")
        sys.exit(1)
    else:
        return 0


if __name__ == "__main__":
    main()
