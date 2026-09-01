/**
 * @file Tests for the path-picker feature module (path-picker.js).
 *
 * Covers the folder path picker and auto-detect logic: opening the picker,
 * browsing directories (including the root-path join edge case), confirming
 * and closing, backdrop dismissal, and auto-detection of host paths.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Set up the DOM elements that path-picker.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="path-picker-modal" class="modal" style="display:none">
      <div id="picker-title"></div>
      <div id="picker-body"></div>
      <div id="picker-breadcrumb"></div>
      <div id="picker-footer-path"></div>
    </div>
    <div id="status-msg"></div>
    <div id="error-dialog-modal" class="modal">
      <div id="error-dialog-message"></div>
    </div>
    <input id="target_path" value="" />
    <input id="media_path_in_jellyfin" value="" />
    <input id="media_path_on_host" value="" />
    <input id="target_path_in_jellyfin" value="" />
    <button id="auto-detect-btn"></button>
  `;
}

/** Shared mocks for the core modules path-picker.js depends on. */
function mockCoreModules() {
  vi.doMock('../../static/js/core/api.js', () => ({
    autoDetectPaths: vi.fn(),
  }));
  vi.doMock('../../static/js/core/ui.js', () => ({
    showModal: vi.fn(),
    hideModal: vi.fn(),
    showToast: vi.fn(),
    showErrorDialog: vi.fn(),
    getEl: (id) => document.getElementById(id),
  }));
}

