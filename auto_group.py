import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

import requests

from utils.helpers import items_from_body

logger = logging.getLogger(__name__)

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


def _env_int(name, default):
    """Read an integer environment variable, falling back to *default*.

    A malformed value (e.g. ``MIN_GROUP_SIZE=abc``) used to raise
    :class:`ValueError` while importing this module, which aborted the CLI
    before it could print anything actionable. Logging a warning and using the
    default keeps the run alive.

    Args:
        name: Environment variable name.
        default: Value to use when the variable is unset or unparseable.

    Returns:
        The parsed integer, or *default*.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s value %r, falling back to default %s", name, raw, default
        )
        return default


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
        "MIN_GROUP_SIZE": _env_int("MIN_GROUP_SIZE", 2),
        "PATTERNS": DEFAULT_PATTERNS,
    }

    config_path_obj = Path(config_path)
    if config_path_obj.exists():
        try:
            with config_path_obj.open("r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
            logger.info(f"Loaded configuration from {config_path}")
        except Exception:
            logger.warning(f"Failed to load {config_path}", exc_info=True)

    # The JSON file can override any key, so re-validate the values the rest of
    # the module assumes are well-typed. A string "3" or a null MIN_GROUP_SIZE
    # would otherwise blow up in group_items() with a TypeError.
    try:
        config["MIN_GROUP_SIZE"] = int(config.get("MIN_GROUP_SIZE", 2))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid MIN_GROUP_SIZE %r, falling back to 2",
            config.get("MIN_GROUP_SIZE"),
        )
        config["MIN_GROUP_SIZE"] = 2
    if config["MIN_GROUP_SIZE"] < 1:
        logger.warning(
            "MIN_GROUP_SIZE %s is below 1, using 1", config["MIN_GROUP_SIZE"]
        )
        config["MIN_GROUP_SIZE"] = 1

    patterns = config.get("PATTERNS")
    if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
        logger.warning("PATTERNS must be a list of strings, using defaults")
        config["PATTERNS"] = DEFAULT_PATTERNS

    # A JSON file may carry DRY_RUN as the string "false". Left alone, that
    # string is truthy and silently keeps the run in dry-run mode.
    dry_run = config.get("DRY_RUN")
    if isinstance(dry_run, str):
        config["DRY_RUN"] = dry_run.strip().lower() in ("true", "1", "yes", "on")
    else:
        config["DRY_RUN"] = bool(dry_run)

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
        Base title extracted from the movie title, or the cleaned title when no
        pattern matches.

    Patterns are user-supplied via the ``PATTERNS`` config key, so they are not
    required to declare a capture group, and a declared group may not have
    participated in the match (for example ``(\\d{4})|(.*)``). Both cases used
    to raise and abort the entire run; the first participating group is used
    now, falling back to the whole match.
    """
    if not title:
        return ""

    cleaned = clean_title(title)
    for pattern in patterns:
        try:
            match = re.match(pattern, cleaned, re.IGNORECASE)
            if not match:
                continue
            base = next(
                (group for group in match.groups() if group is not None),
                match.group(0),
            ).strip()
            if base:
                return base
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
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
        return items_from_body(res.json())
    except Exception:
        logger.exception("Error fetching libraries:")
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
        return items_from_body(res.json())
    except Exception:
        logger.exception(f"Error fetching library items for parent {parent_id}:")
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
        name = item.get("Name")
        # Jellyfin returns ``null`` names for some corrupt entries; treating
        # them as "" merged every such item into one bogus ``""`` group.
        if not isinstance(name, str) or not name.strip():
            logger.debug("Skipping item without a usable name: %r", item)
            continue
        base = extract_base_title(name, patterns)
        if not base:
            continue
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
    # Jellyfin rejects a request whose ``Ids`` list holds an unusable entry, so
    # drop them here instead of sending a malformed query string.
    item_ids = [str(i) for i in item_ids if isinstance(i, str) and i.strip()]
    if not item_ids:
        logger.error("Cannot create collection with empty item list")
        return None

    endpoint = f"{url.rstrip('/')}/Collections"
    params = {"Name": collection_name, "Ids": ",".join(item_ids)}
    try:
        res = requests.post(
            endpoint, headers=get_headers(api_key), params=params, timeout=10
        )
        res.raise_for_status()
        logger.info(
            f"Successfully created collection: '{collection_name}' with {len(item_ids)} items."
        )
        try:
            return res.json().get("Id")
        except ValueError:
            # Jellyfin can answer 200 with no body; the collection was still
            # created, so do not report this as a failure.
            logger.debug("Collection response had no JSON body: %s", collection_name)
            return None
    except Exception:
        logger.exception(f"Error creating collection '{collection_name}':")
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
    item_ids = [str(i) for i in item_ids if isinstance(i, str) and i.strip()]
    if not item_ids:
        logger.warning("No items to add to collection")
        return False

    endpoint = f"{url.rstrip('/')}/Collections/{collection_id}/Items"
    params = {"Ids": ",".join(item_ids)}
    try:
        res = requests.post(
            endpoint, headers=get_headers(api_key), params=params, timeout=10
        )
        res.raise_for_status()
    except Exception:
        logger.exception(f"Error adding items to collection {collection_id}:")
        return False
    logger.info(f"Successfully added items to collection {collection_id}.")
    return True


def main():
    """Main entry point for the auto-grouping CLI."""
    parser = argparse.ArgumentParser(
        description="Automatically group Jellyfin items into collections based on title patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python auto_group.py --config myconfig.json
  python auto_group.py --dry-run --verbose
  JELLYFIN_API_KEY=xxx JELLYFIN_URL=http://jellyfin:8096 python auto_group.py

This script groups titles by pattern and creates one collection per group.
For the pattern + capture-group CLI from the installed package use
``python -m jellyfin_auto_groupings.cli --help`` instead.
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
        logger.error(
            "JELLYFIN_API_KEY is required. Please set it in config.json or env var."
        )
        sys.exit(1)

    logger.info(f"Starting auto-grouping (Dry Run: {config['DRY_RUN']})...")

    libraries = get_libraries(config["JELLYFIN_URL"], config["JELLYFIN_API_KEY"])
    logger.info(f"Found {len(libraries)} libraries.")

    for lib in libraries:
        lib_name = lib.get("Name")
        lib_id = lib.get("Id")
        logger.info(f"Processing library: '{lib_name}' ({lib_id})")

        items = get_library_items(
            config["JELLYFIN_URL"], config["JELLYFIN_API_KEY"], lib_id
        )
        logger.info(f"Retrieved {len(items)} items from '{lib_name}'.")

        groups = group_items(
            items, config["PATTERNS"], min_group_size=config["MIN_GROUP_SIZE"]
        )
        logger.info(f"Found {len(groups)} potential collection groups in '{lib_name}'.")

        for group_name, group_items_list in groups.items():
            item_names = [i.get("Name") for i in group_items_list]
            item_ids = [i.get("Id") for i in group_items_list]
            # Jellyfin rejects the entire collection when one ID is unusable.
            item_ids = [i for i in item_ids if isinstance(i, str) and i.strip()]
            collection_title = f"{group_name} Collection"

            logger.info(f"Group '{collection_title}': {item_names}")
            if not config["DRY_RUN"]:
                if not item_ids:
                    logger.warning(
                        "Skipping '%s': no usable item IDs", collection_title
                    )
                    continue
                create_collection(
                    config["JELLYFIN_URL"],
                    config["JELLYFIN_API_KEY"],
                    collection_title,
                    item_ids,
                )


if __name__ == "__main__":
    main()
