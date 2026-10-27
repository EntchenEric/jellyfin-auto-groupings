from typing import Any


class CollectionGrouper:
    """Group items into collections by a regex pattern applied to their names.

    Args:
        pattern: Regular expression with one capture group. The captured text
            becomes the collection name; items that do not match are dropped.
    """

    def __init__(self, pattern: str = r"^(.*)"):
        self.pattern = pattern

    def group(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Return ``{collection name: [items]}`` for every matching item.

        Items without a usable ``Name`` and items whose name does not match
        ``pattern`` are skipped rather than raising.
        """
        from jellyfin_auto_groupings.client import group_items_by_pattern

        return group_items_by_pattern(items, self.pattern)
