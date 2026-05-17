"""jellyfin.py - Jellyfin API client helpers.

Contains the sort-order mapping used across the application and a thin
convenience wrapper around ``requests.get`` for fetching items from the
Jellyfin ``/Items`` endpoint.
"""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Iterator
from typing import Any, Callable, NoReturn

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COLLECTION_PAGE_LIMIT = 200

# Default Jellyfin item types used across the application.
DEFAULT_ITEM_TYPES = "Movie,Series"

# String boolean values expected by the Jellyfin query API.
RECURSIVE_TRUE = "true"

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
            f"Invalid JSON response (status {response.status_code}): {snippet}",
        ) from exc


def _get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    """GET *url* and return the parsed JSON response.

    Raises:
        RuntimeError: If the request fails or the response body is not valid JSON.

    """
    kwargs: dict[str, Any] = {"timeout": timeout}
    if headers is not None:
        kwargs["headers"] = headers
    if params is not None:
        kwargs["params"] = params
    try:
        response = requests.get(url, **kwargs)  # noqa: S113
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, f"Failed to GET {url}")
    return _parse_json(response)


def _request_or_raise(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: Any = None,
    json: Any = None,
    timeout: int = 30,
    error_prefix: str = "",
) -> requests.Response:
    """Send a *method* request to *url* and return the response, translating errors into ``RuntimeError``.

    Raises:
        RuntimeError: On any ``RequestException``.

    """
    kwargs: dict[str, Any] = {"timeout": timeout}
    if headers is not None:
        kwargs["headers"] = headers
    if params is not None:
        kwargs["params"] = params
    if data is not None:
        kwargs["data"] = data
    if json is not None:
        kwargs["json"] = json
    try:
        if method == "POST":
            response = requests.post(url, **kwargs)  # noqa: S113
        elif method == "DELETE":
            response = requests.delete(url, **kwargs)  # noqa: S113
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, error_prefix)


def _post_or_raise(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: Any = None,
    json: Any = None,
    timeout: int = 30,
    error_prefix: str = "",
) -> requests.Response:
    """POST to *url* and return the response, translating errors into ``RuntimeError``."""
    return _request_or_raise(
        "POST", url, headers=headers, params=params, data=data, json=json, timeout=timeout, error_prefix=error_prefix,
    )


def _post_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: Any = None,
    json: Any = None,
    timeout: int = 30,
    error_prefix: str = "",
) -> Any:
    """POST to *url* and return the parsed JSON response, translating errors into ``RuntimeError``."""
    return _parse_json(
        _post_or_raise(url, headers=headers, params=params, data=data, json=json, timeout=timeout, error_prefix=error_prefix),
    )


def _delete_or_raise(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
    error_prefix: str = "",
) -> requests.Response:
    """DELETE *url* and return the response, translating errors into ``RuntimeError``."""
    return _request_or_raise(
        "DELETE", url, headers=headers, params=params, timeout=timeout, error_prefix=error_prefix,
    )


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
        RuntimeError: If the request fails or the response is not valid JSON.

    """
    headers = _auth_headers(api_key)
    params: dict[str, str] = {}
    if extra_params:
        params.update(extra_params)

    return _get_json(
        f"{base_url}/Items", headers=headers, params=params, timeout=timeout,
    ).get("Items", [])


def fetch_all_jellyfin_items(
    base_url: str,
    api_key: str,
    extra_params: dict[str, str] | None = None,
    *,
    limit: int = 200,
    timeout: int = 30,
    _fetch_page: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all items from the Jellyfin ``/Items`` endpoint, handling pagination.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        extra_params: Additional query-string parameters for every request.
        limit: Number of items to request per page.
        timeout: HTTP request timeout in seconds.
        _fetch_page: Optional callable used to fetch a single page. Defaults to
            :func:`fetch_jellyfin_items`.

    Returns:
        Concatenated list of all ``Items`` across all pages.

    """
    fetch_page = _fetch_page or fetch_jellyfin_items
    all_items: list[dict[str, Any]] = []
    start_index = 0

    while True:
        params: dict[str, str] = {
            "StartIndex": str(start_index),
            "Limit": str(limit),
        }
        if extra_params:
            params.update(extra_params)
        page = fetch_page(base_url, api_key, params, timeout=timeout)
        all_items.extend(page)
        if len(page) < limit:
            break
        start_index += limit

    return all_items


def _paginate_jellyfin(
    base_url: str,
    api_key: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    *,
    limit: int = 200,
    timeout: int = 30,
) -> Iterator[list[dict[str, Any]]]:
    """Yield pages of items from a Jellyfin endpoint.

    Handles ``StartIndex`` / ``Limit`` pagination automatically.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        endpoint: API endpoint path (e.g. ``"Items"``, ``"Genres"``).
        params: Additional query-string parameters for every request.
        limit: Number of items to request per page.
        timeout: HTTP request timeout in seconds.

    Yields:
        Lists of item dictionaries, one per page.

    """
    start_index = 0
    headers = _auth_headers(api_key)

    while True:
        page_params: dict[str, Any] = {
            "StartIndex": start_index,
            "Limit": limit,
        }
        if params:
            page_params.update(params)

        data = _get_json(
            f"{base_url}/{endpoint}",
            headers=headers,
            params=page_params,
            timeout=timeout,
        )
        page_items = data.get("Items", [])
        yield page_items

        total = data.get("TotalRecordCount", 0)
        start_index += len(page_items)
        if not page_items:
            break
        if total and start_index >= total:
            break


