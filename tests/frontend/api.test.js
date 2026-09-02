/**
 * @file Tests for the frontend API module.
 * Covers the centralised API client: request building, auth headers,
 * 401 retry flow, error handling (timeout / network / HTTP / unexpected),
 * and the convenience wrappers.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the ui module so error dialogs are observable and don't touch the DOM.
const showErrorDialog = vi.fn();
const showToast = vi.fn();
vi.mock('../../static/js/core/ui.js', () => ({
  showErrorDialog: (...args) => showErrorDialog(...args),
  showToast: (...args) => showToast(...args),
}));

// Keep a reference to the real sessionStorage so we can restore it.
const realSessionStorage = globalThis.sessionStorage;

function mockFetchResponse({ ok = true, status = 200, body = {} } = {}) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  });
}

describe('api module', () => {
  let api;

  beforeEach(async () => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
    // Fresh sessionStorage per test.
    const store = new Map();
    globalThis.sessionStorage = {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
      clear: () => store.clear(),
    };
    api = await import('../../static/js/core/api.js');
  });

  afterEach(() => {
    globalThis.sessionStorage = realSessionStorage;
  });

  it('should export expected API functions', () => {
    expect(typeof api.apiGet).toBe('function');
    expect(typeof api.apiPost).toBe('function');
    expect(typeof api.setAppPassword).toBe('function');
    expect(typeof api.loadConfig).toBe('function');
    expect(typeof api.saveConfig).toBe('function');
    expect(typeof api.testServer).toBe('function');
    expect(typeof api.fetchMetadata).toBe('function');
    expect(typeof api.fetchUsers).toBe('function');
    expect(typeof api.runSync).toBe('function');
    expect(typeof api.previewSync).toBe('function');
    expect(typeof api.previewGroup).toBe('function');
    expect(typeof api.uploadCover).toBe('function');
    expect(typeof api.getCleanupItems).toBe('function');
    expect(typeof api.performCleanup).toBe('function');
    expect(typeof api.autoDetectPaths).toBe('function');
    expect(typeof api.browsePath).toBe('function');
  });

  it('apiGet should make a GET request with correct headers', async () => {
    global.fetch = mockFetchResponse({ body: { status: 'success' } });
    const result = await api.apiGet('/api/config');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/config',
      expect.objectContaining({
        credentials: 'same-origin',
        headers: expect.objectContaining({}),
        signal: expect.any(AbortSignal),
      }),
    );
    expect(result).toEqual({ status: 'success' });
  });

  it('should clear the timeout timer after a successful request', async () => {
    global.fetch = mockFetchResponse({ body: { status: 'success' } });
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout');
    try {
      await api.apiGet('/api/config');
      // The finally block must clear the abort timer on the success path.
      expect(clearTimeoutSpy).toHaveBeenCalled();
    } finally {
      clearTimeoutSpy.mockRestore();
    }
  });

  it('should clear the timeout timer even when the request throws', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout');
    try {
      await expect(api.apiGet('/api/config')).rejects.toBeInstanceOf(TypeError);
      // The finally block must still clear the abort timer on the error path.
      expect(clearTimeoutSpy).toHaveBeenCalled();
    } finally {
      clearTimeoutSpy.mockRestore();
    }
  });

  it('apiPost should make a POST request with JSON body', async () => {
    global.fetch = mockFetchResponse({ body: { status: 'success', count: 5 } });
    const result = await api.apiPost('/api/grouping/preview', { type: 'genre', value: 'Action' });

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/grouping/preview',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        }),
        body: JSON.stringify({ type: 'genre', value: 'Action' }),
        credentials: 'same-origin',
        signal: expect.any(AbortSignal),
      }),
    );
    expect(result).toEqual({ status: 'success', count: 5 });
  });

  it('apiPost should omit body when undefined', async () => {
    global.fetch = mockFetchResponse({ body: { status: 'success' } });
    await api.apiPost('/api/sync');

    const [, options] = global.fetch.mock.calls[0];
    expect(options.body).toBeUndefined();
  });

  it('apiPost should throw on non-OK response', async () => {
    global.fetch = mockFetchResponse({
      ok: false,
      status: 400,
      body: { status: 'error', message: 'Bad request' },
    });

    await expect(api.apiPost('/api/config', {})).rejects.toThrow('Bad request');
    expect(showErrorDialog).toHaveBeenCalledWith('Bad request');
  });

  it('should include Authorization header when app password is set', async () => {
    api.setAppPassword('secret123');
    global.fetch = mockFetchResponse({ body: {} });
    await api.apiGet('/api/config');

    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers.Authorization).toBe(`Basic ${btoa('user:secret123')}`);
  });

  it('setAppPassword should remove the stored password when given falsy value', () => {
    api.setAppPassword('secret123');
    expect(globalThis.sessionStorage.getItem('jfg_app_password')).toBe('secret123');
    api.setAppPassword('');
    expect(globalThis.sessionStorage.getItem('jfg_app_password')).toBeNull();
  });

  it('should retry once with auth header after a 401 when password is provided', async () => {
    // First call returns 401, second returns success.
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ message: 'Unauthorized' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: 'success' }),
      });

    const promptSpy = vi.spyOn(globalThis, 'prompt').mockReturnValue('pw123');
    const result = await api.apiGet('/api/config');

    expect(promptSpy).toHaveBeenCalledWith('Enter app password:');
    expect(globalThis.sessionStorage.getItem('jfg_app_password')).toBe('pw123');
    expect(global.fetch).toHaveBeenCalledTimes(2);
    // Second call should carry the Authorization header.
    const [, secondOptions] = global.fetch.mock.calls[1];
    expect(secondOptions.headers.Authorization).toBe(`Basic ${btoa('user:pw123')}`);
    expect(result).toEqual({ status: 'success' });
    promptSpy.mockRestore();
  });

  it('should throw ApiError(401) when password prompt is cancelled', async () => {
    global.fetch = mockFetchResponse({
      ok: false,
      status: 401,
      body: { message: 'Unauthorized' },
    });
    const promptSpy = vi.spyOn(globalThis, 'prompt').mockReturnValue(null);

    await expect(api.apiGet('/api/config')).rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
      message: 'Authentication required',
    });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    promptSpy.mockRestore();
  });

  it('should not re-prompt for password on a retried request', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ message: 'Unauthorized' }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ message: 'Unauthorized' }),
      });
    const promptSpy = vi.spyOn(globalThis, 'prompt').mockReturnValue('pw123');

    await expect(api.apiGet('/api/config')).rejects.toMatchObject({ status: 401 });
    // Only one prompt: the retried request must not prompt again.
    expect(promptSpy).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledTimes(2);
    promptSpy.mockRestore();
  });

  it('should show timeout dialog and rethrow on AbortError', async () => {
    const abortError = new Error('The operation was aborted');
    abortError.name = 'AbortError';
    global.fetch = vi.fn().mockRejectedValue(abortError);

    await expect(api.apiGet('/api/config')).rejects.toBe(abortError);
    expect(showErrorDialog).toHaveBeenCalledWith(
      'Request timed out — server did not respond in time',
    );
  });

  it('should show network error dialog and rethrow on TypeError', async () => {
    const networkError = new TypeError('Failed to fetch');
    global.fetch = vi.fn().mockRejectedValue(networkError);

    await expect(api.apiGet('/api/config')).rejects.toBe(networkError);
    expect(showErrorDialog).toHaveBeenCalledWith('Network error — check your connection');
  });

  it('should show unexpected error dialog and rethrow on other errors', async () => {
    const unexpected = new Error('boom');
    global.fetch = vi.fn().mockRejectedValue(unexpected);

    await expect(api.apiGet('/api/config')).rejects.toBe(unexpected);
    expect(showErrorDialog).toHaveBeenCalledWith('Unexpected error occurred');
  });

  it('should fall back to generic message when error body has no message', async () => {
    global.fetch = mockFetchResponse({ ok: false, status: 500, body: {} });

    await expect(api.apiGet('/api/config')).rejects.toThrow('Request failed');
    expect(showErrorDialog).toHaveBeenCalledWith('Request failed');
  });

  it('should handle non-JSON error body gracefully', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('invalid json')),
    });

    await expect(api.apiGet('/api/config')).rejects.toThrow('Request failed');
    expect(showErrorDialog).toHaveBeenCalledWith('Request failed');
  });

  it('browsePath should build a query-string URL and GET it', async () => {
    global.fetch = mockFetchResponse({ body: { entries: [] } });
    const result = await api.browsePath('/media/movies');

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toContain('/api/browse');
    expect(url).toContain('path=');
    expect(decodeURIComponent(url)).toContain('path=/media/movies');
    expect(options.method).toBeUndefined(); // GET
    expect(result).toEqual({ entries: [] });
  });

  it('convenience wrappers should hit the right endpoints', async () => {
    global.fetch = mockFetchResponse({ body: { ok: true } });

    await api.loadConfig();
    expect(global.fetch.mock.calls[0][0]).toBe('/api/config');

    await api.saveConfig({ a: 1 });
    expect(global.fetch.mock.calls[1][0]).toBe('/api/config');
    expect(global.fetch.mock.calls[1][1].method).toBe('POST');

    await api.testServer('http://jf', 'key');
    expect(global.fetch.mock.calls[2][0]).toBe('/api/test-server');
    expect(JSON.parse(global.fetch.mock.calls[2][1].body)).toEqual({
      jellyfin_url: 'http://jf',
      api_key: 'key',
    });

    await api.fetchMetadata();
    expect(global.fetch.mock.calls[3][0]).toBe('/api/jellyfin/metadata');

    await api.fetchUsers();
    expect(global.fetch.mock.calls[4][0]).toBe('/api/jellyfin/users');

    await api.runSync();
    expect(global.fetch.mock.calls[5][0]).toBe('/api/sync');

    await api.previewSync();
    expect(global.fetch.mock.calls[6][0]).toBe('/api/sync/preview_all');

    await api.previewGroup('genre', 'Action', 'unwatched', 'movie');
    expect(global.fetch.mock.calls[7][0]).toBe('/api/grouping/preview');
    expect(JSON.parse(global.fetch.mock.calls[7][1].body)).toEqual({
      type: 'genre',
      value: 'Action',
      watch_state: 'unwatched',
      item_type: 'movie',
    });

    await api.uploadCover('My Group', 'data:image/png;base64,abc');
    expect(global.fetch.mock.calls[8][0]).toBe('/api/upload_cover');
    expect(JSON.parse(global.fetch.mock.calls[8][1].body)).toEqual({
      group_name: 'My Group',
      image: 'data:image/png;base64,abc',
    });

    await api.getCleanupItems();
    expect(global.fetch.mock.calls[9][0]).toBe('/api/cleanup');

    await api.performCleanup(['/a', '/b']);
    expect(global.fetch.mock.calls[10][0]).toBe('/api/cleanup');
    expect(JSON.parse(global.fetch.mock.calls[10][1].body)).toEqual({
      folders: ['/a', '/b'],
    });

    await api.autoDetectPaths();
    expect(global.fetch.mock.calls[11][0]).toBe('/api/jellyfin/auto-detect-paths');
  });
});
