/**
 * Regression tests for the count shown by the sync confirmation dialog.
 *
 * The dialog used to read
 *
 *     This will create/update symlinks for 0 groupings
 *     (0 potential media items).
 *
 * Both numbers were stale. `confirm-sync-group-count` was filled in, but the
 * `potential media items` figure was left at the hard-coded `0` when
 * `showConfirmSyncDialog()` was rewritten to open through `showModal()`, and
 * nothing in the sheet ever updated it — so the dialog understated the work
 * for every user, whatever their configuration. The sentence now states only
 * the figure the client actually knows, and inflects the noun so a single
 * group does not read as "1 groupings".
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const MODAL = `
  <div id="confirm-sync-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <strong id="confirm-sync-group-count"></strong>
    <span id="confirm-sync-group-noun">groupings</span>
    <button class="close-modal-btn">x</button>
  </div>
  <div id="error-dialog-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

beforeEach(() => {
    document.body.innerHTML = MODAL;
    document.body.className = '';
    vi.resetModules();
});

/** Open the dialog with *n* configured groups. */
async function openWith(n) {
    vi.doMock('../../static/js/core/api.js', () => ({ apiPost: vi.fn() }));
    const { state } = await import('../../static/js/core/state.js');
    state.currentConfig = {
        groups: Array.from({ length: n }, (_, i) => ({ name: `G${i}` })),
        scheduler: {},
    };
    const { showConfirmSyncDialog } = await import(
        '../../static/js/features/sync.js'
    );
    showConfirmSyncDialog();
}

describe('sync confirmation dialog counts', () => {
    it('states the number of configured groups', async () => {
        await openWith(3);

        expect(document.getElementById('confirm-sync-group-count').textContent)
            .toBe('3');
    });

    it('uses the singular noun for a single group', async () => {
        await openWith(1);

        expect(document.getElementById('confirm-sync-group-noun').textContent)
            .toBe('grouping');
    });

    it('uses the plural noun for several groups', async () => {
        await openWith(2);

        expect(document.getElementById('confirm-sync-group-noun').textContent)
            .toBe('groupings');
    });

    it('does not claim an item count it never computed', async () => {
        await openWith(2);

        expect(document.getElementById('confirm-sync-item-count')).toBeNull();
    });
});