def get_libraries(base_url: str, api_key: str, timeout: int = 30) -> list[str]:
    """Fetch the list of virtual folder (library) names from Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        timeout: HTTP request timeout.

    Returns:
        A list of library names.

    """
    return [
        name
        for folder in _get_json(
            f"{base_url}/Library/VirtualFolders",
            headers=_auth_headers(api_key),
            timeout=timeout,
        )
        if (name := folder.get("Name"))
    ]


def get_users(base_url: str, api_key: str, timeout: int = 30) -> list[dict[str, Any]]:
    """Fetch the list of users from Jellyfin.

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        timeout: HTTP request timeout.

    Returns:
        A list of user dictionaries.

    """
    return _get_json(
        f"{base_url}/Users",
        headers=_auth_headers(api_key),
        timeout=timeout,
    )


def get_user_recent_items(
    base_url: str, api_key: str, user_id: str, limit: int = 20, timeout: int = 30,
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
        "IncludeItemTypes": DEFAULT_ITEM_TYPES,
        "Recursive": RECURSIVE_TRUE,
        "Limit": str(limit),
        "Fields": "ProviderIds",
    }
    return _get_json(
        f"{base_url}/Users/{user_id}/Items",
        headers=_auth_headers(api_key),
        params=params,
        timeout=timeout,
    ).get("Items", [])


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
        _post_or_raise(
            f"{base_url}/Library/VirtualFolders/Paths",
            headers=headers,
            json={"Name": name, "Path": path},
            timeout=timeout,
            error_prefix=f"Failed to add path {path!r} to library {name!r}",
        )

    # Step 3: Trigger a library refresh if requested
    if refresh_library:
        _post_or_raise(
            f"{base_url}/Library/Refresh",
            headers=headers,
            timeout=timeout,
            error_prefix=f"Failed to trigger library refresh for {name!r}",
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
    try:
        response = requests.delete(
            f"{base_url}/Library/VirtualFolders",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        if not response.ok:
            logger.warning("Delete Virtual Folder Failed (%s): %s", response.status_code, response.text)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, f"Failed to delete virtual folder {name!r}")


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
    for folder in _get_json(
        f"{base_url}/Library/VirtualFolders",
        headers=_auth_headers(api_key),
        timeout=timeout,
    ):
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
    try:
        response = requests.post(url, data=image_bytes, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _raise_request_error(exc, f"Failed to upload image for item {item_id!r}")


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
    except RuntimeError as exc:
        logger.info(str(exc))
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
    params: dict[str, str] = {"Name": name, "Ids": ",".join(item_ids)}
    data = _post_json(
        f"{base_url}/Collections",
        headers=_auth_headers(api_key),
        params=params,
        timeout=timeout,
        error_prefix=f"Failed to create collection {name!r}",
    )
    collection_id: str | None = data.get("Id")
    if not collection_id:
        raise RuntimeError(f"Collection created but no Id returned for {name!r}")
    return collection_id


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
    params: dict[str, Any] = {
        "IncludeItemTypes": "BoxSet",
        "Recursive": RECURSIVE_TRUE,
        "SearchTerm": name,
    }
    for page in _paginate_jellyfin(
        base_url, api_key, "Items", params, limit=_COLLECTION_PAGE_LIMIT, timeout=timeout,
    ):
        for item in page:
            if item.get("Name") == name:
                item_id: str | None = item.get("Id")
                if item_id:
                    return item_id
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

    params: dict[str, str] = {"Ids": ",".join(item_ids)}
    _post_or_raise(
        f"{base_url}/Collections/{collection_id}/Items",
        headers=_auth_headers(api_key),
        params=params,
        timeout=timeout,
        error_prefix=f"Failed to add items to collection {collection_id!r}",
    )


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

    params: dict[str, str] = {"Ids": ",".join(item_ids)}
    _delete_or_raise(
        f"{base_url}/Collections/{collection_id}/Items",
        headers=_auth_headers(api_key),
        params=params,
        timeout=timeout,
        error_prefix=f"Failed to remove items from collection {collection_id!r}",
    )


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
    _delete_or_raise(
        f"{base_url}/Items/{collection_id}",
        headers=_auth_headers(api_key),
        timeout=timeout,
        error_prefix=f"Failed to delete collection {collection_id!r}",
    )


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
    except RuntimeError as exc:
        logger.info(str(exc))
    except OSError as exc:
        logger.error("Cannot set collection image: Failed to read %r: %s", image_path, exc)
    else:
        logger.info("Successfully updated cover image for collection %r", collection_id)
