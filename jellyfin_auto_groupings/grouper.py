from typing import Any


class CollectionGrouper:
    def __init__(self, pattern: str = r"^(.*)"):
        self.pattern = pattern

    def group(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        from jellyfin_auto_groupings.client import group_items_by_pattern

        return group_items_by_pattern(items, self.pattern)
