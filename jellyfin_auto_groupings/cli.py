import argparse
import logging
import os
import re
import sys
from collections.abc import Sequence
from typing import Any

import requests

from jellyfin_auto_groupings.client import (
    JellyfinAPIError,
    JellyfinClient,
    group_items_by_pattern,
    sync_groupings,
)

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:8096"


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
        default=os.environ.get("JELLYFIN_URL") or DEFAULT_URL,
        help=(f"Jellyfin server URL (default: $JELLYFIN_URL, else {DEFAULT_URL})"),
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=os.environ.get("JELLYFIN_API_KEY") or None,
        help=(
            "Jellyfin API key (default: $JELLYFIN_API_KEY). Prefer the env var "
            "so the key stays out of shell history and process listings."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them to the server",
    )
    parser.add_argument(
        "--pattern",
        default=r"^(.*)",
        help=(
            "Regex pattern whose first capture group defines collection names "
            r"(default: ^(.*), which puts each movie in its own collection)"
        ),
    )
    return parser


def main(args: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        An exit code: ``0`` on success, ``1`` on any failure. Every failure
        path returns rather than raising ``SystemExit`` so that callers can
        invoke :func:`main` in-process and inspect the code. The module guard
        forwards the result to :func:`sys.exit`, so the process still exits
        non-zero on failure.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parsed = build_parser().parse_args(args)

    if not parsed.api_key:
        sys.stderr.write(
            "Error: a Jellyfin API key is required. Pass --api-key or set the "
            "JELLYFIN_API_KEY environment variable.\n"
        )
        return 1

    if parsed.url.rstrip("/") != parsed.url:
        logger.warning("Trailing slash in --url; it will be stripped automatically.")

    # Validate that the regex pattern compiles before connecting.
    try:
        re.compile(parsed.pattern)
    except re.error as exc:
        sys.stderr.write(f"Invalid --pattern regex: {exc}\n")
        return 1

    try:
        client = JellyfinClient(parsed.url, parsed.api_key)
        movies = client.get_all_items(item_types=["Movie"])
        groups = group_movies(movies, parsed.pattern)
    except requests.ConnectionError:
        sys.stderr.write(
            f"Could not connect to Jellyfin at {parsed.url}. "
            "Check that the server is running and the URL is correct.\n"
        )
        return 1
    except requests.Timeout:
        sys.stderr.write(
            f"Request to {parsed.url} timed out. The server may be busy.\n"
        )
        return 1
    except JellyfinAPIError as exc:
        msg = f"Error: {exc}"
        sys.stderr.write(msg + "\n")
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary, report and exit
        msg = f"Error: {exc}"
        sys.stderr.write(msg + "\n")
        return 1

    try:
        summary = sync_groupings(client, groups, dry_run=parsed.dry_run)
    except requests.ConnectionError:
        sys.stderr.write(
            "Connection lost while syncing. Re-run with --dry-run first to preview.\n"
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary, report and exit
        sys.stderr.write(f"Failed to sync groupings: {exc}\n")
        return 1

    n_groups = len(summary)
    if parsed.dry_run:
        print(f"Dry run: {n_groups} collection(s) would be synced. No changes made.")
    else:
        print(f"Synced {n_groups} collection(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
