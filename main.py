import logging
import os
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class JellyfinGroupings:
    def __init__(self, server_url: Optional[str] = None, api_key: Optional[str] = None, timeout: int = 10) -> None:
        """
        Initialize JellyfinGroupings client.
        
        :param server_url: Base URL of Jellyfin server. Defaults to JELLYFIN_URL env var.
        :param api_key: Jellyfin API Key. Defaults to JELLYFIN_API_KEY env var.
        :param timeout: HTTP request timeout in seconds.
        """
        self.server_url = (server_url or os.getenv("JELLYFIN_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("JELLYFIN_API_KEY", "")
        self.timeout = timeout
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key:
            err_msg = "API key is missing."
            raise ValueError(err_msg)
        return {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json"
        }

    def get_collections(self) -> List[Dict[str, Any]]:
        """Fetch all collection folders from Jellyfin."""
        if not self.server_url:
            err_msg = "Server URL is missing."
            raise ValueError(err_msg)
        url = f"{self.server_url}/Items?IncludeItemTypes=BoxSet&Recursive=true"
        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("Items", [])
        except requests.RequestException:
            logger.exception("Failed to fetch collections")
            raise

    def get_movies(self) -> List[Dict[str, Any]]:
        """Fetch all movie items from Jellyfin."""
        if not self.server_url:
            err_msg = "Server URL is missing."
            raise ValueError(err_msg)
        url = f"{self.server_url}/Items?IncludeItemTypes=Movie&Recursive=true"
        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("Items", [])
        except requests.RequestException:
            logger.exception("Failed to fetch movies")
            raise

    def create_collection(self, name: str) -> Dict[str, Any]:
        """Create a new boxset collection by name in Jellyfin."""
        if not self.server_url:
            err_msg = "Server URL is missing."
            raise ValueError(err_msg)
        url = f"{self.server_url}/Collections?Name={name}"
        try:
            response = self.session.post(url, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            logger.exception(f"Failed to create collection: {name}")
            raise

    def add_to_collection(self, collection_id: str, item_ids: List[str]) -> None:
        """Add movie/item IDs to an existing collection in Jellyfin."""
        if not self.server_url:
            err_msg = "Server URL is missing."
            raise ValueError(err_msg)
        if not item_ids:
            return
        ids_param = ",".join(item_ids)
        url = f"{self.server_url}/Collections/{collection_id}/Items?Ids={ids_param}"
        try:
            response = self.session.post(url, headers=self._get_headers(), timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            logger.exception(f"Failed to add items to collection {collection_id}")
            raise

    def auto_group(self) -> Dict[str, Any]:
        """
        Main execution entry point to process and group items.
        """
        logger.info("Starting Jellyfin auto-grouping process...")
        try:
            collections = self.get_collections()
            logger.info(f"Successfully fetched {len(collections)} collections.")
            return {"status": "success", "collections_count": len(collections), "collections": collections}
        except Exception:
            logger.exception("Error during auto-grouping")
            return {"status": "error", "message": "Error during auto-grouping"}

    def group_movies_by_collection(self) -> Dict[str, Any]:
        """
        Group Jellyfin movies into collections based on metadata CollectionName.
        """
        logger.info("Starting group_movies_by_collection process...")
        try:
            movies = self.get_movies()
            existing_collections = {col["Name"]: col["Id"] for col in self.get_collections() if "Name" in col and "Id" in col}
            collections_to_create: Dict[str, List[str]] = {}

            for movie in movies:
                collection_name = movie.get("CollectionName")
                movie_id = movie.get("Id")
                if collection_name and movie_id:
                    if collection_name not in collections_to_create:
                        collections_to_create[collection_name] = []
                    collections_to_create[collection_name].append(movie_id)

            created_count = 0
            for collection_name, movie_ids in collections_to_create.items():
                if collection_name not in existing_collections:
                    logger.info(f"Creating collection: {collection_name}")
                    new_collection = self.create_collection(collection_name)
                    collection_id = new_collection.get("Id")
                    if collection_id:
                        existing_collections[collection_name] = collection_id
                    created_count += 1
                else:
                    collection_id = existing_collections[collection_name]

                if collection_id:
                    logger.info(f"Adding movies to collection {collection_name}: {movie_ids}")
                    self.add_to_collection(collection_id, movie_ids)

            return {
                "status": "success",
                "collections_created": created_count,
                "grouped_collections": len(collections_to_create)
            }
        except Exception:
            logger.exception("Error grouping movies by collection")
            return {"status": "error", "message": "Error grouping movies by collection"}
