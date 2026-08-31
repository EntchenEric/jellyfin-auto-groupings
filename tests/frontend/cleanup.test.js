/**
 * @file Tests for the cleanup feature module (cleanup.js).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Set up the DOM elements that cleanup.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="status-msg"></div>
    <div id="error-dialog-modal" class="modal">
      <div id="error-dialog-message"></div>
    </div>
    <div id="cleanup-modal" class="modal" style="display:none"></div>
    <div id="cleanup-loading" style="display:none"></div>
    <div id="cleanup-content" style="display:none"></div>
    <div id="cleanup-error" style="display:none"></div>
    <div id="cleanup-list"></div>
    <div id="cleanup-count"></div>
    <button id="confirm-cleanup-btn"></button>
  `;
}

describe('cleanup feature module', () => {
  beforeEach(() => {
    setupDOM();
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should export openCleanupModal, updateCleanupCount, execCleanup and initCleanup', async () => {
    const mod = await import('../../static/js/features/cleanup.js');
    expect(typeof mod.openCleanupModal).toBe('function');
    expect(typeof mod.updateCleanupCount).toBe('function');
    expect(typeof mod.execCleanup).toBe('function');
    expect(typeof mod.initCleanup).toBe('function');
  });

  it('openCleanupModal should render items on success', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({
        status: 'success',
        items: [
          { name: 'Action', is_configured: true },
          { name: 'Orphan', is_configured: false },
        ],
      }),
    });

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.openCleanupModal();

    const list = document.getElementById('cleanup-list');
    expect(list.querySelectorAll('.cleanup-item').length).toBe(2);
    expect(list.querySelector('.cleanup-badge-configured').textContent).toBe('Configured');
    expect(list.querySelector('.cleanup-badge-unconfigured').textContent).toBe('Unconfigured');
    expect(document.getElementById('cleanup-loading').style.display).toBe('none');
    expect(document.getElementById('cleanup-content').style.display).toBe('flex');
  });

  it('openCleanupModal should show empty state when no items', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ status: 'success', items: [] }),
    });

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.openCleanupModal();

    const list = document.getElementById('cleanup-list');
    expect(list.querySelector('.cleanup-empty').textContent).toBe('No folders found in Target Directory.');
  });

  it('openCleanupModal should show error when API returns failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ status: 'error', message: 'Failed to load' }),
    });

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.openCleanupModal();

    expect(document.getElementById('cleanup-error').textContent).toBe('Failed to load');
    expect(document.getElementById('cleanup-error').style.display).toBe('block');
  });

  it('openCleanupModal should show network error on fetch failure', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network down'));

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.openCleanupModal();

    expect(document.getElementById('cleanup-error').textContent).toBe('Network error fetching folders');
    expect(document.getElementById('cleanup-error').style.display).toBe('block');
  });

  it('updateCleanupCount should update count and button state', async () => {
    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" checked>
      <input type="checkbox" class="cleanup-item-checkbox">
    `;

    const mod = await import('../../static/js/features/cleanup.js');
    mod.updateCleanupCount();

    expect(document.getElementById('cleanup-count').textContent).toBe('(1)');
    expect(document.getElementById('confirm-cleanup-btn').disabled).toBe(false);
    expect(document.getElementById('confirm-cleanup-btn').style.opacity).toBe('1');
  });

  it('updateCleanupCount should disable button when nothing checked', async () => {
    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox">
    `;

    const mod = await import('../../static/js/features/cleanup.js');
    mod.updateCleanupCount();

    expect(document.getElementById('cleanup-count').textContent).toBe('');
    expect(document.getElementById('confirm-cleanup-btn').disabled).toBe(true);
    expect(document.getElementById('confirm-cleanup-btn').style.opacity).toBe('0.5');
  });

  it('execCleanup should POST selected folders and show toast on success', async () => {
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
      <input type="checkbox" class="cleanup-item-checkbox" value="Drama">
    `;

    global.fetch = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ status: 'success', deleted: 1 }),
    });

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    // Verify the POST body only contains checked folders
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/cleanup');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body).folders).toEqual(['Action']);
    expect(showToast).toHaveBeenCalled();
    expect(showErrorDialog).not.toHaveBeenCalled();
  });

  it('execCleanup should show error dialog on API failure', async () => {
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
    `;

    global.fetch = vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ status: 'error', message: 'Permission denied' }),
    });

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    expect(showErrorDialog).toHaveBeenCalledWith('Error deleting folders: Permission denied');
  });

  it('execCleanup should show error dialog on network failure', async () => {
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
    `;

    global.fetch = vi.fn().mockRejectedValue(new Error('Network down'));

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    expect(showErrorDialog).toHaveBeenCalledWith('Network error while deleting folders.');
  });

  it('execCleanup should do nothing when no folders selected', async () => {
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action">
    `;

    global.fetch = vi.fn();

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    expect(global.fetch).not.toHaveBeenCalled();
  });
});
