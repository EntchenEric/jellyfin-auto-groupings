/**
 * @file Tests for the cleanup feature module (cleanup.js).
 *
 * cleanup.js delegates HTTP to the centralized api.js helpers
 * (getCleanupItems / performCleanup), so these tests mock that module
 * directly and focus on cleanup.js's own rendering / UX logic.
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
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn().mockResolvedValue({
        status: 'success',
        items: [
          { name: 'Action', is_configured: true },
          { name: 'Orphan', is_configured: false },
        ],
      }),
      performCleanup: vi.fn(),
    }));

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
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn().mockResolvedValue({ status: 'success', items: [] }),
      performCleanup: vi.fn(),
    }));

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.openCleanupModal();

    const list = document.getElementById('cleanup-list');
    expect(list.querySelector('.cleanup-empty').textContent).toBe('No folders found in Target Directory.');
  });

  it('openCleanupModal should show error when API returns failure', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn().mockResolvedValue({ status: 'error', message: 'Failed to load' }),
      performCleanup: vi.fn(),
    }));

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.openCleanupModal();

    expect(document.getElementById('cleanup-error').textContent).toBe('Failed to load');
    expect(document.getElementById('cleanup-error').style.display).toBe('block');
  });

  it('openCleanupModal should use fallback message when API error has no message', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn().mockResolvedValue({ status: 'error' }),
      performCleanup: vi.fn(),
    }));

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.openCleanupModal();

    expect(document.getElementById('cleanup-error').textContent).toBe('Failed to load folders');
    expect(document.getElementById('cleanup-error').style.display).toBe('block');
  });

  it('openCleanupModal should show network error when the API helper rejects', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn().mockRejectedValue(new Error('Network down')),
      performCleanup: vi.fn(),
    }));

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
    const performCleanup = vi.fn().mockResolvedValue({ status: 'success', deleted: 1 });
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn(),
      performCleanup,
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
      <input type="checkbox" class="cleanup-item-checkbox" value="Drama">
    `;

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    // Verify only checked folders are sent to the centralized helper
    expect(performCleanup).toHaveBeenCalledWith(['Action']);
    expect(showToast).toHaveBeenCalled();
    expect(showErrorDialog).not.toHaveBeenCalled();
  });

  it('execCleanup should show warning toast with errors on partial success', async () => {
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn(),
      performCleanup: vi.fn().mockResolvedValue({
        status: 'partial_success',
        deleted: 1,
        errors: ['Drama: permission denied'],
      }),
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
    `;

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    expect(showToast).toHaveBeenCalledWith(
      'Successfully deleted 1 folder(s). Errors: Drama: permission denied',
      'warning'
    );
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
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn(),
      performCleanup: vi.fn().mockResolvedValue({ status: 'error', message: 'Permission denied' }),
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
    `;

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    expect(showErrorDialog).toHaveBeenCalledWith('Error deleting folders: Permission denied');
  });

  it('execCleanup should show error dialog when the API helper rejects', async () => {
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn(),
      performCleanup: vi.fn().mockRejectedValue(new Error('Network down')),
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
    `;

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    expect(showErrorDialog).toHaveBeenCalledWith('Network error while deleting folders.');
  });

  it('initCleanup should be callable without throwing', async () => {
    const mod = await import('../../static/js/features/cleanup.js');
    expect(() => mod.initCleanup()).not.toThrow();
  });

  it('execCleanup should do nothing when no folders selected', async () => {
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));
    const performCleanup = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({
      getCleanupItems: vi.fn(),
      performCleanup,
    }));

    document.getElementById('cleanup-list').innerHTML = `
      <input type="checkbox" class="cleanup-item-checkbox" value="Action">
    `;

    const mod = await import('../../static/js/features/cleanup.js');
    await mod.execCleanup();

    expect(performCleanup).not.toHaveBeenCalled();
  });
});
