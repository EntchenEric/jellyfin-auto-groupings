import argparse
import logging
import re
import sys
from typing import Any, Optional, Sequence

import requests

from jellyfin_auto_groupings.client import (
    JellyfinAPIError,
    JellyfinClient,
    sync_groupings,
)

logger = logging.getLogger(__name__)


def group_movies(
    items: list[dict[str, Any]], pattern: str = r"^(.*)"
) -> dict[str, list[dict[str, Any]]]:
    """Group movies using a regex pattern applied to their ``Name`` field.

    Args:
        items: List of item dictionaries (must contain a ``Name`` key).
        pattern: Regex pattern whose first capture group (or full match)
            determines the collection name.

    Returns:
        Mapping of collection names to lists of items.
    """
    from jellyfin_auto_groupings.client import group_items_by_pattern

    return group_items_by_pattern(items, pattern)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="jellyfin-auto-groupings",
        description="Automate Jellyfin collection creation from media title patterns.",
    )
    parser.add_argument(
        "--url",
        "--server",
        dest="url",
        default="http://localhost:8096",
        help="Jellyfin server URL (default: http://localhost:8096)",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        required=True,
        help="Jellyfin API key (set JELLYFIN_API_KEY env var instead to avoid shell history)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them to the server",
    )
    parser.add_argument(
        "--pattern",
        default=r"^(.*)",
        help="Regex pattern whose first capture group defines collection names (default: ^( .* ) — one collection per movie)",
    )
    return parser


def main(args: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns an exit code (0 on success, 1 on failure)."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parsed = build_parser().parse_args(args)

    if parsed.url.rstrip("/") != parsed.url:
        logger.warning("Trailing slash in --url; it will be stripped automatically.")

    # Validate that the regex pattern compiles before connecting.
    try:
        re.compile(parsed.pattern)
    except re.error as exc:
        sys.stderr.write(f"Invalid --pattern regex: {exc}\n")
        sys.exit(1)

    try:
        client = JellyfinClient(parsed.url, parsed.api_key)
        movies = client.get_all_items(item_types=["Movie"])
        groups = group_movies(movies, parsed.pattern)
    except requests.ConnectionError:
        sys.stderr.write(
            f"Could not connect to Jellyfin at {parsed.url}. "
            "Check that the server is running and the URL is correct.\n"
        )
        sys.exit(1)
    except requests.Timeout:
        sys.stderr.write(
            f"Request to {parsed.url} timed out. The server may be busy.\n"
        )
        sys.exit(1)
    except JellyfinAPIError as exc:
        msg = f"Error: {exc}"
        sys.stderr.write(msg + "\n")
        sys.exit(1)
    except Exception as exc:
        msg = f"Error: {exc}"
        sys.stderr.write(msg + "\n")
        sys.exit(1)

    try:
        summary = sync_groupings(client, groups, dry_run=parsed.dry_run)
    except requests.ConnectionError:
        sys.stderr.write(
            "Connection lost while syncing. Re-run with --dry-run first to preview.\n"
        )
        sys.exit(1)
    except Exception as exc:
        sys.stderr.write(f"Failed to sync groupings: {exc}\n")
        sys.exit(1)

    n_groups = len(summary)
    mode = "dry-run" if parsed.dry_run else "applied"
    print(f"{n_groups} collection(s) would be {mode}. Use --dry-run to preview.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
