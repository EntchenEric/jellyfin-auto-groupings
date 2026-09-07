export interface MediaItem {
  id: string;
  name: string;
  type: 'Movie' | 'Series';
  productionYear?: number;
  genres?: string[];
  collectionName?: string;
  director?: string;
  artists?: string[];
}

export interface GroupingResult {
  groupName: string;
  items: MediaItem[];
  reason: string;
}

export interface GroupingRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  group: (items: MediaItem[]) => GroupingResult[];
}
