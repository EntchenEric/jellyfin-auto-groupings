/**
 * Regression tests for focus restoration when a dialog closes (WCAG 2.4.3).
 *
 * `showModal()` used to remember its trigger through the element's `id`:
 *
 *     el.dataset.previousActive = document.activeElement.id || '';
 *
 * Every per-group "Cover" and "Edit" button is built in a loop in
 * `groupings.js` and carries no `id`, so the stored value was always the
 * empty string. `hideModal()` then found no element and returned focus
 * nowhere, leaving it on the closed `role="dialog"` — the next Tab press
 * started again from the top of the document instead of continuing near the
 * button the user had activated.
 *
 * The trigger is now held by reference, so a button without an `id` (or one
 * that Jellyfin re-renders while the dialog is open) restores correctly.
 */

import { describe, it, expect, beforeEach } from 'vitest';

// Imported once: ui.js registers document-level handlers (Escape, backdrop
// click, .close-modal-btn) at module scope, and a second import would stack
// duplicate listeners that consume events before the live dialog sees them.
import * as ui from '../../static/js/core/ui.js';

const MODALS = `
  <button type="button" class="group-action-btn group-action-btn--cover">Cover</button>
  <button type="button" id="export-btn">Export</button>

  <div id="cover-generator-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <input id="cover-text">
    <button type="button" class="close-modal-btn" aria-label="Close">x</button>
  </div>

  <div id="export-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <button type="button" class="close-modal-btn" aria-label="Close">x</button>
  </div>

  <div id="loading-overlay" role="dialog" aria-hidden="true" style="display: none">
    <p id="loading-overlay-status"></p>
  </div>

  <div id="status-msg"></div>
`;

/** Replace the DOM with freshly closed dialogs and reset focus. */
function mount() {
    document.body.innerHTML = MODALS;
    document.body.className = '';
    if (document.activeElement && document.activeElement.blur) {
        document.activeElement.blur();
    }
}

const tick = (ms = 150) => new Promise((resolve) => setTimeout(resolve, ms));

beforeEach(() => {
    mount();
});

describe('focus restoration on modal close', () => {
    it('restores focus to a trigger that has no id', async () => {
        const trigger = document.querySelector('.group-action-btn--cover');
        trigger.focus();
        expect(document.activeElement).toBe(trigger);

        ui.showModal('cover-generator-modal');
        await tick();
        // showModal() moves focus into the dialog.
        expect(document.activeElement).not.toBe(trigger);

        ui.hideModal('cover-generator-modal');

        expect(document.activeElement).toBe(trigger);
    });

    it('restores focus to a trigger that has an id', async () => {
        const trigger = document.getElementById('export-btn');
        trigger.focus();

        ui.showModal('export-modal');
        await tick();
        ui.hideModal('export-modal');

        expect(document.activeElement).toBe(trigger);
    });

    it('restores focus when the dialog is closed with its close button', async () => {
        const trigger = document.querySelector('.group-action-btn--cover');
        trigger.focus();

        ui.showModal('cover-generator-modal');
        await tick();
        document
            .querySelector('#cover-generator-modal .close-modal-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        expect(document.activeElement).toBe(trigger);
    });

    it('drops the reference when the trigger was removed while open', async () => {
        const trigger = document.querySelector('.group-action-btn--cover');
        trigger.focus();

        ui.showModal('cover-generator-modal');
        await tick();
        trigger.remove();

        // A stale node must not be focused, and closing must not throw.
        expect(() => ui.hideModal('cover-generator-modal')).not.toThrow();
        expect(document.getElementById('cover-generator-modal').style.display).toBe('none');
    });

    it('does not steal focus back after a redundant hide', async () => {
        const trigger = document.querySelector('.group-action-btn--cover');
        trigger.focus();

        ui.showModal('cover-generator-modal');
        await tick();
        ui.hideModal('cover-generator-modal');
        expect(document.activeElement).toBe(trigger);

        // The user moves focus elsewhere, then something hides the already
        // closed dialog again. Focus must stay where the user put it.
        const other = document.getElementById('export-btn');
        other.focus();
        ui.hideModal('cover-generator-modal');

        expect(document.activeElement).toBe(other);
    });

    it('restores focus after the loading overlay is hidden', async () => {
        const trigger = document.querySelector('.group-action-btn--cover');
        trigger.focus();

        ui.showLoadingOverlay('Syncing', 'Grouping items...');
        expect(document.getElementById('loading-overlay').style.display).toBe('flex');

        ui.hideLoadingOverlay();

        expect(document.activeElement).toBe(trigger);
    });
});
