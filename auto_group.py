import os
import sys
import re
import json
import logging
import argparse
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEFAULT_PATTERNS = [
    r'^(.*?)\s+Part\s+\d+',
    r'^(.*?)\s+Vol(?:ume)?\.?\s*\d+',
    r'^(.*?)\s+\d+$',
    r'^(.*?):.*$',
    r'^(.*?)\s+-\s+.*$',
]

def load_config(config_path="config.json"):
    config = {
        "JELLYFIN_URL": os.environ.get("JELLYFIN_URL", "http://localhost:8096"),
        "JELLYFIN_API_KEY": os.environ.get("JELLYFIN_API_KEY", ""),
        "DRY_RUN": os.environ.get("DRY_RUN", "true").lower() in ("true", "1", "yes"),
        "MIN_GROUP_SIZE": int(os.environ.get("MIN_GROUP_SIZE", "2")),
        "PATTERNS": DEFAULT_PATTERNS
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
            logging.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logging.warning(f"Failed to load {config_path}: {e}")
            
    return config

def get_headers(api_key):
    return {
        "X-Emby-Token": api_key,
        "Content-Type": "application/json"
    }

def clean_title(title):
    # Remove year tags like (2020) or [1080p]
    title = re.sub(r'[\[\(]\d{4}[\]\)]', '', title)
    title = re.sub(r'[\[\(].*?[\]\)]', '', title)
    # Strip trailing punctuation
    title = title.strip(" :-")
    return title.strip()

def extract_base_title(title, patterns):
    cleaned = clean_title(title)
    for pattern in patterns:
        match = re.match(pattern, cleaned, re.IGNORECASE)
        if match:
            base = match.group(1).strip()
            if base:
                return base
    return cleaned

def get_libraries(url, api_key):
    endpoint = f"{url.rstrip('/')}/Views"
    try:
        res = requests.get(endpoint, headers=get_headers(api_key), timeout=10)
        res.raise_for_status()
        return res.json().get("Items", [])
    except Exception as e:
        logging.error(f"Error fetching libraries: {e}")
        return []

def get_library_items(url, api_key, parent_id):
    endpoint = f"{url.rstrip('/')}/Items"
    params = {
        "ParentId": parent_id,
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Series",
        "Fields": "Name,Id"
    }
    try:
        res = requests.get(endpoint, headers=get_headers(api_key), params=params, timeout=15)
        res.raise_for_status()
        return res.json().get("Items", [])
    except Exception as e:
        logging.error(f"Error fetching library items for parent {parent_id}: {e}")
        return []

def group_items(items, patterns, min_group_size=2):
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
    endpoint = f"{url.rstrip('/')}/Collections"
    params = {
        "Name": collection_name,
        "Ids": ",".join(item_ids)
    }
    try:
        res = requests.post(endpoint, headers=get_headers(api_key), params=params, timeout=10)
        res.raise_for_status()
        logging.info(f"Successfully created collection: '{collection_name}' with {len(item_ids)} items.")
        return res.json().get("Id")
    except Exception as e:
        logging.error(f"Error creating collection '{collection_name}': {e}")
        return None

def add_to_collection(url, api_key, collection_id, item_ids):
    endpoint = f"{url.rstrip('/')}/Collections/{collection_id}/Items"
    params = {
        "Ids": ",".join(item_ids)
    }
    try:
        res = requests.post(endpoint, headers=get_headers(api_key), params=params, timeout=10)
        res.raise_for_status()
        logging.info(f"Successfully added items to collection {collection_id}.")
    except Exception as e:
        logging.error(f"Error adding items to collection {collection_id}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Automatically group Jellyfin items into collections based on title patterns.")
    parser.add_argument("--config", default="config.json", help="Path to configuration JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry run mode without creating collections")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.dry_run:
        config["DRY_RUN"] = True

    if not config["JELLYFIN_API_KEY"]:
        logging.error("JELLYFIN_API_KEY is required. Please set it in config.json or env var.")
        sys.exit(1)

    logging.info(f"Starting auto-grouping (Dry Run: {config['DRY_RUN']})...")
    
    libraries = get_libraries(config["JELLYFIN_URL"], config["JELLYFIN_API_KEY"])
    logging.info(f"Found {len(libraries)} libraries.")

    for lib in libraries:
        lib_name = lib.get("Name")
        lib_id = lib.get("Id")
        logging.info(f"Processing library: '{lib_name}' ({lib_id})")
        
        items = get_library_items(config["JELLYFIN_URL"], config["JELLYFIN_API_KEY"], lib_id)
        logging.info(f"Retrieved {len(items)} items from '{lib_name}'.")

        groups = group_items(items, config["PATTERNS"], min_group_size=config["MIN_GROUP_SIZE"])
        logging.info(f"Found {len(groups)} potential collection groups in '{lib_name}'.")

        for group_name, group_items_list in groups.items():
            item_names = [i.get('Name') for i in group_items_list]
            item_ids = [i.get('Id') for i in group_items_list]
            collection_title = f"{group_name} Collection"
            
            logging.info(f"Group '{collection_title}': {item_names}")
            if not config["DRY_RUN"]:
                create_collection(config["JELLYFIN_URL"], config["JELLYFIN_API_KEY"], collection_title, item_ids)

if __name__ == '__main__':
    main()
