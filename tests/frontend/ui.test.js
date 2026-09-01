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

  it('should not throw when the overlay exists but progress elements are missing', async () => {
    // Overlay present, but the progress-bar-fill / percentage / eta children
    // are absent — _updateProgressBar must guard against the missing nodes.
    document.body.innerHTML = `
      <div id="loading-overlay">
        <div id="loading-overlay-title"></div>
        <div id="loading-overlay-status"></div>
      </div>
    `;
    const { showLoadingOverlay, updateLoadingStatus, hideLoadingOverlay } =
      await import('../../static/js/core/ui.js');
    expect(() => showLoadingOverlay('Test', 'Start', 5)).not.toThrow();
    expect(() => updateLoadingStatus('Step', true)).not.toThrow();
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

describe('hideModal focus restoration and body class', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('should restore focus to the element that triggered the modal', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const trigger = document.createElement('button');
    trigger.id = 'open-modal-trigger';
    document.body.appendChild(trigger);
    trigger.focus();

    showModal('some-modal');
    expect(document.body.classList.contains('modal-open')).toBe(true);

    hideModal('some-modal');
    expect(document.activeElement).toBe(trigger);
  });

  it('should remove modal-open body class when no modals remain visible', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    // Simulate the real CSS state: hidden modals have display:none
    document.querySelectorAll('.modal').forEach((m) => { m.style.display = 'none'; });
    showModal('some-modal');
    expect(document.body.classList.contains('modal-open')).toBe(true);

    hideModal('some-modal');
    expect(document.body.classList.contains('modal-open')).toBe(false);
  });

  it('should keep modal-open body class when another modal is still visible', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    showModal('some-modal');
    showModal('cover-generator-modal');

    hideModal('some-modal');
    // cover-generator-modal is still visible, so body class stays
    expect(document.body.classList.contains('modal-open')).toBe(true);
  });

  it('should not throw when hiding a non-existent modal', async () => {
    const { hideModal } = await import('../../static/js/core/ui.js');
    expect(() => hideModal('does-not-exist')).not.toThrow();
  });
});

describe('modal keyboard and backdrop handlers', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('should close the topmost visible modal on Escape key', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    expect(modal.style.display).toBe('flex');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(modal.style.display).toBe('none');
  });

  it('should not close anything when Escape pressed with no visible modal', async () => {
    const modal = document.getElementById('some-modal');
    modal.style.display = 'none';
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(modal.style.display).toBe('none');
  });

  it('should close a modal when its backdrop is clicked', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    expect(modal.style.display).toBe('flex');

    // Simulate a click directly on the modal element (the backdrop)
    modal.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(modal.style.display).toBe('none');
  });

  it('should not close a modal when clicking inside its content area', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    const inner = document.createElement('div');
    modal.appendChild(inner);

    inner.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(modal.style.display).toBe('flex');
  });

  it('should close a modal via Escape without a trigger element without throwing', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    // No element has data-modal/onclick pointing at some-modal, so the
    // trigger lookup returns null and the focus-restore branch is skipped.
    expect(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    }).not.toThrow();
    expect(modal.style.display).toBe('none');
  });

  it('should close a modal via its close button without a trigger element without throwing', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    const closeBtn = modal.querySelector('.close-modal-btn');
    // No data-modal/onclick trigger exists for some-modal, so the
    // focus-restore branch is skipped.
    expect(() => {
      closeBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }).not.toThrow();
    expect(modal.style.display).toBe('none');
  });
});

describe('progress bar ETA display', () => {
  beforeEach(() => {
    setupDOM();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should show ETA when remaining time exceeds 2 seconds', async () => {
    const { showLoadingOverlay, updateLoadingStatus } = await import('../../static/js/core/ui.js');
    const etaEl = document.getElementById('progress-eta');

    showLoadingOverlay('Test', 'Start', 10);
    // Simulate elapsed time so the per-step estimate yields > 2s remaining
    vi.setSystemTime(Date.now() + 10000);
    updateLoadingStatus('Step 1', true);

    expect(etaEl.style.display).toBe('inline');
    expect(etaEl.textContent).toMatch(/s remaining/);
  });

  it('should hide ETA when remaining time is small', async () => {
    const { showLoadingOverlay, updateLoadingStatus } = await import('../../static/js/core/ui.js');
    const etaEl = document.getElementById('progress-eta');

    showLoadingOverlay('Test', 'Start', 10);
    // No meaningful elapsed time -> remaining estimate stays <= 2s
    updateLoadingStatus('Step 1', true);

    expect(etaEl.style.display).toBe('none');
  });

  it('should hide ETA on the final step', async () => {
    const { showLoadingOverlay, updateLoadingStatus } = await import('../../static/js/core/ui.js');
    const etaEl = document.getElementById('progress-eta');

    showLoadingOverlay('Test', 'Start', 1);
    updateLoadingStatus('Done', true);

    expect(etaEl.style.display).toBe('none');
  });
});

