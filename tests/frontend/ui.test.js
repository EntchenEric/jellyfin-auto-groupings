/**
 * @file Tests for the frontend UI module.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Helper to set up DOM elements that ui.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="status-msg"></div>
    <div id="loading-overlay">
      <div id="loading-overlay-title"></div>
      <div id="loading-overlay-status"></div>
      <div id="progress-bar-fill"></div>
      <div id="progress-percentage"></div>
      <div id="progress-eta" style="display:none"></div>
    </div>
    <div id="error-dialog-modal" class="modal">
      <div id="error-dialog-message"></div>
      <button class="close-modal-btn">X</button>
    </div>
    <div id="confirm-dialog-modal" class="modal">
      <div id="confirm-dialog-title"></div>
      <div id="confirm-dialog-message"></div>
      <button id="confirm-dialog-ok-btn" class="close-modal-btn">Confirm</button>
      <button id="confirm-dialog-cancel-btn" class="close-modal-btn">Cancel</button>
    </div>
    <div id="some-modal" class="modal">
      <button class="close-modal-btn">X</button>
    </div>
    <div id="cover-generator-modal" class="modal"></div>
  `;
}

describe('showToast', () => {
  beforeEach(() => {
    setupDOM();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should display the status message with success class', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('Sync complete!', 'success');

    const el = document.getElementById('status-msg');
    expect(el.textContent).toContain('Sync complete!');
    expect(el.classList.contains('success')).toBe(true);
    expect(el.style.display).toBe('block');
  });

  it('should display error type toasts with error class', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('Something went wrong', 'error');

    const el = document.getElementById('status-msg');
    expect(el.textContent).toContain('Something went wrong');
    expect(el.classList.contains('error')).toBe(true);
  });

  it('should add a close button to the toast', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('Test message');

    const el = document.getElementById('status-msg');
    const closeBtn = el.querySelector('.toast-close');
    expect(closeBtn).not.toBeNull();
  });

  it('should auto-dismiss the toast after the default duration', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('Temporary message');

    const el = document.getElementById('status-msg');
    expect(el.style.display).toBe('block');

    // Fast-forward past the default 5000ms timeout
    vi.advanceTimersByTime(5100);
    expect(el.style.display).toBe('none');
  });

  it('should dismiss error toasts after the longer default duration (8000ms)', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('Error message', 'error');

    const el = document.getElementById('status-msg');

    // Before 8s, it should still be visible
    vi.advanceTimersByTime(7000);
    expect(el.style.display).toBe('block');

    // After 8s, it should be dismissed
    vi.advanceTimersByTime(1100);
    expect(el.style.display).toBe('none');
  });

  it('should use a custom duration when provided', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('Custom', 'success', 2000);

    const el = document.getElementById('status-msg');
    vi.advanceTimersByTime(1500);
    expect(el.style.display).toBe('block');

    vi.advanceTimersByTime(600);
    expect(el.style.display).toBe('none');
  });

  it('should not set display if status-msg element is missing', async () => {
    document.body.innerHTML = '';
    const { showToast } = await import('../../static/js/core/ui.js');
    // Should not throw
    expect(() => showToast('Missing element')).not.toThrow();
  });

  it('should update toastId data attribute to avoid stale timer dismissal', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('First message');
    const el = document.getElementById('status-msg');
    expect(el.dataset.toastId).toBeDefined();
    const firstId = el.dataset.toastId;

    showToast('Second message');
    const secondId = el.dataset.toastId;
    expect(secondId).not.toBe(firstId);
  });

  it('close button should dismiss the toast immediately', async () => {
    const { showToast } = await import('../../static/js/core/ui.js');
    showToast('Dismiss me');
    const el = document.getElementById('status-msg');
    const closeBtn = el.querySelector('.toast-close');

    closeBtn.click();
    expect(el.style.display).toBe('none');
  });
});

describe('getEl', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('should return the element by id', async () => {
    const { getEl } = await import('../../static/js/core/ui.js');
    expect(getEl('status-msg')).toBe(document.getElementById('status-msg'));
  });

  it('should return null for non-existent id', async () => {
    const { getEl } = await import('../../static/js/core/ui.js');
    expect(getEl('non-existent')).toBeNull();
  });
});

describe('showModal / hideModal', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('showModal should set display to flex', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    showModal('error-dialog-modal');
    const el = document.getElementById('error-dialog-modal');
    expect(el.style.display).toBe('flex');
  });

  it('hideModal should set display to none', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    showModal('error-dialog-modal');
    hideModal('error-dialog-modal');
    const el = document.getElementById('error-dialog-modal');
    expect(el.style.display).toBe('none');
  });

  it('showModal should not throw for non-existent id', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    expect(() => showModal('does-not-exist')).not.toThrow();
  });
});

describe('setLoading', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('should add btn-loading class when loading is true', async () => {
    const { setLoading } = await import('../../static/js/core/ui.js');
    const btn = document.createElement('button');
    setLoading(btn, true);
    expect(btn.classList.contains('btn-loading')).toBe(true);
  });

  it('should remove btn-loading class when loading is false', async () => {
    const { setLoading } = await import('../../static/js/core/ui.js');
    const btn = document.createElement('button');
    btn.classList.add('btn-loading');
    setLoading(btn, false);
    expect(btn.classList.contains('btn-loading')).toBe(false);
  });

  it('should not throw for null button', async () => {
    const { setLoading } = await import('../../static/js/core/ui.js');
    expect(() => setLoading(null, true)).not.toThrow();
  });
});

describe('showErrorDialog', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('should display the error message in the modal', async () => {
    const { showErrorDialog } = await import('../../static/js/core/ui.js');
    showErrorDialog('Test error message');

    const msgEl = document.getElementById('error-dialog-message');
    expect(msgEl.textContent).toBe('Test error message');
  });

  it('should show the error dialog modal', async () => {
    const { showErrorDialog } = await import('../../static/js/core/ui.js');
    showErrorDialog('Error');

    const modal = document.getElementById('error-dialog-modal');
    expect(modal.style.display).toBe('flex');
  });

  it('should fall back to showToast when modal elements are missing', async () => {
    document.body.innerHTML = '<div id="status-msg"></div>';
    const { showErrorDialog } = await import('../../static/js/core/ui.js');
    // Should not throw when error-dialog-modal is missing
    expect(() => showErrorDialog('Missing modal')).not.toThrow();
  });
});

describe('showConfirmDialog', () => {
  beforeEach(() => {
    setupDOM();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should display the confirm dialog with correct title and message', async () => {
    const { showConfirmDialog } = await import('../../static/js/core/ui.js');
    const promise = showConfirmDialog('Confirm Delete', 'Are you sure?', 'Delete', 'Cancel');

    const titleEl = document.getElementById('confirm-dialog-title');
    const msgEl = document.getElementById('confirm-dialog-message');
    const okBtn = document.getElementById('confirm-dialog-ok-btn');
    const cancelBtn = document.getElementById('confirm-dialog-cancel-btn');

    expect(titleEl.textContent).toBe('Confirm Delete');
    expect(msgEl.textContent).toBe('Are you sure?');
    expect(okBtn.textContent).toBe('Delete');
    expect(cancelBtn.textContent).toBe('Cancel');

    // Clean up by dismissing
    cancelBtn.click();
    await promise;
  });

  it('should resolve to true when confirm is clicked', async () => {
    const { showConfirmDialog } = await import('../../static/js/core/ui.js');
    const promise = showConfirmDialog('Title', 'Message');

    document.getElementById('confirm-dialog-ok-btn').click();
    const result = await promise;
    expect(result).toBe(true);
  });

  it('should resolve to false when cancel is clicked', async () => {
    const { showConfirmDialog } = await import('../../static/js/core/ui.js');
    const promise = showConfirmDialog('Title', 'Message');

    document.getElementById('confirm-dialog-cancel-btn').click();
    const result = await promise;
    expect(result).toBe(false);
  });

  it('should hide the modal after confirm', async () => {
    const { showConfirmDialog } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('confirm-dialog-modal');
    const promise = showConfirmDialog('Title', 'Message');

    document.getElementById('confirm-dialog-ok-btn').click();
    await promise;
    expect(modal.style.display).toBe('none');
  });

  it('should hide the modal after cancel', async () => {
    const { showConfirmDialog } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('confirm-dialog-modal');
    const promise = showConfirmDialog('Title', 'Message');

    document.getElementById('confirm-dialog-cancel-btn').click();
    await promise;
    expect(modal.style.display).toBe('none');
  });

  it('should fall back to native confirm when modal elements are missing', async () => {
    document.body.innerHTML = '';
    global.confirm = vi.fn().mockReturnValue(true);

    const { showConfirmDialog } = await import('../../static/js/core/ui.js');
    const result = await showConfirmDialog('Title', 'Message');
    expect(result).toBe(true);
  });
});

describe('loading overlay', () => {
  beforeEach(() => {
    setupDOM();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('showLoadingOverlay should show the overlay with correct title', async () => {
    const { showLoadingOverlay } = await import('../../static/js/core/ui.js');
    showLoadingOverlay('Syncing...', 'Processing groups', 5);

    const overlay = document.getElementById('loading-overlay');
    const titleEl = document.getElementById('loading-overlay-title');
    const statusEl = document.getElementById('loading-overlay-status');

    expect(overlay.style.display).toBe('flex');
    expect(titleEl.textContent).toBe('Syncing...');
    expect(statusEl.textContent).toBe('Processing groups');
  });

  it('showLoadingOverlay should use defaults when no title given', async () => {
    const { showLoadingOverlay } = await import('../../static/js/core/ui.js');
    showLoadingOverlay();

    const titleEl = document.getElementById('loading-overlay-title');
    expect(titleEl.textContent).toBe('Connecting to Jellyfin');
  });

  it('hideLoadingOverlay should hide the overlay', async () => {
    const { showLoadingOverlay, hideLoadingOverlay } = await import('../../static/js/core/ui.js');
    showLoadingOverlay('Test');
    hideLoadingOverlay();

    const overlay = document.getElementById('loading-overlay');
    expect(overlay.style.display).toBe('none');
  });

  it('updateLoadingStatus should update the status text', async () => {
    const { showLoadingOverlay, updateLoadingStatus } = await import('../../static/js/core/ui.js');
    showLoadingOverlay('Syncing...', 'Starting', 5);
    updateLoadingStatus('Halfway done');

    const statusEl = document.getElementById('loading-overlay-status');
    expect(statusEl.textContent).toBe('Halfway done');
  });

  it('updateLoadingStatus should advance the progress bar when advanceStep is true', async () => {
    const { showLoadingOverlay, updateLoadingStatus } = await import('../../static/js/core/ui.js');
    showLoadingOverlay('Syncing...', 'Step 0', 5);

    updateLoadingStatus('Step 1', true);
    const fill = document.getElementById('progress-bar-fill');
    expect(fill.style.width).toBe('20%');

    updateLoadingStatus('Step 2', true);
    expect(fill.style.width).toBe('40%');
  });

  it('progress should not exceed 100%', async () => {
    const { showLoadingOverlay, updateLoadingStatus } = await import('../../static/js/core/ui.js');
    showLoadingOverlay('Test', 'Start', 2);

    updateLoadingStatus('Done', true);
    updateLoadingStatus('Over', true);
    updateLoadingStatus('Way Over', true);
    const fill = document.getElementById('progress-bar-fill');

    // Should cap at 100%
    expect(parseInt(fill.style.width)).toBeLessThanOrEqual(100);
  });

  it('should not throw when overlay elements are missing', async () => {
    document.body.innerHTML = '';
    const { showLoadingOverlay, hideLoadingOverlay } = await import('../../static/js/core/ui.js');
    expect(() => showLoadingOverlay('Test')).not.toThrow();
    expect(() => hideLoadingOverlay()).not.toThrow();
  });
});

describe('renderEmptyState', () => {
  it('should create a paragraph with the given message in the container', async () => {
    const { renderEmptyState } = await import('../../static/js/core/ui.js');
    const container = document.createElement('div');
    renderEmptyState(container, 'No items found');

    expect(container.innerHTML).toContain('No items found');
    expect(container.querySelector('p')).not.toBeNull();
    expect(container.querySelector('p').style.color).toBeTruthy();
  });

  it('should clear the container before setting', async () => {
    const { renderEmptyState } = await import('../../static/js/core/ui.js');
    const container = document.createElement('div');
    container.innerHTML = '<p>Old content</p>';
    renderEmptyState(container, 'Empty');

    expect(container.children.length).toBe(1);
    expect(container.textContent).toBe('Empty');
  });
});