/**
 * @file Tests for the frontend API module.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('api module', () => {
  beforeEach(() => {
    // Reset fetch mock before each test
    global.fetch = vi.fn();
  });

  it('should export expected API functions', async () => {
    const api = await import('../../static/js/core/api.js');
    expect(typeof api.apiGet).toBe('function');
    expect(typeof api.apiPost).toBe('function');
    expect(typeof api.fetchUsers).toBe('function');
  });

  it('apiGet should make a GET request with correct headers', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'success' }),
    });

    const { apiGet } = await import('../../static/js/core/api.js');
    const result = await apiGet('/api/config');

    expect(global.fetch).toHaveBeenCalledWith('/api/config', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    expect(result).toEqual({ status: 'success' });
  });

  it('apiPost should make a POST request with JSON body', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'success', count: 5 }),
    });

    const { apiPost } = await import('../../static/js/core/api.js');
    const result = await apiPost('/api/grouping/preview', { type: 'genre', value: 'Action' });

    expect(global.fetch).toHaveBeenCalledWith('/api/grouping/preview', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ type: 'genre', value: 'Action' }),
    });
    expect(result).toEqual({ status: 'success', count: 5 });
  });

  it('apiPost should throw on non-OK response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ status: 'error', message: 'Bad request' }),
    });

    const { apiPost } = await import('../../static/js/core/api.js');
    await expect(apiPost('/api/config', {})).rejects.toThrow('Bad request');
  });
});