describe('path-picker module', () => {
  beforeEach(() => {
    setupDOM();
    vi.resetModules();
    mockCoreModules();
    // Default: a successful browse response
    global.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({
        status: 'success',
        current: '/media',
        parent: '/',
        dirs: ['Movies', 'Shows'],
      }),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it('should export the expected public functions', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    expect(typeof mod.openPathPicker).toBe('function');
    expect(typeof mod.browseDir).toBe('function');
    expect(typeof mod.confirmPicker).toBe('function');
    expect(typeof mod.closePicker).toBe('function');
    expect(typeof mod.pickerOutsideClick).toBe('function');
    expect(typeof mod.autoDetectPaths).toBe('function');
    expect(typeof mod.autoDetectIfEmpty).toBe('function');
    expect(typeof mod.initPathPicker).toBe('function');
  });

  it('openPathPicker should set the title for target_path and show the modal', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.openPathPicker('target_path');
    expect(document.getElementById('picker-title').textContent).toBe('Select Target Path');
    expect(ui.showModal).toHaveBeenCalledWith('path-picker-modal');
  });

  it('openPathPicker should set the title for media_path_in_jellyfin', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.openPathPicker('media_path_in_jellyfin');
    expect(document.getElementById('picker-title').textContent)
      .toBe('Select Media Path (Jellyfin side)');
  });

  it('openPathPicker should use a generic title for other fields', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.openPathPicker('media_path_on_host');
    expect(document.getElementById('picker-title').textContent)
      .toBe('Select Media Path (this machine)');
  });

  it('browseDir should render directories and a parent link', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.browseDir('/media');
    const body = document.getElementById('picker-body');
    const items = body.querySelectorAll('.picker-item');
    // parent "go up" button + two directories
    expect(items.length).toBe(3);
    expect(body.querySelector('.picker-up')).not.toBeNull();
    expect(document.getElementById('picker-breadcrumb').textContent).toBe('/media');
    expect(document.getElementById('picker-footer-path').textContent).toBe('/media');
  });

  it('browseDir should join child paths correctly when browsing the root directory', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ status: 'success', current: '/', parent: null, dirs: ['Movies'] }),
    });
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.browseDir('/');
    const body = document.getElementById('picker-body');
    const btn = body.querySelector('.picker-item');
    // Root join must not produce a double slash: '/' + 'Movies' -> '/Movies'
    expect(btn.title).toBe('/Movies');
  });

  it('browseDir should show an empty message when there are no subdirectories', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ status: 'success', current: '/empty', parent: null, dirs: [] }),
    });
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.browseDir('/empty');
    const body = document.getElementById('picker-body');
    expect(body.querySelector('.picker-empty').textContent).toBe('No subdirectories here.');
  });

  it('browseDir should show an error message when the API returns failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ status: 'error', message: 'Permission denied' }),
    });
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.browseDir('/restricted');
    const body = document.getElementById('picker-body');
    expect(body.querySelector('.picker-empty').textContent).toBe('Permission denied');
  });

  it('browseDir should show a loading message while fetching', async () => {
    let resolveFetch;
    global.fetch = vi.fn().mockReturnValue(new Promise((res) => { resolveFetch = res; }));
    const mod = await import('../../static/js/features/path-picker.js');
    const promise = mod.browseDir('/media');
    // Loading placeholder should be present before the fetch resolves
    expect(document.getElementById('picker-body').textContent).toContain('Loading...');
    resolveFetch({ json: () => Promise.resolve({ status: 'success', current: '/media', parent: null, dirs: [] }) });
    await promise;
  });

  it('browseDir should handle a network error gracefully', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('offline'));
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.browseDir('/media');
    const body = document.getElementById('picker-body');
    expect(body.querySelector('.picker-empty').textContent).toContain('Could not load directory');
  });

  it('confirmPicker should write the current path into the target input and close', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.openPathPicker('target_path');
    await mod.browseDir('/media');
    mod.confirmPicker();
    expect(document.getElementById('target_path').value).toBe('/media');
    expect(ui.hideModal).toHaveBeenCalledWith('path-picker-modal');
  });

  it('closePicker should hide the modal', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    mod.closePicker();
    expect(ui.hideModal).toHaveBeenCalledWith('path-picker-modal');
  });

  it('pickerOutsideClick should close when clicking the modal backdrop', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('path-picker-modal');
    mod.pickerOutsideClick({ target: modal });
    expect(ui.hideModal).toHaveBeenCalledWith('path-picker-modal');
  });

  it('pickerOutsideClick should not close when clicking inside the modal', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    const inner = document.getElementById('picker-body');
    mod.pickerOutsideClick({ target: inner });
    expect(ui.hideModal).not.toHaveBeenCalled();
  });

  it('autoDetectPaths should fill all path fields on success', async () => {
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockResolvedValue({
      status: 'success',
      detected: {
        media_path_in_jellyfin: '/jf/media',
        media_path_on_host: '/host/media',
        target_path: '/host/target',
        target_path_in_jellyfin: '/jf/target',
      },
    });
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.autoDetectPaths();
    expect(document.getElementById('media_path_in_jellyfin').value).toBe('/jf/media');
    expect(document.getElementById('media_path_on_host').value).toBe('/host/media');
    expect(document.getElementById('target_path').value).toBe('/host/target');
    expect(document.getElementById('target_path_in_jellyfin').value).toBe('/jf/target');
    expect(ui.showToast).toHaveBeenCalled();
  });

  it('autoDetectPaths should warn when detection succeeds but no host path is found', async () => {
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockResolvedValue({ status: 'success', detected: {} });
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.autoDetectPaths();
    expect(ui.showErrorDialog).toHaveBeenCalledWith(
      'Auto-detection finished but could not find matching host paths.'
    );
    expect(ui.showToast).not.toHaveBeenCalled();
  });

  it('autoDetectPaths should show an error dialog when detection fails', async () => {
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockResolvedValue({ status: 'error', message: 'boom' });
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.autoDetectPaths();
    expect(ui.showErrorDialog).toHaveBeenCalledWith('boom');
  });

  it('autoDetectPaths should show an error dialog when the API is unreachable', async () => {
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockRejectedValue(new Error('network'));
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.autoDetectPaths();
    expect(ui.showErrorDialog).toHaveBeenCalledWith('Auto-detection failed - API unreachable');
  });

  it('autoDetectIfEmpty should only fill empty fields', async () => {
    document.getElementById('target_path').value = '/existing';
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockResolvedValue({
      status: 'success',
      detected: {
        target_path: '/new-target',
        media_path_in_jellyfin: '/jf/media',
        media_path_on_host: '/host/media',
        target_path_in_jellyfin: '/jf/target',
      },
    });
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.autoDetectIfEmpty();
    // target_path was already set, so it must not be overwritten
    expect(document.getElementById('target_path').value).toBe('/existing');
    expect(document.getElementById('media_path_in_jellyfin').value).toBe('/jf/media');
    expect(document.getElementById('media_path_on_host').value).toBe('/host/media');
    expect(document.getElementById('target_path_in_jellyfin').value).toBe('/jf/target');
  });

  it('autoDetectIfEmpty should fill empty fields from the detected result', async () => {
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockResolvedValue({
      status: 'success',
      detected: {
        target_path: '/new-target',
        media_path_in_jellyfin: '/jf/media',
        media_path_on_host: '/host/media',
        target_path_in_jellyfin: '/jf/target',
      },
    });
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.autoDetectIfEmpty();
    // All fields were empty, so every one should be filled from the result.
    expect(document.getElementById('target_path').value).toBe('/new-target');
    expect(document.getElementById('media_path_in_jellyfin').value).toBe('/jf/media');
    expect(document.getElementById('media_path_on_host').value).toBe('/host/media');
    expect(document.getElementById('target_path_in_jellyfin').value).toBe('/jf/target');
    expect(ui.showToast).toHaveBeenCalledWith('Paths auto-filled - review and save.', 'success');
  });

  it('autoDetectIfEmpty should do nothing when detection returns a non-success status', async () => {
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockResolvedValue({ status: 'error', message: 'boom' });
    const mod = await import('../../static/js/features/path-picker.js');
    const ui = await import('../../static/js/core/ui.js');
    await mod.autoDetectIfEmpty();
    expect(document.getElementById('target_path').value).toBe('');
    expect(ui.showToast).not.toHaveBeenCalled();
  });

  it('autoDetectIfEmpty should skip the API call when all fields are filled', async () => {
    document.getElementById('target_path').value = '/a';
    document.getElementById('media_path_in_jellyfin').value = '/b';
    document.getElementById('media_path_on_host').value = '/c';
    const api = await import('../../static/js/core/api.js');
    const mod = await import('../../static/js/features/path-picker.js');
    await mod.autoDetectIfEmpty();
    expect(api.autoDetectPaths).not.toHaveBeenCalled();
  });

  it('autoDetectIfEmpty should silently ignore API failures', async () => {
    const api = await import('../../static/js/core/api.js');
    api.autoDetectPaths.mockRejectedValue(new Error('offline'));
    const mod = await import('../../static/js/features/path-picker.js');
    await expect(mod.autoDetectIfEmpty()).resolves.toBeUndefined();
  });

  it('initPathPicker should not throw', async () => {
    const mod = await import('../../static/js/features/path-picker.js');
    expect(() => mod.initPathPicker()).not.toThrow();
  });
});
