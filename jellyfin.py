"""
jellyfin.py – Jellyfin API client helpers.

Contains the sort-order mapping used across the application and a thin
convenience wrapper around ``requests.get`` for fetching items from the
Jellyfin ``/Items`` endpoint.
"""

from __future__ import annotations

from typing import Any, NoReturn

import mimetypes
import logging
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COLLECTION_PAGE_LIMIT = 200

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


def _auth_headers(api_key: str) -> dict[str, str]:
    """Return Jellyfin authentication headers for *api_key*."""
    return {"X-Emby-Token": api_key}


def _format_request_error(exc: requests.exceptions.RequestException, prefix: str) -> str:
    """Build a human-readable error message from *exc* with response details if available."""
    msg = prefix
    if hasattr(exc, "response") and exc.response is not None:
        msg += f" (Status {exc.response.status_code}): {exc.response.text}"
    else:
        msg += f": {exc!s}"
    return msg


def _raise_request_error(exc: requests.exceptions.RequestException, prefix: str) -> NoReturn:
    """Format *exc* into a ``RuntimeError`` with response details if available."""
    raise RuntimeError(_format_request_error(exc, prefix)) from exc


def _parse_json(response: requests.Response) -> Any:
    """Safely parse *response* JSON, translating decode failures into ``RuntimeError``."""
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        snippet = response.text[:200]
        raise RuntimeError(
            f"Invalid JSON response (status {response.status_code}): {snippet}"
        ) from exc


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
        requests.exceptions.RequestException: For any other network-level error.
    """
    headers = _auth_headers(api_key)
    params: dict[str, str] = {}
    if extra_params:
        params.update(extra_params)

    response = requests.get(f"{base_url}/Items", headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    return _parse_json(response).get("Items", [])


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
        headers=_auth_headers(api_key),
        timeout=timeout,
    )
    response.raise_for_status()
    return [folder.get("Name", "") for folder in _parse_json(response)]


def get_users(base_url: str, api_key: str, timeout: int = 30) -> list[dict[str, Any]]:
    """Fetch the list of users from Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        timeout: HTTP request timeout.

    Returns:
        A list of user dictionaries.
    """
    response = requests.get(
        f"{base_url}/Users",
        headers=_auth_headers(api_key),
        timeout=timeout,
    )
    response.raise_for_status()
    return _parse_json(response)


def get_user_recent_items(
    base_url: str, api_key: str, user_id: str, limit: int = 20, timeout: int = 30
) -> list[dict[str, Any]]:
    """Fetch a user's recently played movies and shows.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        user_id: ID of the user.
        limit: Number of items to fetch.
        timeout: HTTP request timeout.

    Returns:
        A list of item dictionaries.
    """
    params = {
        "Filters": "IsPlayed",
        "SortBy": "DatePlayed",
        "SortOrder": "Descending",
        "IncludeItemTypes": "Movie,Series",
        "Recursive": "true",
        "Limit": str(limit),
        "Fields": "ProviderIds",
    }
    response = requests.get(
        f"{base_url}/Users/{user_id}/Items",
        headers=_auth_headers(api_key),
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return _parse_json(response).get("Items", [])


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

    headers = _auth_headers(api_key)

    # Step 1: Create the virtual folder shell
    # We omit 'paths' here to avoid the 400 error.
    create_params = {
        "name": name,
        "refreshLibrary": "false",
    }
    if collection_type != "mixed":
        create_params["collectionType"] = collection_type

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
        _raise_request_error(exc, f"Failed to create virtual folder {name!r}")

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
            _raise_request_error(
                exc, f"Failed to add path {path!r} to library {name!r}"
            )

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
            _raise_request_error(
                exc, f"Failed to trigger library refresh for {name!r}"
            )


def delete_virtual_folder(base_url: str, api_key: str, name: str, timeout: int = 30) -> None:
    """Delete a virtual folder (library) from Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Name of the library to delete.
        timeout: HTTP request timeout.
    """
    params = {"name": name}
    headers = _auth_headers(api_key)
    response = requests.delete(
        f"{base_url}/Library/VirtualFolders",
        params=params,
        headers=headers,
        timeout=timeout,
    )
    if not response.ok:
        logger.warning("Delete Virtual Folder Failed (%s): %s", response.status_code, response.text)
    response.raise_for_status()


def get_library_id(base_url: str, api_key: str, name: str, timeout: int = 30) -> str | None:
    """Get the ItemId of a virtual folder (library) from Jellyfin by name.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Name of the library.
        timeout: HTTP request timeout.

    Returns:
        The string ItemId of the library if found, else None.
    """
    response = requests.get(
        f"{base_url}/Library/VirtualFolders",
        headers=_auth_headers(api_key),
        timeout=timeout,
    )
    response.raise_for_status()

    for folder in _parse_json(response):
        if folder.get("Name") == name:
            item_id = folder.get("ItemId")
            if item_id is not None:
                return str(item_id)

    return None


def _upload_image(
    base_url: str,
    api_key: str,
    item_id: str,
    image_path: str,
    timeout: int = 30,
) -> None:
    """Upload *image_path* to Jellyfin as the primary image for *item_id*.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        item_id: Jellyfin item / library / collection ID.
        image_path: Absolute path to the local image file to upload.
        timeout: HTTP request timeout.
    """
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    mime_type, _ = mimetypes.guess_type(image_path)
    headers = _auth_headers(api_key)
    headers["Content-Type"] = mime_type or "application/octet-stream"
    url = f"{base_url}/Items/{item_id}/Images/Primary"
    response = requests.post(url, data=image_bytes, headers=headers, timeout=timeout)
    response.raise_for_status()


def set_virtual_folder_image(
    base_url: str,
    api_key: str,
    name: str,
    image_path: str,
    timeout: int = 30,
) -> None:
    """Set the primary image for a virtual folder (library) in Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Name of the library to update.
        image_path: Absolute path to the local image file to upload.
        timeout: HTTP request timeout.
    """
    try:
        library_id = get_library_id(base_url, api_key, name, timeout=timeout)
        if not library_id:
            logger.info("Cannot set image: Library %r not found or ID unknown.", name)
            return
        _upload_image(base_url, api_key, library_id, image_path, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        logger.info(
            _format_request_error(exc, f"Failed to set image for library {name!r}")
        )
    except OSError as exc:
        logger.error("Cannot set image: Failed to read image file %r: %s", image_path, exc)
    else:
        logger.info("Successfully updated cover image for library %r", name)


# ---------------------------------------------------------------------------
# Collection (Boxset) helpers
# ---------------------------------------------------------------------------


def create_collection(
    base_url: str,
    api_key: str,
    name: str,
    item_ids: list[str],
    timeout: int = 30,
) -> str:
    """Create a new Jellyfin Collection (Boxset) with the given items.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Display name for the collection.
        item_ids: List of Jellyfin item IDs to include in the collection.
        timeout: HTTP request timeout.

    Returns:
        The ``Id`` of the newly created collection.

    Raises:
        RuntimeError: If the API call fails.
    """
    headers = _auth_headers(api_key)
    params: dict[str, str] = {"Name": name, "Ids": ",".join(item_ids)}

    try:
        resp = requests.post(
            f"{base_url}/Collections",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = _parse_json(resp)
        collection_id: str | None = data.get("Id")
        if not collection_id:
            raise RuntimeError(f"Collection created but no Id returned for {name!r}")
        return collection_id
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, f"Failed to create collection {name!r}")


def find_collection_by_name(
    base_url: str,
    api_key: str,
    name: str,
    timeout: int = 30,
) -> str | None:
    """Find an existing Jellyfin Collection (Boxset) by name.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Exact name of the collection to find.
        timeout: HTTP request timeout.

    Returns:
        The collection ``Id`` if found, ``None`` otherwise.
    """
    headers = _auth_headers(api_key)
    limit = _COLLECTION_PAGE_LIMIT
    start_index = 0

    while True:
        params: dict[str, str | int] = {
            "IncludeItemTypes": "BoxSet",
            "Recursive": "true",
            "SearchTerm": name,
            "Limit": limit,
            "StartIndex": start_index,
        }

        resp = requests.get(
            f"{base_url}/Items",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = _parse_json(resp)
        items = data.get("Items", [])

        for item in items:
            if item.get("Name") == name:
                item_id: str | None = item.get("Id")
                if item_id:
                    return item_id

        total = data.get("TotalRecordCount", 0)
        start_index += len(items)
        if start_index >= total or not items:
            break

    return None


def add_to_collection(
    base_url: str,
    api_key: str,
    collection_id: str,
    item_ids: list[str],
    timeout: int = 30,
) -> None:
    """Add items to an existing Jellyfin Collection.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        collection_id: ID of the target collection.
        item_ids: List of item IDs to add.
        timeout: HTTP request timeout.

    Raises:
        RuntimeError: If the API call fails.
    """
    if not item_ids:
        return

    headers = _auth_headers(api_key)
    params: dict[str, str] = {"Ids": ",".join(item_ids)}

    try:
        resp = requests.post(
            f"{base_url}/Collections/{collection_id}/Items",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, f"Failed to add items to collection {collection_id!r}")


def remove_from_collection(
    base_url: str,
    api_key: str,
    collection_id: str,
    item_ids: list[str],
    timeout: int = 30,
) -> None:
    """Remove items from a Jellyfin Collection.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        collection_id: ID of the collection.
        item_ids: List of item IDs to remove.
        timeout: HTTP request timeout.

    Raises:
        RuntimeError: If the API call fails.
    """
    if not item_ids:
        return

    headers = _auth_headers(api_key)
    params: dict[str, str] = {"Ids": ",".join(item_ids)}

    try:
        resp = requests.delete(
            f"{base_url}/Collections/{collection_id}/Items",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, f"Failed to remove items from collection {collection_id!r}")


def delete_collection(
    base_url: str,
    api_key: str,
    collection_id: str,
    timeout: int = 30,
) -> None:
    """Delete a Jellyfin Collection (Boxset) by ID.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        collection_id: ID of the collection to delete.
        timeout: HTTP request timeout.

    Raises:
        RuntimeError: If the API call fails.
    """
    headers = _auth_headers(api_key)

    try:
        resp = requests.delete(
            f"{base_url}/Items/{collection_id}",
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, f"Failed to delete collection {collection_id!r}")


def set_collection_image(
    base_url: str,
    api_key: str,
    collection_id: str,
    image_path: str,
    timeout: int = 30,
) -> None:
    """Set the primary image for a Jellyfin Collection.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        collection_id: ID of the collection.
        image_path: Absolute path to the local image file to upload.
        timeout: HTTP request timeout.
    """
    try:
        _upload_image(base_url, api_key, collection_id, image_path, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        logger.info(
            _format_request_error(
                exc, f"Failed to set image for collection {collection_id!r}"
            )
        )
    except OSError as exc:
        logger.error("Cannot set collection image: Failed to read %r: %s", image_path, exc)
    else:
        logger.info("Successfully updated cover image for collection %r", collection_id)