describe('modal focus trap', () => {
  beforeEach(() => {
    setupDOM();
    // Use fake timers so the async focus scheduled by showModal() does not
    // leak across tests and interfere with the synchronous Tab assertions.
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should wrap Tab from the last focusable element back to the first', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    // cover-generator-modal is empty in setupDOM, so we control its focusables.
    const modal = document.getElementById('cover-generator-modal');
    const btn1 = document.createElement('button');
    btn1.id = 'trap-btn-1';
    const btn2 = document.createElement('button');
    btn2.id = 'trap-btn-2';
    modal.appendChild(btn1);
    modal.appendChild(btn2);

    showModal('cover-generator-modal');
    // Flush the async focus scheduled by showModal() so it cannot race with
    // the explicit focus below.
    vi.runAllTimers();
    btn2.focus();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(btn1);
    hideModal('cover-generator-modal');
  });

  it('should wrap Shift+Tab from the first focusable element back to the last', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('cover-generator-modal');
    const btn1 = document.createElement('button');
    btn1.id = 'trap-btn-1';
    const btn2 = document.createElement('button');
    btn2.id = 'trap-btn-2';
    modal.appendChild(btn1);
    modal.appendChild(btn2);

    showModal('cover-generator-modal');
    vi.runAllTimers();
    btn1.focus();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }));
    expect(document.activeElement).toBe(btn2);
    hideModal('cover-generator-modal');
  });

  it('should not trap Tab when no modal is open', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('cover-generator-modal');
    const btn1 = document.createElement('button');
    btn1.id = 'trap-btn-1';
    const btn2 = document.createElement('button');
    btn2.id = 'trap-btn-2';
    modal.appendChild(btn1);
    modal.appendChild(btn2);

    showModal('cover-generator-modal');
    hideModal('cover-generator-modal');
    // setupDOM() does not include the CSS that hides .modal by default, so
    // explicitly hide every modal to simulate the real closed state.
    document.querySelectorAll('.modal').forEach((m) => { m.style.display = 'none'; });
    btn1.focus();

    // With no visible modal, Tab should not be intercepted (default action allowed).
    const evt = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    document.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(false);
  });

  it('should trap focus in the topmost modal when several are open', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('some-modal');
    const btn1 = document.createElement('button');
    btn1.id = 'trap-btn-1';
    modal.appendChild(btn1);

    const cover = document.getElementById('cover-generator-modal');
    const btn2 = document.createElement('button');
    btn2.id = 'trap-btn-2';
    cover.appendChild(btn2);

    showModal('some-modal');
    showModal('cover-generator-modal');
    btn2.focus();

    // Topmost modal is cover-generator-modal; Tab wraps within it.
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(btn2);
    hideModal('cover-generator-modal');
    hideModal('some-modal');
  });

  it('should exclude focusables inside a hidden ancestor from the trap', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('cover-generator-modal');

    // A visible button and a button nested inside a display:none container.
    const visibleBtn = document.createElement('button');
    visibleBtn.id = 'trap-visible';
    const hiddenWrapper = document.createElement('div');
    hiddenWrapper.style.display = 'none';
    const hiddenBtn = document.createElement('button');
    hiddenBtn.id = 'trap-hidden';
    hiddenWrapper.appendChild(hiddenBtn);
    modal.appendChild(visibleBtn);
    modal.appendChild(hiddenWrapper);

    showModal('cover-generator-modal');
    vi.runAllTimers();
    visibleBtn.focus();

    // Tab from the only visible focusable should wrap back to itself, never
    // landing on the hidden button (which must be excluded by _isVisible).
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(visibleBtn);
    hideModal('cover-generator-modal');
  });

  it('should prevent Tab and keep focus on the modal when it has no focusable elements', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('cover-generator-modal');
    // cover-generator-modal is empty in setupDOM — no focusable children.

    showModal('cover-generator-modal');
    vi.runAllTimers();

    const evt = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    document.dispatchEvent(evt);
    // With no focusable elements, the trap must prevent the default Tab
    // behaviour (which would otherwise move focus to the browser chrome).
    expect(evt.defaultPrevented).toBe(true);
    hideModal('cover-generator-modal');
  });

  it('should wrap Tab from the last focusable element back to the first', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('cover-generator-modal');
    const btn1 = document.createElement('button');
    btn1.id = 'trap-first';
    const btn2 = document.createElement('button');
    btn2.id = 'trap-last';
    modal.appendChild(btn1);
    modal.appendChild(btn2);

    showModal('cover-generator-modal');
    vi.runAllTimers();
    btn2.focus();

    // Tab from the last focusable should wrap back to the first, keeping
    // keyboard focus trapped inside the modal (WCAG 2.1.2).
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(btn1);
    hideModal('cover-generator-modal');
  });

  it('should wrap Tab back to the first when focus is outside the modal', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('cover-generator-modal');
    const btn1 = document.createElement('button');
    btn1.id = 'trap-outside-first';
    const btn2 = document.createElement('button');
    btn2.id = 'trap-outside-last';
    modal.appendChild(btn1);
    modal.appendChild(btn2);

    showModal('cover-generator-modal');
    vi.runAllTimers();
    // Focus is on an element outside the modal (e.g. the background page).
    const outside = document.createElement('button');
    outside.id = 'trap-outside';
    document.body.appendChild(outside);
    outside.focus();

    // Tab with focus outside the modal should pull focus back to the first
    // focusable inside the modal.
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(btn1);
    hideModal('cover-generator-modal');
  });

  it('should wrap Shift+Tab back to the last when focus is outside the modal', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('cover-generator-modal');
    const btn1 = document.createElement('button');
    btn1.id = 'trap-shift-first';
    const btn2 = document.createElement('button');
    btn2.id = 'trap-shift-last';
    modal.appendChild(btn1);
    modal.appendChild(btn2);

    showModal('cover-generator-modal');
    vi.runAllTimers();
    // Focus is on an element outside the modal.
    const outside = document.createElement('button');
    outside.id = 'trap-shift-outside';
    document.body.appendChild(outside);
    outside.focus();

    // Shift+Tab with focus outside the modal should pull focus back to the
    // last focusable inside the modal.
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }));
    expect(document.activeElement).toBe(btn2);
    hideModal('cover-generator-modal');
  });

  it('should restore focus to the trigger element when closing via Escape', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('some-modal');
    const trigger = document.createElement('button');
    trigger.id = 'escape-trigger';
    trigger.setAttribute('data-modal', 'some-modal');
    document.body.appendChild(trigger);
    trigger.focus();

    showModal('some-modal');
    expect(modal.style.display).toBe('flex');
    // The trigger id is stored so hideModal can restore focus to it.
    expect(modal.dataset.previousActive).toBe('escape-trigger');
    // Advance the focus timer so focus actually moves into the modal first.
    vi.runAllTimers();
    expect(modal.contains(document.activeElement)).toBe(true);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(modal.style.display).toBe('none');
    // Focus should be restored to the element that opened the modal.
    expect(document.activeElement).toBe(trigger);
  });

  it('should restore focus to the trigger element when closing via close button', async () => {
    const { showModal } = await import('../../static/js/core/ui.js');
    const modal = document.getElementById('some-modal');
    const trigger = document.createElement('button');
    trigger.id = 'close-trigger';
    trigger.setAttribute('data-modal', 'some-modal');
    document.body.appendChild(trigger);
    trigger.focus();

    showModal('some-modal');
    expect(modal.dataset.previousActive).toBe('close-trigger');
    // Advance the focus timer so focus actually moves into the modal first.
    vi.runAllTimers();
    expect(modal.contains(document.activeElement)).toBe(true);

    const closeBtn = modal.querySelector('.close-modal-btn');
    closeBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(modal.style.display).toBe('none');
    // Focus should be restored to the element that opened the modal.
    expect(document.activeElement).toBe(trigger);
  });
});

