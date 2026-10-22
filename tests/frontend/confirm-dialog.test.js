/**
 * Regression tests for `showConfirmDialog()` settlement.
 *
 * The dialog attaches click handlers to its Confirm/Cancel buttons and
 * `hideModal()` closes it for three other paths: the Escape key, a backdrop
 * click, and the × button. Those three never ran the handlers, so the
 * returned promise stayed pending forever and the caller's `await` never
 * resumed. In the UI this looked like the button doing nothing:
 * `deleteGroup()` and `clearAllGroups()` both start with
 * `if (!await showConfirmDialog(...)) return;`.
 *
 * Every close path must settle the promise exactly once, with `false` unless
 * the Confirm button was the trigger.
 */

import { describe, it, expect, beforeEach } from 'vitest';

// Import the module once. `ui.js` registers document-level handlers (Escape,
// backdrop click, .close-modal-btn) at module scope; re-importing it per test
// would stack duplicate listeners, and the first stale copy would consume the
// event before the current dialog's hide listener could run. The app loads the
// module once, so the tests do the same.
import * as ui from '../../static/js/core/ui.js';

const DIALOG = `
  <button id="opener">open</button>
  <div id="confirm-dialog-modal" class="modal" role="alertdialog" aria-hidden="true" style="display: none">
    <div class="modal-content">
      <button type="button" class="close-btn close-modal-btn" aria-label="Close">x</button>
      <h3 id="confirm-dialog-title">Confirm</h3>
      <p id="confirm-dialog-message"></p>
      <button type="button" class="secondary-btn close-modal-btn" id="confirm-dialog-cancel-btn">Cancel</button>
      <button type="button" id="confirm-dialog-ok-btn">Confirm</button>
    </div>
  </div>
  <div id="status-msg"></div>
`;

/** Replace the DOM with a freshly closed dialog. */
function mount() {
    document.body.innerHTML = DIALOG;
    document.body.className = '';
    return ui;
}

/** Open the dialog and return a handle that records the settled value. */
function open({ title = 'Delete Grouping', message = 'Permanently remove?' } = {}) {
    const result = { settled: false, value: undefined };
    ui.showConfirmDialog(title, message, 'Delete', 'Cancel').then((value) => {
        result.settled = true;
        result.value = value;
    });
    return result;
}

/** Let the pending microtasks and the 100 ms focus timer run. */
const tick = (ms = 150) => new Promise((resolve) => setTimeout(resolve, ms));

describe('confirm dialog settlement', () => {
    beforeEach(() => {
        // Every test replaces the DOM, so no dialog state crosses over.
        mount();
    });

    it('resolves true when the confirm button is clicked', async () => {
        const result = open();
        await tick();

        document.getElementById('confirm-dialog-ok-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        await tick(0);
        expect(result.settled).toBe(true);
        expect(result.value).toBe(true);
        expect(document.getElementById('confirm-dialog-modal').style.display).toBe('none');
    });

    it('resolves false when the cancel button is clicked', async () => {
        const result = open();
        await tick();

        document.getElementById('confirm-dialog-cancel-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        await tick(0);
        expect(result.settled).toBe(true);
        expect(result.value).toBe(false);
    });

    it('resolves false when dismissed with the Escape key', async () => {
        const result = open();
        await tick();

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

        await tick(0);
        expect(result.settled).toBe(true);
        expect(result.value).toBe(false);
    });

    it('resolves false on a backdrop click', async () => {
        const result = open();
        await tick();

        const modal = document.getElementById('confirm-dialog-modal');
        modal.dispatchEvent(new MouseEvent('click', { bubbles: true }));

        await tick(0);
        expect(result.settled).toBe(true);
        expect(result.value).toBe(false);
    });

    it('resolves false when the × button closes the dialog', async () => {
        const result = open();
        await tick();

        document.querySelector('#confirm-dialog-modal .close-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        await tick(0);
        expect(result.settled).toBe(true);
        expect(result.value).toBe(false);
    });

    it('does not let a later dialog inherit the earlier dismissal', async () => {
        const first = open();
        await tick();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await tick(0);
        expect(first.value).toBe(false);

        // Re-open and confirm: a stale hide listener from the first dialog
        // must not settle this one early.
        const second = open();
        await tick();
        expect(second.settled).toBe(false);

        document.getElementById('confirm-dialog-ok-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        await tick(0);
        expect(second.value).toBe(true);
    });

    it('ignores a second confirm click after settling', async () => {
        const result = open();
        await tick();

        const okBtn = document.getElementById('confirm-dialog-ok-btn');
        okBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        // The dialog is closed now; a stray click must not resolve twice or
        // throw from a detached handler.
        expect(() => okBtn.dispatchEvent(new MouseEvent('click', { bubbles: true })))
            .not.toThrow();

        await tick(0);
        expect(result.settled).toBe(true);
        expect(result.value).toBe(true);
    });

    it('settles a superseded dialog as cancelled', async () => {
        mount();
        const first = open();
        await tick();
        // A second request replaces the shared dialog; the first caller must
        // not be left waiting forever.
        const second = open({ title: 'Clear All Groupings' });
        await tick(0);

        expect(first.settled).toBe(true);
        expect(first.value).toBe(false);
        expect(second.settled).toBe(false);

        document.getElementById('confirm-dialog-ok-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await tick(0);

        expect(second.settled).toBe(true);
        expect(second.value).toBe(true);
    });

    it('renders the supplied labels', async () => {
        open({ title: 'Clear All Groupings', message: 'This cannot be undone.' });
        await tick();

        expect(document.getElementById('confirm-dialog-title').textContent)
            .toBe('Clear All Groupings');
        expect(document.getElementById('confirm-dialog-message').textContent)
            .toBe('This cannot be undone.');
        expect(document.getElementById('confirm-dialog-ok-btn').textContent).toBe('Delete');
        expect(document.getElementById('confirm-dialog-cancel-btn').textContent).toBe('Cancel');
    });

    it('removes the hide listener once settled', async () => {
        const result = open();
        await tick();

        document.getElementById('confirm-dialog-ok-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await tick(0);
        expect(result.settled).toBe(true);

        // Hiding the already-closed dialog again must be a no-op, not a
        // second resolution attempt.
        ui.hideModal('confirm-dialog-modal');
        expect(result.value).toBe(true);
    });
});
