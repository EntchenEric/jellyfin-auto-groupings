import { MediaItem, GroupingRule, GroupingResult } from './types.js';

export type { MediaItem, GroupingRule, GroupingResult };

export interface RuleOptions {
  minItems?: number;
}

/**
 * Creates a rule to group media items by collection/franchise.
 */
export function createFranchiseRule(options: RuleOptions = {}): GroupingRule {
  const minItems = options.minItems ?? 2;
  return {
    id: 'franchise-collections',
    name: 'Franchise Collections',
    description: 'Group movies that belong to the same collection/franchise',
    enabled: true,
    group: (items: MediaItem[]): GroupingResult[] => {
      const collectionMap = new Map<string, MediaItem[]>();

      for (const item of items) {
        if (item.collectionName) {
          const list = collectionMap.get(item.collectionName) ?? [];
          list.push(item);
          collectionMap.set(item.collectionName, list);
        }
      }

      const results: GroupingResult[] = [];
      for (const [name, groupItems] of collectionMap.entries()) {
        if (groupItems.length >= minItems) {
          results.push({
            groupName: name,
            items: groupItems,
            reason: `Collection: ${name} (${groupItems.length} items)`,
          });
        }
      }

      return results;
    },
  };
}

/**
 * Creates a rule to group media items by primary genre.
 */
export function createGenreRule(options: RuleOptions = {}): GroupingRule {
  const minItems = options.minItems ?? 3;
  return {
    id: 'genre-clusters',
    name: 'Genre Clusters',
    description: 'Group items sharing primary genres',
    enabled: true,
    group: (items: MediaItem[]): GroupingResult[] => {
      const genreMap = new Map<string, MediaItem[]>();

      for (const item of items) {
        if (item.genres && item.genres.length > 0) {
          const primaryGenre = item.genres[0];
          const list = genreMap.get(primaryGenre) ?? [];
          list.push(item);
          genreMap.set(primaryGenre, list);
        }
      }

      const results: GroupingResult[] = [];
      for (const [genre, groupItems] of genreMap.entries()) {
        if (groupItems.length >= minItems) {
          results.push({
            groupName: `${genre} Spotlight`,
            items: groupItems,
            reason: `Genre: ${genre} (${groupItems.length} items)`,
          });
        }
      }

      return results;
    },
  };
}

/**
 * Creates a rule to group media items by release decade.
 */
export function createDecadeRule(options: RuleOptions = {}): GroupingRule {
  const minItems = options.minItems ?? 3;
  return {
    id: 'decade-retrospectives',
    name: 'Decade Retrospectives',
    description: 'Group items released in the same decade',
    enabled: true,
    group: (items: MediaItem[]): GroupingResult[] => {
      const decadeMap = new Map<string, MediaItem[]>();

      for (const item of items) {
        if (item.productionYear) {
          const decade = `${Math.floor(item.productionYear / 10) * 10}s`;
          const list = decadeMap.get(decade) ?? [];
          list.push(item);
          decadeMap.set(decade, list);
        }
      }

      const results: GroupingResult[] = [];
      for (const [decade, groupItems] of decadeMap.entries()) {
        if (groupItems.length >= minItems) {
          results.push({
            groupName: `${decade} Cinema`,
            items: groupItems,
            reason: `Decade: ${decade} (${groupItems.length} items)`,
          });
        }
      }

      return results;
    },
  };
}

/**
 * Default grouping rules for Jellyfin media items.
 */
export const defaultRules: GroupingRule[] = [
  createFranchiseRule(),
  createGenreRule(),
  createDecadeRule(),
];

/**
 * Apply active rules to group media items.
 */
export function applyGroupingRules(
  items: MediaItem[],
  rules: GroupingRule[] = defaultRules
): GroupingResult[] {
  const activeRules = rules.filter((r) => r.enabled);
  const allResults: GroupingResult[] = [];

  for (const rule of activeRules) {
    const results = rule.group(items);
    allResults.push(...results);
  }

  return allResults;
}
