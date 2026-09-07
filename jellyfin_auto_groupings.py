"""Jellyfin Auto Groupings tool.

Automatically group movies/shows into collections/boxsets in Jellyfin
based on common title prefixes, patterns, or sequel naming conventions.
"""

import argparse
import os
import re
import sys
from typing import Any, Dict, List, Optional

import requests


def get_items(url: str, api_key: str, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch movie/show items from Jellyfin API with pagination support.

    Args:
        url: Base URL of the Jellyfin server.
        api_key: Jellyfin API access key.
        parent_id: Optional parent folder/library ID.

    Returns:
        List of item dictionaries from Jellyfin.
    """
    headers = {"X-Emby-Token": api_key}
    items: List[Dict[str, Any]] = []
    limit = 500
    start_index = 0

    while True:
        params: Dict[str, Any] = {
            "IncludeItemTypes": "Movie",
            "Recursive": True,
            "Fields": "PrimaryImageAspectRatio,SortName",
            "StartIndex": start_index,
            "Limit": limit,
        }
        if parent_id:
            params["ParentId"] = parent_id

        try:
            res = requests.get(f"{url.rstrip('/')}/Items", headers=headers, params=params, timeout=30)
            res.raise_for_status()
            data = res.json()
        except (requests.RequestException, ValueError) as err:
            print(f"Error fetching items from Jellyfin: {err}", file=sys.stderr)
            break

        fetched_items = data.get("Items", [])
        items.extend(fetched_items)

        total_record_count = data.get("TotalRecordCount", len(items))
        start_index += len(fetched_items)

        if not fetched_items or start_index >= total_record_count:
            break

    return items


def group_items_by_prefix(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group items that share a common title prefix or franchise root.

    Args:
        items: List of Jellyfin item dictionaries.

    Returns:
        A mapping of collection/group name to lists of item dicts.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    
    # Normalize and extract root prefixes
    # Example regex patterns for franchise detection (e.g. "Toy Story", "Toy Story 2", "Toy Story: ...")
    prefix_pattern = re.compile(r"^(.*?)(?:\s+\d+|:\s+.*|\s+-[\s\w]+)?$", re.IGNORECASE)

    candidates: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        name = item.get("Name", "").strip()
        if not name:
            continue
        
        # Extract base title prefix
        match = prefix_pattern.match(name)
        base_name = match.group(1).strip() if match else name
        
        if base_name not in candidates:
            candidates[base_name] = []
        candidates[base_name].append(item)

    # Keep groups with 2 or more items
    return {
        group_name: matched_items
        for group_name, matched_items in candidates.items()
        if len(matched_items) >= 2
    }


def create_collection(
    url: str,
    api_key: str,
    name: str,
    item_ids: List[str],
    dry_run: bool = False
) -> Optional[str]:
    """Create a collection in Jellyfin and add specified items.

    Args:
        url: Base URL of the Jellyfin server.
        api_key: Jellyfin API access key.
        name: Name of the collection to create.
        item_ids: List of Jellyfin item IDs to include.
        dry_run: If True, simulate creation without sending API requests.

    Returns:
        Collection ID if created successfully, or None.
    """
    if dry_run:
        print(f"[DRY-RUN] Would create collection '{name}' with {len(item_ids)} item(s): {item_ids}")
        return "dry-run-collection-id"

    headers = {"X-Emby-Token": api_key}
    endpoint = f"{url.rstrip('/')}/Collections"
    params = {
        "Name": name,
        "Ids": ",".join(item_ids),
    }
    try:
        res = requests.post(endpoint, headers=headers, params=params, timeout=30)
        res.raise_for_status()
        data = res.json()
        collection_id = data.get("Id")
        print(f"Successfully created collection '{name}' (ID: {collection_id}).")
    except (requests.RequestException, ValueError) as err:
        print(f"Failed to create collection '{name}': {err}", file=sys.stderr)
        return None
    else:
        return collection_id


def build_argument_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for Jellyfin Auto Groupings tool."""
    parser = argparse.ArgumentParser(
        description="Automatically group Jellyfin items into collections based on title matching."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("JELLYFIN_URL", ""),
        help="Jellyfin server URL (can also set JELLYFIN_URL env var)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("JELLYFIN_API_KEY", ""),
        help="Jellyfin API Key (can also set JELLYFIN_API_KEY env var)",
    )
    parser.add_argument(
        "--parent-id",
        default=None,
        help="Optional Parent Library ID to restrict search",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without creating actual collections in Jellyfin",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI main entry point."""
    parser = build_argument_parser()
    parsed = parser.parse_args(args)

    if not parsed.url or not parsed.api_key:
        print("Error: Both --url and --api-key (or JELLYFIN_URL and JELLYFIN_API_KEY env vars) are required.", file=sys.stderr)
        return 1

    print(f"Fetching items from {parsed.url}...")
    items = get_items(parsed.url, parsed.api_key, parent_id=parsed.parent_id)
    print(f"Found {len(items)} item(s).")

    groups = group_items_by_prefix(items)
    print(f"Identified {len(groups)} group(s) with 2 or more matching items.")

    for group_name, group_items in groups.items():
        item_ids = [item["Id"] for item in group_items if "Id" in item]
        if item_ids:
            create_collection(parsed.url, parsed.api_key, group_name, item_ids, dry_run=parsed.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
