import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runAutoGrouping } from '../src/index.js';
import { MediaItem } from '../src/types.js';
import { createFranchiseRule, createGenreRule, createDecadeRule } from '../src/rules.js';

const mockItems: MediaItem[] = [
  {
    id: '1',
    name: 'Toy Story',
    type: 'Movie',
    productionYear: 1995,
    genres: ['Animation', 'Adventure'],
    collectionName: 'Toy Story Collection',
  },
  {
    id: '2',
    name: 'Toy Story 2',
    type: 'Movie',
    productionYear: 1999,
    genres: ['Animation', 'Comedy'],
    collectionName: 'Toy Story Collection',
  },
  {
    id: '3',
    name: 'A Bug\'s Life',
    type: 'Movie',
    productionYear: 1998,
    genres: ['Animation', 'Family'],
  },
];

describe('runAutoGrouping & Rule Factories', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('should run auto grouping with dryRun=true without calling createCollection', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/Items')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ Items: mockItems }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ Id: 'new-collection-id' }),
      });
    });

    const summary = await runAutoGrouping({
      config: {
        serverUrl: 'http://localhost:8096',
        apiKey: 'test-key',
      },
      dryRun: true,
    });

    expect(summary.totalItemsScanned).toBe(3);
    expect(summary.collectionsCreated).toBe(0);
    expect(summary.groupsFound).toBeGreaterThan(0);
  });

  it('should create collections when dryRun=false', async () => {
    const createCollectionSpy = vi.fn();

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/Items')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ Items: mockItems }),
        });
      }
      if (url.includes('/Collections')) {
        createCollectionSpy();
        return Promise.resolve({
          ok: true,
          json: async () => ({ Id: 'col-123' }),
        });
      }
      return Promise.reject(new Error('Unknown endpoint'));
    });

    const summary = await runAutoGrouping({
      config: {
        serverUrl: 'http://localhost:8096',
        apiKey: 'test-key',
      },
      dryRun: false,
    });

    expect(summary.collectionsCreated).toBe(summary.groupsFound);
    expect(createCollectionSpy).toHaveBeenCalledTimes(summary.groupsFound);
  });

  it('should allow custom minItems using rule factories', () => {
    const franchiseRule = createFranchiseRule({ minItems: 3 });
    const genreRule = createGenreRule({ minItems: 2 });
    const decadeRule = createDecadeRule({ minItems: 2 });

    // Toy Story has 2 items, so minItems=3 returns empty
    expect(franchiseRule.group(mockItems)).toHaveLength(0);

    // Animation genre has 3 items, so minItems=2 returns 1 group
    expect(genreRule.group(mockItems)).toHaveLength(1);

    // 1990s decade has 3 items, so minItems=2 returns 1 group
    expect(decadeRule.group(mockItems)).toHaveLength(1);
  });
});
