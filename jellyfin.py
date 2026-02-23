"""
jellyfin.py – Jellyfin API client helpers.

Contains the sort-order mapping used across the application and a thin
convenience wrapper around ``requests.get`` for fetching items from the
Jellyfin ``/Items`` endpoint.
"""

from __future__ import annotations

from typing import Any

import requests

# ---------------------------------------------------------------------------
# Sort-order mapping
# ---------------------------------------------------------------------------

# Maps internal ``sort_order`` keys to the Jellyfin API ``SortBy`` /
# ``SortOrder`` query parameter pairs.
#
# ``"imdb_list_order"``, ``"trakt_list_order"``, and ``""`` are handled
# separately by the sync logic and do **not** appear in this map.
SORT_MAP: dict[str, tuple[str, str]] = {
    "CommunityRating": ("CommunityRating", "Descending"),
    "ProductionYear": ("ProductionYear,SortName", "Descending,Ascending"),
    "SortName": ("SortName", "Ascending"),
    "DateCreated": ("DateCreated", "Descending"),
    "Random": ("Random", "Ascending"),
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def fetch_jellyfin_items(
    base_url: str,
    api_key: str,
    extra_params: dict[str, str] | None = None,
    *,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Fetch the ``Items`` list from the Jellyfin ``/Items`` endpoint.

    Builds query parameters, performs a GET request, and returns the parsed
    ``Items`` list from the JSON response.

    Args:
        base_url: Jellyfin server base URL (no trailing slash), e.g.
            ``"http://localhost:8096"``.
        api_key: Jellyfin API key.
        extra_params: Additional query-string parameters to merge into the
            request (e.g. ``{"IncludeItemTypes": "Movie,Series"}``).
        timeout: HTTP request timeout in seconds.

    Returns:
        The ``Items`` list from the Jellyfin response, or an empty list if
        the response contained no ``Items`` key.

    Raises:
        requests.HTTPError: If the server returns a non-2xx status code.
        requests.RequestException: For any other network-level error.
    """
    params: dict[str, str] = {"api_key": api_key}
    if extra_params:
        params.update(extra_params)

    response = requests.get(f"{base_url}/Items", params=params, timeout=timeout)
    response.raise_for_status()
    return response.json().get("Items", [])


def get_libraries(base_url: str, api_key: str, timeout: int = 30) -> list[str]:
    """Fetch the list of virtual folder (library) names from Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        timeout: HTTP request timeout.

    Returns:
        A list of library names.
    """
    response = requests.get(
        f"{base_url}/Library/VirtualFolders",
        params={"api_key": api_key},
        timeout=timeout,
    )
    response.raise_for_status()
    return [folder.get("Name", "") for folder in response.json()]


def add_virtual_folder(
    base_url: str,
    api_key: str,
    name: str,
    paths: list[str],
    collection_type: str = "movies",
    refresh_library: bool = True,
    timeout: int = 30,
) -> None:
    """Create a new virtual folder (library) in Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Name of the new library.
        paths: List of absolute paths to include in the library.
        collection_type: Type of media (e.g., "movies", "tvshows", "music", "mixed").
        refresh_library: Whether to trigger a library scan after creation.
        timeout: HTTP request timeout.
    """
    # Strategy: Try to create with all info in query string first (most common for simple cases)
    # If it already exists, we skip creation.
    
    headers = {"X-Emby-Token": api_key}
    
    # Step 1: Create the virtual folder shell
    # We omit 'paths' here to avoid the 400 error.
    create_params = {
        "name": name,
        "collectionType": collection_type if collection_type != "mixed" else "movies",
        "refreshLibrary": "false",
    }
    
    try:
        # data="" ensures non-JSON POST works for creation if needed
        create_resp = requests.post(
            f"{base_url}/Library/VirtualFolders",
            params=create_params,
            headers=headers,
            data="",
            timeout=timeout,
        )
        if create_resp.status_code != 409:
            create_resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        msg = f"Failed to create virtual folder {name!r}"
        if hasattr(exc, "response") and exc.response is not None:
            msg += f" (Status {exc.response.status_code}): {exc.response.text}"
        else:
            msg += f": {exc!s}"
        raise RuntimeError(msg) from exc

    # Step 2: Add each path using strictly a JSON body as recommended
    for path in paths:
        path_url = f"{base_url}/Library/VirtualFolders/Paths"
        payload = {
            "Name": name,
            "Path": path
        }
        
        try:
            # We use json= which automatically sets Content-Type: application/json
            path_resp = requests.post(
                path_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            path_resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            msg = f"Failed to add path {path!r} to library {name!r}"
            if hasattr(exc, "response") and exc.response is not None:
                msg += f" (Status {exc.response.status_code}): {exc.response.text}"
            else:
                msg += f": {exc!s}"
            raise RuntimeError(msg) from exc
            
    # Step 3: Trigger a library refresh if requested
    if refresh_library:
        try:
            refresh_resp = requests.post(
                f"{base_url}/Library/Refresh",
                headers=headers,
                timeout=timeout
            )
            refresh_resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            msg = f"Failed to trigger library refresh for {name!r}"
            if hasattr(exc, "response") and exc.response is not None:
                msg += f" (Status {exc.response.status_code}): {exc.response.text}"
            else:
                msg += f": {exc!s}"
            raise RuntimeError(msg) from exc


def delete_virtual_folder(base_url: str, api_key: str, name: str, timeout: int = 30) -> None:
    """Delete a virtual folder (library) from Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Name of the library to delete.
        timeout: HTTP request timeout.
    """
    params = {"name": name}
    headers = {"X-Emby-Token": api_key}
    response = requests.delete(
        f"{base_url}/Library/VirtualFolders",
        params=params,
        headers=headers,
        timeout=timeout,
    )
    if not response.ok:
        print(f"DEBUG: Delete Virtual Folder Failed ({response.status_code}): {response.text}")
    response.raise_for_status()
