import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

DEFAULT_PATTERNS = [
    r"^(.*?)\s+Part\s+\d+",
    r"^(.*?)\s+Vol(?:ume)?\.?\s*\d+",
    r"^(.*?)\s+\d+$",
    r"^(.*?):.*$",
    r"^(.*?)\s+-\s+.*$",
]


def load_config(config_path="config.json"):
    """Load configuration from environment variables and JSON file.

    Args:
        config_path: Path to configuration JSON file (default: 'config.json')

    Returns:
        Dictionary with merged configuration (environment overrides JSON)
    """
    config = {
        "JELLYFIN_URL": os.environ.get("JELLYFIN_URL", "http://localhost:8096"),
        "JELLYFIN_API_KEY": os.environ.get("JELLYFIN_API_KEY", ""),
        "DRY_RUN": os.environ.get("DRY_RUN", "true").lower() in ("true", "1", "yes"),
        "MIN_GROUP_SIZE": int(os.environ.get("MIN_GROUP_SIZE", "2")),
        "PATTERNS": DEFAULT_PATTERNS,
    }

    config_path_obj = Path(config_path)
    if config_path_obj.exists():
        try:
            with config_path_obj.open("r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
            logging.info(f"Loaded configuration from {config_path}")
        except Exception:
            logging.warning(f"Failed to load {config_path}", exc_info=True)

    return config


def get_headers(api_key):
    """Get headers for Jellyfin API requests.

    Args:
        api_key: Jellyfin API key for authentication

    Returns:
        Dictionary with authentication headers
    """
    return {"X-Emby-Token": api_key, "Content-Type": "application/json"}


def clean_title(title):
    """Clean movie title by removing year tags and extra formatting.

    Args:
        title: Original movie title string

    Returns:
        Cleaned title string suitable for grouping
    """
    if not title:
        return ""

    # Remove year tags like (2020) or [1080p]
    title = re.sub(r"[\[\(]\d{4}[\]\)]", "", title)
    title = re.sub(r"[\[\(].*?[\]\)]", "", title)
    # Strip trailing punctuation
    title = title.strip(" :-")
    return title.strip()


def extract_base_title(title, patterns):
    """Extract base title from a movie title using regex patterns.

    Args:
        title: Movie title to process
        patterns: List of regex patterns to match against the title

    Returns:
        Base title extracted from the movie title, or cleaned title if no pattern matches
    """
    if not title:
        return ""

    cleaned = clean_title(title)
    for pattern in patterns:
        try:
            match = re.match(pattern, cleaned, re.IGNORECASE)
            if match:
                base = match.group(1).strip()
                if base:
                    return base
        except re.error as e:
            logging.warning(f"Invalid regex pattern '{pattern}': {e}")
            continue
    return cleaned


def get_libraries(url, api_key):
    """Get all libraries from Jellyfin server.

    Args:
        url: Jellyfin server URL
        api_key: Jellyfin API key for authentication

    Returns:
        List of library dictionaries, empty list on error
    """
    endpoint = f"{url.rstrip('/')}/Views"
    try:
        res = requests.get(endpoint, headers=get_headers(api_key), timeout=10)
        res.raise_for_status()
        return res.json().get("Items", [])
    except Exception:
        logging.exception("Error fetching libraries:")
        return []


def get_library_items(url, api_key, parent_id):
    """Get all items from a specific library.

    Args:
        url: Jellyfin server URL
        api_key: Jellyfin API key for authentication
        parent_id: ID of the library to fetch items from

    Returns:
        List of item dictionaries from the library, empty list on error
    """
    endpoint = f"{url.rstrip('/')}/Items"
    params = {
        "ParentId": parent_id,
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Series",
        "Fields": "Name,Id",
    }
    try:
        res = requests.get(
            endpoint, headers=get_headers(api_key), params=params, timeout=15
        )
        res.raise_for_status()
        return res.json().get("Items", [])
    except Exception:
        logging.exception(f"Error fetching library items for parent {parent_id}:")
        return []


def group_items(items, patterns, min_group_size=2):
    """Group items by common base titles using regex patterns.

    Args:
        items: List of item dictionaries from Jellyfin
        patterns: List of regex patterns for extracting base titles
        min_group_size: Minimum number of items required to create a group

    Returns:
        Dictionary mapping base titles to lists of item dictionaries
    """
    groups = {}
    for item in items:
        name = item.get("Name", "")
        base = extract_base_title(name, patterns)
        if base not in groups:
            groups[base] = []
        groups[base].append(item)

    # Filter out groups that are smaller than min_group_size
    return {k: v for k, v in groups.items() if len(v) >= min_group_size}


def create_collection(url, api_key, collection_name, item_ids):
    """Create a new collection in Jellyfin.

    Args:
        url: Jellyfin server URL
        api_key: Jellyfin API key for authentication
        collection_name: Name for the new collection
        item_ids: List of item IDs to include in the collection

    Returns:
        Collection ID if successful, None on failure
    """
    if not item_ids:
        logging.error("Cannot create collection with empty item list")
        return None

    endpoint = f"{url.rstrip('/')}/Collections"
    params = {"Name": collection_name, "Ids": ",".join(item_ids)}
    try:
        res = requests.post(
            endpoint, headers=get_headers(api_key), params=params, timeout=10
        )
        res.raise_for_status()
        logging.info(
            f"Successfully created collection: '{collection_name}' with {len(item_ids)} items."
        )
        return res.json().get("Id")
    except Exception:
        logging.exception(f"Error creating collection '{collection_name}':")
        return None


def add_to_collection(url, api_key, collection_id, item_ids):
    """Add items to an existing collection.

    Args:
        url: Jellyfin server URL
        api_key: Jellyfin API key for authentication
        collection_id: ID of the collection to add items to
        item_ids: List of item IDs to add to the collection

    Returns:
        True if successful, False otherwise
    """
    if not item_ids:
        logging.warning("No items to add to collection")
        return False

    endpoint = f"{url.rstrip('/')}/Collections/{collection_id}/Items"
    params = {"Ids": ",".join(item_ids)}
    try:
        res = requests.post(
            endpoint, headers=get_headers(api_key), params=params, timeout=10
        )
        res.raise_for_status()
    except Exception:
        logging.exception(f"Error adding items to collection {collection_id}:")
        return False
    logging.info(f"Successfully added items to collection {collection_id}.")
    return True


def main():
    """Main entry point for the auto-grouping CLI."""
    parser = argparse.ArgumentParser(
        description="Automatically group Jellyfin items into collections based on title patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m jellyfin_auto_groupings.cli --config myconfig.json
  python -m jellyfin_auto_groupings.cli --dry-run
  JELLYFIN_API_KEY=xxx JELLYFIN_URL=http://jellyfin:8096 python -m jellyfin_auto_groupings.cli
        """,
    )
    parser.add_argument(
        "--config", default="config.json", help="Path to configuration JSON file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry run mode without creating collections",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_config(args.config)
    if args.dry_run:
        config["DRY_RUN"] = True

    if not config["JELLYFIN_API_KEY"]:
        logging.error(
            "JELLYFIN_API_KEY is required. Please set it in config.json or env var."
        )
        sys.exit(1)

    logging.info(f"Starting auto-grouping (Dry Run: {config['DRY_RUN']})...")

    libraries = get_libraries(config["JELLYFIN_URL"], config["JELLYFIN_API_KEY"])
    logging.info(f"Found {len(libraries)} libraries.")

    for lib in libraries:
        lib_name = lib.get("Name")
        lib_id = lib.get("Id")
        logging.info(f"Processing library: '{lib_name}' ({lib_id})")

        items = get_library_items(
            config["JELLYFIN_URL"], config["JELLYFIN_API_KEY"], lib_id
        )
        logging.info(f"Retrieved {len(items)} items from '{lib_name}'.")

        groups = group_items(
            items, config["PATTERNS"], min_group_size=config["MIN_GROUP_SIZE"]
        )
        logging.info(
            f"Found {len(groups)} potential collection groups in '{lib_name}'."
        )

        for group_name, group_items_list in groups.items():
            item_names = [i.get("Name") for i in group_items_list]
            item_ids = [i.get("Id") for i in group_items_list]
            collection_title = f"{group_name} Collection"

            logging.info(f"Group '{collection_title}': {item_names}")
            if not config["DRY_RUN"]:
                create_collection(
                    config["JELLYFIN_URL"],
                    config["JELLYFIN_API_KEY"],
                    collection_title,
                    item_ids,
                )


if __name__ == "__main__":
    main()
