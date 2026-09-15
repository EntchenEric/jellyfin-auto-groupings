from typing import Any, Dict, List


class CollectionGrouper:
    def __init__(self, pattern: str = r"^(.*)"):
        self.pattern = pattern

    def group(self, items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        from jellyfin_auto_groupings.client import group_items_by_pattern
        return group_items_by_pattern(items, self.pattern)
