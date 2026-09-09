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
