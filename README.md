# Jellyfin Auto Groupings

Automatic media grouping library for Jellyfin servers. Group your movies and shows by franchise collections, genre clusters, and decade retrospectives automatically.

## Installation

```bash
npm install jellyfin-auto-groupings
```

## Quick Start

```typescript
import { runAutoGrouping } from 'jellyfin-auto-groupings';

const summary = await runAutoGrouping({
  config: {
    serverUrl: 'http://localhost:8096',
    apiKey: 'your-jellyfin-api-key',
    userId: 'optional-user-id',
  },
  dryRun: true, // Set to false to actually create collections in Jellyfin
});

console.log(`Scanned ${summary.totalItemsScanned} items.`);
console.log(`Found ${summary.groupsFound} potential groups:`);

for (const result of summary.results) {
  console.log(`- ${result.groupName}: ${result.reason}`);
}
```

## Custom & Configurable Rules

You can customize rule thresholds using the rule factories or disable default rules:

```typescript
import {
  runAutoGrouping,
  createFranchiseRule,
  createGenreRule,
  createDecadeRule,
} from 'jellyfin-auto-groupings';

const customRules = [
  createFranchiseRule({ minItems: 2 }),
  createGenreRule({ minItems: 5 }), // Higher threshold for genre clusters
  createDecadeRule({ minItems: 4 }),
];

await runAutoGrouping({
  config: { serverUrl: 'http://localhost:8096', apiKey: 'your-key' },
  rules: customRules,
});
```

## Built-in Rules

1. **Franchise Collections** (`franchise-collections`): Groups movies belonging to the same collection (default minimum 2 items).
2. **Genre Clusters** (`genre-clusters`): Groups items by primary genre (default minimum 3 items).
3. **Decade Retrospectives** (`decade-retrospectives`): Groups items released in the same decade (default minimum 3 items).

## License

MIT
