import argparse
import sys
from typing import Optional, Sequence
from jellyfin_auto_groupings.client import JellyfinAPIError, JellyfinClient, group_items_by_pattern, sync_groupings


def group_movies(items):
    return group_items_by_pattern(items, r"^(.*)")


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
        groups = group_movies(movies)
        sync_groupings(client, groups, dry_run=parsed.dry_run)
        return 0
    except JellyfinAPIError as e:
        sys.stderr.write(f"Error: {e}\\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
