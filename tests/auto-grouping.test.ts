import { describe, it, expect, vi } from 'vitest';
import { runAutoGrouping, createFranchiseRule, JellyfinApiClient } from '../src/index.js';
import { MediaItem } from '../src/types.js';

const mockItems: MediaItem[] = [
  { id: '101', name: 'Alien', type: 'Movie', collectionName: 'Alien Collection' },
  { id: '102', name: 'Aliens', type: 'Movie', collectionName: 'Alien Collection' },
];

vi.mock('../src/jellyfin-api.js', () => {
  return {
    JellyfinApiClient: vi.fn().mockImplementation(() => ({
      getItems: vi.fn().mockResolvedValue([
        { id: '101', name: 'Alien', type: 'Movie', collectionName: 'Alien Collection' },
        { id: '102', name: 'Aliens', type: 'Movie', collectionName: 'Alien Collection' },
      ]),
      createCollection: vi.fn().mockResolvedValue('collection-id-123'),
    })),
  };
});

describe('runAutoGrouping', () => {
  it('should run in dryRun mode without creating collections', async () => {
    const summary = await runAutoGrouping({
      config: { serverUrl: 'http://localhost:8096', apiKey: 'test' },
      dryRun: true,
    });

    expect(summary.totalItemsScanned).toBe(2);
    expect(summary.groupsFound).toBeGreaterThan(0);
    expect(summary.collectionsCreated).toBe(0);
  });

  it('should create collections when dryRun is false', async () => {
    const summary = await runAutoGrouping({
      config: { serverUrl: 'http://localhost:8096', apiKey: 'test' },
      dryRun: false,
    });

    expect(summary.collectionsCreated).toBe(summary.groupsFound);
  });

  it('should support rule factory functions with custom options', () => {
    const customFranchiseRule = createFranchiseRule({ minItems: 1 });
    const results = customFranchiseRule.group([
      { id: '1', name: 'Solo Movie', type: 'Movie', collectionName: 'Solo Collection' },
    ]);
    expect(results).toHaveLength(1);
    expect(results[0].groupName).toBe('Solo Collection');
  });
});
