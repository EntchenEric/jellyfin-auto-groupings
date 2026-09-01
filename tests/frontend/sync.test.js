/**
 * @file Tests for the sync feature module (sync.js).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Set up the DOM elements that sync.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="status-msg"></div>
    <div id="error-dialog-modal" class="modal">
      <div id="error-dialog-message"></div>
    </div>
    <div id="sync-results-panel" style="display:none"></div>
    <div id="sync-results-content"></div>
    <div id="preview-sync-results"></div>
    <div id="preview-sync-modal" class="modal" style="display:none"></div>
    <div id="confirm-sync-modal" class="modal" style="display:none"></div>
    <div id="confirm-sync-group-count"></div>
  `;
}

describe('sync feature module', () => {
  beforeEach(() => {
    setupDOM();
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should export syncAll, previewSyncAll, showConfirmSyncDialog and initSync', async () => {
    const mod = await import('../../static/js/features/sync.js');
    expect(typeof mod.syncAll).toBe('function');
    expect(typeof mod.previewSyncAll).toBe('function');
    expect(typeof mod.showConfirmSyncDialog).toBe('function');
    expect(typeof mod.initSync).toBe('function');
  });

  it('syncAll should render results and show toast on success', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({
        status: 'success',
        results: [
          { group: 'Action', links: 3 },
          { group: 'Drama', links: 2, error: 'some error' },
        ],
      }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    await mod.syncAll();

    const panel = document.getElementById('sync-results-panel');
    const content = document.getElementById('sync-results-content');
    expect(panel.style.display).toBe('block');
    expect(content.querySelectorAll('.sync-result-entry').length).toBe(2);
    expect(content.querySelector('.sync-result-links').textContent).toBe('3 links');
    expect(content.querySelector('.sync-result-error').textContent).toBe('(some error)');
  });

  it('syncAll should show error dialog on failure', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({ status: 'error', message: 'Sync failed' }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    await mod.syncAll();
    expect(showErrorDialog).toHaveBeenCalledWith('Sync failed');
  });

  it('syncAll should use fallback message when error has no message', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({ status: 'error' }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    await mod.syncAll();
    expect(showErrorDialog).toHaveBeenCalledWith('Sync failed');
  });

  it('previewSyncAll should render group cards on success', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({
        status: 'success',
        results: [
          {
            group: 'Action',
            links: 2,
            items: [{ Name: 'Die Hard', Year: 1988 }, { Name: 'John Wick' }],
          },
          { group: 'Empty', links: 0, items: [] },
          { group: 'Broken', links: 0, error: 'boom' },
        ],
      }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    await mod.previewSyncAll();

    const container = document.getElementById('preview-sync-results');
    const modal = document.getElementById('preview-sync-modal');
    expect(modal.style.display).toBe('flex');
    expect(container.querySelectorAll('.sync-preview-card').length).toBe(3);
    // Item with year renders "Name (Year)"
    expect(container.querySelector('.sync-preview-list li').textContent).toBe('Die Hard (1988)');
    // Item without year renders just the name
    expect(container.querySelectorAll('.sync-preview-list li')[1].textContent).toBe('John Wick');
    // Error group shows error
    expect(container.querySelector('.sync-preview-error').textContent).toBe('Error: boom');
    // Empty group shows empty message
    expect(container.querySelector('.sync-preview-empty').textContent).toBe('No items found for this group.');
  });

  it('previewSyncAll should show empty state when no results', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({ status: 'success', results: [] }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    await mod.previewSyncAll();

    const container = document.getElementById('preview-sync-results');
    expect(container.querySelector('.sync-preview-empty').textContent).toBe('No groupings configured.');
  });

  it('previewSyncAll should show error dialog on failure', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({ status: 'error', message: 'Preview failed' }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    await mod.previewSyncAll();
    expect(showErrorDialog).toHaveBeenCalledWith('Preview failed');
  });

  it('showConfirmSyncDialog should show modal with group count', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    // Set up state with 3 groups
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = { groups: [{}, {}, {}] };

    mod.showConfirmSyncDialog();
    const modal = document.getElementById('confirm-sync-modal');
    expect(modal.style.display).toBe('flex');
    expect(document.getElementById('confirm-sync-group-count').textContent).toBe('3');
    expect(showErrorDialog).not.toHaveBeenCalled();
  });

  it('initSync should be callable without throwing', async () => {
    const mod = await import('../../static/js/features/sync.js');
    expect(() => mod.initSync()).not.toThrow();
  });

  it('previewSyncAll should use fallback message when error has no message', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({ status: 'error' }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    await mod.previewSyncAll();
    expect(showErrorDialog).toHaveBeenCalledWith('Preview failed');
  });

  it('showConfirmSyncDialog should show error when no groups', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/sync.js');
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = { groups: [] };

    mod.showConfirmSyncDialog();
    expect(showErrorDialog).toHaveBeenCalledWith('No groups to sync.');
  });
});
