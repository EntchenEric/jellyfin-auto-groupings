import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runAutoGrouping, createFranchiseRule } from '../src/index.js';
import { MediaItem } from '../src/types.js';

const sampleItems: MediaItem[] = [
  {
    id: '1',
    name: 'Movie A',
    type: 'Movie',
    collectionName: 'Super Collection',
  },
  {
    id: '2',
    name: 'Movie B',
    type: 'Movie',
    collectionName: 'Super Collection',
  },
];

global.fetch = vi.fn();

describe('runAutoGrouping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch items and perform dry-run auto grouping without creating collections', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ Items: sampleItems }),
    });

    const summary = await runAutoGrouping({
      config: {
        serverUrl: 'http://localhost:8096',
        apiKey: 'test-key',
      },
      dryRun: true,
    });

    expect(summary.totalItemsScanned).toBe(2);
    expect(summary.groupsFound).toBe(1);
    expect(summary.collectionsCreated).toBe(0);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('should create collections when dryRun is false', async () => {
    (global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ Items: sampleItems }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ Id: 'col-123' }),
      });

    const summary = await runAutoGrouping({
      config: {
        serverUrl: 'http://localhost:8096',
        apiKey: 'test-key',
      },
      dryRun: false,
    });

    expect(summary.collectionsCreated).toBe(1);
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('should support configurable rules', () => {
    const strictRule = createFranchiseRule({ minItems: 3 });
    const results = strictRule.group(sampleItems);
    expect(results).toHaveLength(0);
  });
});
