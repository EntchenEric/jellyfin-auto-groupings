import { JellyfinApiClient, JellyfinConfig } from './jellyfin-api.js';
import {
  defaultRules,
  applyGroupingRules,
  createFranchiseRule,
  createGenreRule,
  createDecadeRule,
  GroupingRule,
  GroupingResult,
  RuleOptions,
} from './rules.js';
import { MediaItem } from './types.js';

export {
  JellyfinApiClient,
  defaultRules,
  applyGroupingRules,
  createFranchiseRule,
  createGenreRule,
  createDecadeRule,
};
export type {
  JellyfinConfig,
  GroupingRule,
  GroupingResult,
  MediaItem,
  RuleOptions,
};

export interface AutoGroupOptions {
  config: JellyfinConfig;
  rules?: GroupingRule[];
  dryRun?: boolean;
}

export interface AutoGroupSummary {
  totalItemsScanned: number;
  groupsFound: number;
  collectionsCreated: number;
  results: GroupingResult[];
}

/**
 * Main entry point for running automatic media grouping.
 */
export async function runAutoGrouping(options: AutoGroupOptions): Promise<AutoGroupSummary> {
  const client = new JellyfinApiClient(options.config);
  const items = await client.getItems();

  const rules = options.rules ?? defaultRules;
  const groupingResults = applyGroupingRules(items, rules);

  let collectionsCreated = 0;

  if (!options.dryRun) {
    for (const group of groupingResults) {
      const itemIds = group.items.map((i) => i.id);
      await client.createCollection(group.groupName, itemIds);
      collectionsCreated++;
    }
  }

  return {
    totalItemsScanned: items.length,
    groupsFound: groupingResults.length,
    collectionsCreated,
    results: groupingResults,
  };
}
