import os
import requests
from typing import Dict, List, Any, Optional

class JellyfinGroupings:
    """Client for managing Jellyfin collection groupings automatically."""

    def __init__(self, url: str, api_key: str) -> None:
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-Emby-Token': self.api_key,
            'Content-Type': 'application/json'
        }

    def get_collections(self) -> List[Dict[str, Any]]:
        """Retrieve all existing collections (BoxSets) from Jellyfin."""
        endpoint = f"{self.url}/Collections"
        params = {
            'IncludeItemTypes': 'BoxSet',
            'Recursive': True
        }
        response = requests.get(endpoint, headers=self.headers, params=params)
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        return data.get('Items', [])

    def get_movies(self) -> List[Dict[str, Any]]:
        """Retrieve all movies with ProviderIds from Jellyfin."""
        endpoint = f"{self.url}/Items"
        params = {
            'IncludeItemTypes': 'Movie',
            'Recursive': True,
            'Fields': 'ProviderIds'
        }
        response = requests.get(endpoint, headers=self.headers, params=params)
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        return data.get('Items', [])

    def create_collection(self, name: str, item_ids: List[str]) -> Dict[str, Any]:
        """Create a new collection with specified item IDs."""
        endpoint = f"{self.url}/Collections"
        params = {
            'Name': name,
            'Ids': ','.join(item_ids)
        }
        response = requests.post(endpoint, headers=self.headers, params=params)
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        return data

    def add_to_collection(self, collection_id: str, item_ids: List[str]) -> None:
        """Add items to an existing collection."""
        endpoint = f"{self.url}/Collections/{collection_id}/Items"
        params = {
            'Ids': ','.join(item_ids)
        }
        response = requests.post(endpoint, headers=self.headers, params=params)
        response.raise_for_status()

def main() -> None:
    """Main entry point to execute grouping sync."""
    url = os.environ.get('JELLYFIN_URL', 'http://localhost:8096')
    api_key = os.environ.get('JELLYFIN_API_KEY', '')

    if not api_key:
        print("Error: JELLYFIN_API_KEY environment variable is required.")
        return

    client = JellyfinGroupings(url, api_key)
    collections = client.get_collections()
    movies = client.get_movies()

    print(f"Found {len(collections)} existing collections.")
    print(f"Found {len(movies)} movies.")

if __name__ == '__main__':
    main()
