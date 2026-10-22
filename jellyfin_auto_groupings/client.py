import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)


class JellyfinAPIError(Exception):
    """Exception raised for Jellyfin API errors."""


class JellyfinClient:
    def __init__(self, server_url: str, api_key: str, user_id: str | None = None):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.headers = {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        }
        self.session.headers.update(self.headers)

    @property
    def base_url(self) -> str:
        """Return the base URL of the Jellyfin server."""
        return self.server_url

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.server_url}{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            logger.exception("Error fetching %s", url)
            raise

    def _post(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.server_url}{endpoint}"
        try:
            resp = self.session.post(url, params=params, json=data, timeout=30)
            resp.raise_for_status()
            if not resp.text.strip():
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text
        except requests.RequestException:
            logger.exception("Error posting to %s", url)
            raise

    def _delete(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.server_url}{endpoint}"
        try:
            resp = self.session.delete(url, params=params, timeout=30)
            resp.raise_for_status()
            if not resp.text.strip():
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text
        except requests.RequestException:
            logger.exception("Error deleting %s", url)
            raise

    def get_users(self) -> list[dict[str, Any]]:
        """Fetch the list of users from the Jellyfin server."""
        return self._get("/Users")

    def get_first_admin_user_id(self) -> str:
        """Return the ID of the first administrator user.

        Raises:
            RuntimeError: If no users are found on the server.
        """
        users = self.get_users()
        if not users:
            msg = "No users found on the Jellyfin server."
            raise RuntimeError(msg)
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u["Id"]
        return users[0]["Id"]

    def get_all_items(
        self, item_types: list[str] | None = None, parent_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch items matching optional item type and parent filters.

        Args:
            item_types: Optional list of Jellyfin item type names to include.
            parent_id: Optional parent folder ID to filter by.
        """
        if not self.user_id:
            self.user_id = self.get_first_admin_user_id()
        params = {
            "Recursive": "true",
            "Fields": "Tags,Genres,ProductionYear,PremiereDate,Overview",
        }
        if item_types:
            params["IncludeItemTypes"] = ",".join(item_types)
        if parent_id:
            params["ParentId"] = parent_id
        data = self._get(f"/Users/{self.user_id}/Items", params=params)
        return data.get("Items", [])

    def get_items(self, library_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch all items, optionally limited to a specific library.

        Args:
            library_id: Optional Jellyfin library folder ID.

        Raises:
            JellyfinAPIError: If the request fails.
        """
        try:
            if not self.user_id:
                self.user_id = self.get_first_admin_user_id()
            params = {
                "Recursive": "true",
                "Fields": "Tags,Genres,ProductionYear,PremiereDate,Overview",
            }
            if library_id:
                params["ParentId"] = library_id
            endpoint = f"/Users/{self.user_id}/Items"
            data = self._get(endpoint, params=params)
            return data.get("Items", [])
        except Exception as e:
            msg = f"API request GET /Items failed: {e}"
            raise JellyfinAPIError(msg) from e

    def get_collections(self) -> list[dict[str, Any]]:
        """Fetch all collections (BoxSets) from the Jellyfin server."""
        return self.get_all_items(item_types=["BoxSet"])

    def get_collection_items(self, collection_id: str) -> list[dict[str, Any]]:
        """Fetch all items belonging to a specific collection."""
        return self.get_all_items(parent_id=collection_id)

    def get_movies(self) -> list[dict[str, Any]]:
        """Fetch all movie items from the Jellyfin server."""
        return self.get_all_items(item_types=["Movie"])

    def create_collection(self, name: str, item_ids: list[str]) -> dict[str, Any]:
        """Create a new collection with the given name and items.

        Args:
            name: The display name for the collection.
            item_ids: List of Jellyfin item IDs to include.

        Returns:
            The collection metadata, or an empty dictionary if no items were provided.
        """
        if not item_ids:
            return {}
        params = {
            "Name": name,
            "Ids": ",".join(item_ids),
        }
        res = self._post("/Collections", params=params)
        if isinstance(res, dict):
            return res
        if res is None:
            # Jellyfin answers with an empty body on success; there is no ID
            # to report, and ``str(None)`` would fabricate a ``"None"`` id.
            return {}
        return {"Id": str(res)}

    def add_to_collection(
        self, collection_id: str, item_ids: list[str]
    ) -> dict[str, Any]:
        """Add items to an existing collection.

        Args:
            collection_id: The ID of the collection.
            item_ids: List of Jellyfin item IDs to add.

        Returns:
            The response metadata, or an empty dictionary if no items were provided.
        """
        if not item_ids:
            return {}
        params = {"Ids": ",".join(item_ids)}
        res = self._post(f"/Collections/{collection_id}/Items", params=params)
        return res if isinstance(res, dict) else {}

    def remove_from_collection(
        self, collection_id: str, item_ids: list[str]
    ) -> dict[str, Any]:
        """Remove items from an existing collection.

        Args:
            collection_id: The ID of the collection.
            item_ids: List of Jellyfin item IDs to remove.

        Returns:
            The response metadata, or an empty dictionary if no items were provided.
        """
        if not item_ids:
            return {}
        params = {"Ids": ",".join(item_ids)}
        res = self._delete(f"/Collections/{collection_id}/Items", params=params)
        return res if isinstance(res, dict) else {}

    def update_item_sort_name(self, item_id: str, sort_name: str) -> None:
        """Update the forced sort name for a specific item.

        Args:
            item_id: The ID of the item to update.
            sort_name: The new sort name to apply.

        Raises:
            requests.RequestException: If the request fails or the server
                rejects it.
        """
        url = f"{self.server_url}/Items/{item_id}"
        try:
            resp = self.session.post(
                url, json={"ForcedSortName": sort_name}, timeout=30
            )
            # Without this the caller cannot tell a rejected update (401/404)
            # from a successful one, and every item would look re-sorted.
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to update sort name for item %s", item_id)
            raise


def group_items_by_pattern(
    items: list[dict[str, Any]], pattern: str, attribute: str = "Name"
) -> dict[str, list[dict[str, Any]]]:
    """Group items based on a regex pattern extracted from an attribute.

    Args:
        items: List of item dictionaries.
        pattern: Regex pattern to match against item attributes.
        attribute: Item attribute to match against (default: "Name").

    Returns:
        A dictionary mapping group names to lists of matching items.
    """
    compiled = re.compile(pattern, re.IGNORECASE)
    groups: dict[str, list[dict[str, Any]]] = {}

    for item in items:
        val = item.get(attribute)
        if isinstance(val, list):
            target_vals = [str(x) for x in val]
        elif val is not None:
            target_vals = [str(val)]
        else:
            continue

        for target in target_vals:
            match = compiled.search(target)
            if match:
                group_name = _matched_group_name(match)
                if group_name:
                    groups.setdefault(group_name, []).append(item)
                break
    return groups


def _matched_group_name(match: re.Match[str]) -> str:
    r"""Resolve the group name for a regex match.

    Prefers the first capture group, falling back to the first group that
    actually participated in the match and finally to the whole match. A
    pattern such as ``(\d{4})|(.*)`` leaves the unused branch ``None``, and
    calling ``.strip()`` on that ``None`` used to abort the whole sync.
    """
    if match.groups():
        for group in match.groups():
            if group is not None:
                return group.strip()
    return match.group(0).strip()


def sync_groupings(
    client: JellyfinClient,
    groups: dict[str, list[dict[str, Any]]],
    dry_run: bool = False,
    min_items: int = 1,
) -> dict[str, list[str]]:
    """Sync calculated groups with Jellyfin collections.

    Args:
        client: The JellyfinClient instance.
        groups: Dictionary mapping group names to lists of items.
        dry_run: If True, log actions without applying them.
        min_items: Minimum number of items required for a group to be processed.

    Returns:
        A dictionary mapping group names to lists of item IDs.
    """
    summary: dict[str, list[str]] = {}
    existing_collections = {
        col["Name"]: col["Id"]
        for col in client.get_all_items(item_types=["BoxSet"])
        if "Name" in col and "Id" in col
    }

    for group_name, items in groups.items():
        if len(items) < min_items:
            continue
        item_ids = [str(item["Id"]) for item in items if "Id" in item]
        if not item_ids:
            continue

        summary[group_name] = item_ids

        if dry_run:
            logger.info(
                f"[DRY-RUN] Would sync {len(item_ids)} items to collection '{group_name}'"
            )
            continue

        if group_name in existing_collections:
            col_id = existing_collections[group_name]
            logger.info(
                f"Adding {len(item_ids)} items to existing collection '{group_name}' ({col_id})"
            )
            client.add_to_collection(col_id, item_ids)
        else:
            logger.info(
                f"Creating collection '{group_name}' with {len(item_ids)} items"
            )
            client.create_collection(group_name, item_ids)

    return summary


def _resolve_release_year(item: dict[str, Any]) -> int | None:
    """Extract a valid integer release year from an item.

    Prefers ``ProductionYear`` and falls back to the first four digits of
    ``PremiereDate``. Handles both int and string forms of the year safely so
    that malformed data (e.g. a string year) never raises.

    Args:
        item: A single item dictionary.

    Returns:
        The release year as an int, or None when it cannot be resolved.
    """
    year = item.get("ProductionYear")
    if isinstance(year, bool):
        # ``bool`` is an ``int`` subclass; True/False are not release years.
        year = None
    if isinstance(year, int) and year > 0:
        return year
    if isinstance(year, str) and year.strip().isdigit():
        parsed = int(year.strip())
        if parsed > 0:
            return parsed
    if item.get("PremiereDate"):
        date_str = str(item.get("PremiereDate"))
        if len(date_str) >= 4 and date_str[:4].isdigit():
            return int(date_str[:4])
    return None


def get_decade_groups(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group items by their release decade.

    Args:
        items: List of item dictionaries.

    Returns:
        A dictionary mapping decade keys (e.g. "1990s Movies") to item lists.
    """
    decades: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        year = _resolve_release_year(item)
        if year is not None and 1800 <= year <= 2100:
            key = f"{(year // 10) * 10}s Movies"
            decades.setdefault(key, []).append(item)
    return decades


def get_year_groups(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group items by their release year.

    Args:
        items: List of item dictionaries.

    Returns:
        A dictionary mapping year keys (e.g. "Best of 1994") to item lists.
    """
    years: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        year = _resolve_release_year(item)
        if year is not None and 1800 <= year <= 2100:
            key = f"Best of {year}"
            years.setdefault(key, []).append(item)
    return years


def get_movies_by_query(
    items: list[dict[str, Any]], query: str, tags: list[str] | None = None
) -> list[dict[str, Any]]:
    """Filter items matching a query string in Name or Overview, optionally requiring tags.

    Args:
        items: List of item dictionaries.
        query: Search string (case-insensitive).
        tags: Optional list of tags that must all be present on matching items.

    Returns:
        A list of items matching the query and tag criteria.
    """
    matching = []
    query_lower = query.lower()
    for item in items:
        name = str(item.get("Name") or "").lower()
        overview = str(item.get("Overview") or "").lower()
        # Jellyfin sends ``null`` for empty tag lists and may include non-string
        # entries; normalise before matching so a single bad item cannot abort
        # the whole scan.
        item_tags = [str(t).lower() for t in (item.get("Tags") or [])]
        if query_lower in name or query_lower in overview:
            if tags:
                if all(t.lower() in item_tags for t in tags):
                    matching.append(item)
            else:
                matching.append(item)
    return matching


def group_movies_by_tag(
    items: list[dict[str, Any]], min_group_size: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Group items by their tags.

    Args:
        items: List of item dictionaries.
        min_group_size: Minimum number of items required for a tag group.

    Returns:
        A dictionary mapping tag names to lists of items with that tag.
    """
    tag_groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for tag in item.get("Tags") or []:
            # Skip empty or non-string tag values instead of raising.
            if isinstance(tag, str) and tag:
                tag_groups.setdefault(tag, []).append(item)
    return {tag: val for tag, val in tag_groups.items() if len(val) >= min_group_size}


def group_movies_by_genre(
    items: list[dict[str, Any]], min_group_size: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Group items by their genres.

    Args:
        items: List of item dictionaries.
        min_group_size: Minimum number of items required for a genre group.

    Returns:
        A dictionary mapping genre names to lists of items with that genre.
    """
    genre_groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for genre in item.get("Genres") or []:
            # Skip empty or non-string genre values instead of raising.
            if isinstance(genre, str) and genre:
                genre_groups.setdefault(genre, []).append(item)
    return {
        genre: val for genre, val in genre_groups.items() if len(val) >= min_group_size
    }


def process_groupings(
    client: Any,
    library_id: Any = None,
    items: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
) -> Any:
    """Process library items and group them automatically.

    Handles two modes:
    1. If the client supports collection methods, items within existing
       collections are sorted by PremiereDate.
    2. If a ``library_id`` is provided, new collections are created by grouping
       item names on their leading prefix.

    The two modes run independently: collection re-sorting is always performed
    when supported, and prefix grouping runs only for ``JellyfinClient`` when
    a ``library_id`` or ``items`` argument is supplied. ``dry_run`` applies to
    both modes: no sort names are written and no collections are created.

    Args:
        client: JellyfinClient instance or compatible object.
        library_id: Optional library ID to fetch items from.
        items: Optional pre-fetched item list.
        dry_run: If True, only return planned changes without applying.

    Returns:
        List of changes or created collections depending on mode.
    """
    changes: list[tuple[str, str, str]] = []

    # Mode 1: Sort items within existing collections by PremiereDate.
    if hasattr(client, "get_collection_items"):
        collections = (
            client.get_collections() if hasattr(client, "get_collections") else []
        )
        for col in collections:
            col_id = col.get("Id")
            if not col_id:
                # Querying items without a collection ID would return an
                # unrelated item set, so skip malformed entries.
                continue
            col_name = col.get("Name") or "Collection"
            col_items = client.get_collection_items(col_id)
            # Jellyfin returns ``null`` for undated items; comparing ``None``
            # with a date string raises TypeError, so coerce to "".
            sorted_items = sorted(
                col_items, key=lambda x: str(x.get("PremiereDate") or "")
            )
            for idx, item in enumerate(sorted_items, start=1):
                expected_sort_name = f"{col_name} {idx:02d}"
                current_sort = item.get("ForcedSortName", "")
                item_id = item.get("Id")
                if not item_id:
                    # An item without an ID cannot be re-sorted; posting to
                    # ``/Items/None`` would fail and abort the remaining items.
                    # The position still counts so later sort names stay stable.
                    continue
                if current_sort != expected_sort_name:
                    changes.append((item_id, item.get("Name"), expected_sort_name))
                    if not dry_run and hasattr(client, "update_item_sort_name"):
                        client.update_item_sort_name(item_id, expected_sort_name)

    # If a specific library was requested, fetch its items for prefix grouping.
    if items is None and isinstance(library_id, str) and library_id:
        items = client.get_items(library_id)

    # Mode 2: Create new collections grouped by name prefix.
    if isinstance(client, JellyfinClient):
        if not items:
            return changes
        groups: dict[str, list[str]] = {}
        for item in items:
            name = item.get("Name", "")
            prefix = name.split()[0] if name else "Unknown"
            item_id = item.get("Id")
            if not item_id:
                # An item without an ID cannot be added to a collection;
                # passing "" would make Jellyfin reject the whole request.
                continue
            groups.setdefault(prefix, []).append(str(item_id))
        if dry_run:
            # A dry run must never mutate the server.
            return changes
        created = []
        for group_name, item_ids in groups.items():
            if len(item_ids) > 1:
                col = client.create_collection(group_name, item_ids)
                created.append(col)
        return [*changes, *created]
    return changes


def create_groupings(
    client_or_items: Any,
    library_id: str | None = None,
    items: list[dict[str, Any]] | None = None,
    min_group_size: int = 2,
) -> Any:
    """Create collections or grouping mapping for items matching criteria.

    Can be called in two ways:

    1. ``create_groupings(items_list)`` returns a ``dict[str, list[dict]]`` of
       preset groups: the "Marvel Cinematic Universe", "Star Wars Collection"
       and "Sci-Fi Classics" query matches, plus one entry per release decade.
       It builds no collections and does not read ``library_id``.
    2. ``create_groupings(client, library_id, items, min_group_size)`` groups
       items by the first word of ``Name`` and creates a collection per group
       that reaches ``min_group_size``. Items without a usable ``Id`` are
       skipped.

    Args:
        client_or_items: Either a JellyfinClient instance or a list of item dictionaries.
        library_id: Optional library ID (used when first arg is a client).
        items: Optional list of item dictionaries (used when first arg is a client).
        min_group_size: Minimum number of items required to create a collection.

    Returns:
        For case 1: A dictionary mapping preset group names to lists of items.
        For case 2: A list of created collection metadata.
    """
    if isinstance(client_or_items, list) and library_id is None:
        sample_items = client_or_items
        res: dict[str, list[dict[str, Any]]] = {}
        mcu = get_movies_by_query(sample_items, "MCU")
        if mcu:
            res["Marvel Cinematic Universe"] = mcu
        sw = get_movies_by_query(sample_items, "Star Wars")
        if sw:
            res["Star Wars Collection"] = sw
        scifi = get_movies_by_query(sample_items, "Sci-Fi", tags=["sci-fi", "classic"])
        if scifi:
            res["Sci-Fi Classics"] = scifi
        decades = get_decade_groups(sample_items)
        res.update(decades)
        return res

    client = client_or_items
    items = items or []
    if not items:
        return []
    groups: dict[str, list[str]] = {}
    for item in items:
        name = item.get("Name", "")
        prefix = name.split()[0] if name else "Unknown"
        item_id = item.get("Id")
        if not item_id:
            # An item without an ID cannot be added to a collection;
            # passing "" would make Jellyfin reject the whole request.
            continue
        groups.setdefault(prefix, []).append(str(item_id))

    created = []
    for group_name, item_ids in groups.items():
        if len(item_ids) >= min_group_size:
            col = client.create_collection(group_name, item_ids)
            created.append(col)
    return created