describe('showModal previousActive handling', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('should store an empty previousActive when the active element has no id', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const trigger = document.createElement('button');
    // No id set on purpose — the previousActive fallback should be empty.
    document.body.appendChild(trigger);
    trigger.focus();

    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    expect(modal.dataset.previousActive).toBe('');

    // Hiding should not throw even though there is no stored trigger id.
    expect(() => hideModal('some-modal')).not.toThrow();
  });

  it('should not store previousActive when the active element is the body', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    // Ensure focus is on the body (no element focused).
    document.body.focus();

    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    expect(modal.dataset.previousActive).toBe('');

    expect(() => hideModal('some-modal')).not.toThrow();
  });
});

describe('hideModal focus restoration when trigger is missing', () => {
  beforeEach(() => {
    setupDOM();
  });

  it('should not throw when the previousActive element no longer exists', async () => {
    const { showModal, hideModal } = await import('../../static/js/core/ui.js');
    const trigger = document.createElement('button');
    trigger.id = 'vanished-trigger';
    document.body.appendChild(trigger);
    trigger.focus();

    showModal('some-modal');
    const modal = document.getElementById('some-modal');
    expect(modal.dataset.previousActive).toBe('vanished-trigger');

    // Remove the trigger element before hiding — focus restoration must
    // gracefully skip the missing element instead of throwing.
    trigger.remove();
    expect(() => hideModal('some-modal')).not.toThrow();
  });
});
