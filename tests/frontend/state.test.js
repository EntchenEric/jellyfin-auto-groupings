/**
 * @file Tests for the frontend state module.
 */
import { describe, it, expect, beforeEach } from 'vitest';

// We test the state module by importing it and checking its API surface.
// Since the module uses DOM globals, we need jsdom environment.

describe('state module', () => {
  it('should export metadataTypes as an array', async () => {
    const { metadataTypes } = await import('../../static/js/core/state.js');
    expect(Array.isArray(metadataTypes)).toBe(true);
    expect(metadataTypes.length).toBeGreaterThan(0);
    expect(metadataTypes).toContain('genre');
    expect(metadataTypes).toContain('actor');
    expect(metadataTypes).toContain('studio');
    expect(metadataTypes).toContain('tag');
    expect(metadataTypes).toContain('year');
  });

  it('should export state as an object', async () => {
    const { state } = await import('../../static/js/core/state.js');
    expect(state).toBeDefined();
    expect(typeof state).toBe('object');
  });
});
