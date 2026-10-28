/**
 * Regression tests for the cleanup dialog's Delete button.
 *
 * `execCleanup()` was exported from `features/cleanup.js` but never called:
 * `initCleanup()` was an empty stub and the button had lost its inline
 * `onclick` during the frontend modularisation. "Delete Selected" in the
 * Clean Up Folders dialog therefore did nothing, which left the cleanup flow
 * with no way to delete anything from the UI.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const MODAL = `
  <div id="cleanup-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <div id="cleanup-loading"></div>
    <div id="cleanup-error"></div>
    <div id="cleanup-content">
      <div id="cleanup-list">
        <label class="cleanup-item">
          <input type="checkbox" class="cleanup-item-checkbox" value="Action" checked>
        </label>
        <label class="cleanup-item">
          <input type="checkbox" class="cleanup-item-checkbox" value="Comedy" checked>
        </label>
      </div>
    </div>
    <button type="button" id="confirm-cleanup-btn">Delete Selected</button>
  </div>
  <div id="error-dialog-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

const performCleanup = vi.fn(async () => ({
    status: 'success',
    deleted: 2,
    errors: [],
}));
const getCleanupItems = vi.fn(async () => ({ status: 'success', items: [] }));

beforeEach(() => {
    document.body.innerHTML = MODAL;
    vi.resetModules();
    vi.restoreAllMocks();
    performCleanup.mockClear();
    getCleanupItems.mockClear();
    vi.doMock('../../static/js/core/api.js', () => ({
        performCleanup,
        getCleanupItems,
    }));
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('initCleanup', () => {
    it('deletes the selected folders when the button is clicked', async () => {
        const { initCleanup } = await import('../../static/js/features/cleanup.js');
        initCleanup();

        document.getElementById('confirm-cleanup-btn').click();
        await vi.waitFor(() => expect(performCleanup).toHaveBeenCalled());

        expect(performCleanup).toHaveBeenCalledWith(['Action', 'Comedy']);
    });

    it('does nothing when no folder is selected', async () => {
        document
            .querySelectorAll('#cleanup-list input[type="checkbox"]')
            .forEach((cb) => {
                cb.checked = false;
            });

        const { initCleanup } = await import('../../static/js/features/cleanup.js');
        initCleanup();

        document.getElementById('confirm-cleanup-btn').click();
        await Promise.resolve();

        expect(performCleanup).not.toHaveBeenCalled();
    });

    it('does not stack handlers when initialised twice', async () => {
        const { initCleanup } = await import('../../static/js/features/cleanup.js');
        initCleanup();
        initCleanup();

        document.getElementById('confirm-cleanup-btn').click();
        await vi.waitFor(() => expect(performCleanup).toHaveBeenCalledTimes(1));

        // Give a stacked second handler the chance to run before asserting.
        await Promise.resolve();
        expect(performCleanup).toHaveBeenCalledTimes(1);
    });

    it('reports a failed delete instead of staying silent', async () => {
        performCleanup.mockResolvedValueOnce({
            status: 'error',
            message: 'Target directory is not writable',
        });

        const { initCleanup } = await import('../../static/js/features/cleanup.js');
        initCleanup();

        document.getElementById('confirm-cleanup-btn').click();
        await vi.waitFor(() =>
            expect(
                document.getElementById('error-dialog-message').textContent
            ).toContain('not writable')
        );
    });

    it('restores the button after a failed delete', async () => {
        performCleanup.mockRejectedValueOnce(new Error('network down'));

        const { initCleanup } = await import('../../static/js/features/cleanup.js');
        initCleanup();

        const btn = document.getElementById('confirm-cleanup-btn');
        btn.click();
        await vi.waitFor(() => expect(btn.textContent).toContain('Delete Selected'));

        expect(btn.disabled).toBe(false);
    });
});
