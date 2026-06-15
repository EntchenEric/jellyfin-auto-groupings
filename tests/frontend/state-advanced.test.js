/**
 * @file Additional tests for the frontend state module.
 */
import { describe, it, expect } from 'vitest';

describe('state module — constants', () => {
  it('should have sourceOptions with jellyfin and external categories', async () => {
    const { sourceOptions } = await import('../../static/js/core/state.js');
    expect(sourceOptions.jellyfin).toBeInstanceOf(Array);
    expect(sourceOptions.external).toBeInstanceOf(Array);
    expect(sourceOptions.jellyfin.length).toBeGreaterThan(0);
    expect(sourceOptions.external.length).toBeGreaterThan(0);
  });

  it('should have sortLabels for all known sort types', async () => {
    const { sortLabels } = await import('../../static/js/core/state.js');
    expect(sortLabels['CommunityRating']).toBe('Community Rating');
    expect(sortLabels['ProductionYear']).toBe('Production Year');
    expect(sortLabels['SortName']).toBe('Name (A→Z)');
    expect(sortLabels['Random']).toBe('Random');
  });

  it('should have all external list sort order labels', async () => {
    const { sortLabels } = await import('../../static/js/core/state.js');
    expect(sortLabels['imdb_list_order']).toBe('IMDb List Order');
    expect(sortLabels['trakt_list_order']).toBe('Trakt List Order');
    expect(sortLabels['tmdb_list_order']).toBe('TMDb List Order');
    expect(sortLabels['anilist_list_order']).toBe('AniList List Order');
    expect(sortLabels['mal_list_order']).toBe('MAL List Order');
    expect(sortLabels['letterboxd_list_order']).toBe('Letterboxd List Order');
    expect(sortLabels['recommendations_list_order']).toBe('Recommendations Order');
  });
});

describe('state module — functions', () => {
  it('setState should update the state object', async () => {
    const { state, setState } = await import('../../static/js/core/state.js');
    setState('isServerValidated', true);
    expect(state.isServerValidated).toBe(true);
  });

  it('setState should set a new key on the state', async () => {
    const { state, setState } = await import('../../static/js/core/state.js');
    setState('customKey', 'customValue');
    expect(state.customKey).toBe('customValue');
  });
});

describe('sourceOptions — external sources', () => {
  it('should list all external source types', async () => {
    const { sourceOptions } = await import('../../static/js/core/state.js');
    const values = sourceOptions.external.map(s => s.value);
    expect(values).toContain('imdb_list');
    expect(values).toContain('trakt_list');
    expect(values).toContain('tmdb_list');
    expect(values).toContain('anilist_list');
    expect(values).toContain('mal_list');
    expect(values).toContain('letterboxd_list');
  });

  it('should mark sources requiring API keys', async () => {
    const { sourceOptions } = await import('../../static/js/core/state.js');
    const trakt = sourceOptions.external.find(s => s.value === 'trakt_list');
    expect(trakt.requiredKey).toBe('trakt_client_id');

    const mal = sourceOptions.external.find(s => s.value === 'mal_list');
    expect(mal.requiredKey).toBe('mal_client_id');

    const imdb = sourceOptions.external.find(s => s.value === 'imdb_list');
    expect(imdb.requiredKey).toBeUndefined();
  });
});

describe('sourceOptions — jellyfin sources', () => {
  it('should list all jellyfin source types', async () => {
    const { sourceOptions } = await import('../../static/js/core/state.js');
    const values = sourceOptions.jellyfin.map(s => s.value);
    expect(values).toContain('general');
    expect(values).toContain('genre');
    expect(values).toContain('actor');
    expect(values).toContain('studio');
    expect(values).toContain('tag');
    expect(values).toContain('complex');
    expect(values).toContain('recommendations');
  });

  it('should mark recommendations as requiring tmdb_api_key', async () => {
    const { sourceOptions } = await import('../../static/js/core/state.js');
    const rec = sourceOptions.jellyfin.find(s => s.value === 'recommendations');
    expect(rec.requiredKey).toBe('tmdb_api_key');
  });
});

describe('metadataTypes', () => {
  it('should contain the expected types', async () => {
    const { metadataTypes } = await import('../../static/js/core/state.js');
    expect(metadataTypes).toContain('genre');
    expect(metadataTypes).toContain('actor');
    expect(metadataTypes).toContain('studio');
    expect(metadataTypes).toContain('tag');
    expect(metadataTypes).toContain('complex');
    expect(metadataTypes).not.toContain('general');
  });
});

describe('initial state', () => {
  it('should have default values in the state object', async () => {
    const { state } = await import('../../static/js/core/state.js');
    expect(state.currentConfig).toEqual({ groups: [], scheduler: {} });
    expect(state.pendingImportData).toBeNull();
    expect(state.editingIndex).toBe(-1);
    // isServerValidated may have been mutated by other tests; check groups default
    expect(state.cachedMetadata).toBeDefined();
  });
});