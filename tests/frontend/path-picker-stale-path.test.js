/**
 * Regression tests for the folder picker keeping a path from a previous use.
 *
 * `_pickerCurrentPath` was only ever *set*, on a successful browse. Nothing
 * cleared it when the picker was opened again for a different field, or when
 * the next browse failed:
 *
 * 1. Open the picker for "Path in Jellyfin", reach `/media` — the module
 *    remembers `/media`.
 * 2. Cancel.
 * 3. Open the picker for "Base Target Path", whose own value is a directory
 *    the server refuses to list. `browseDir()` renders the error and returns
 *    early, so `_pickerCurrentPath` still holds `/media`, and the breadcrumb
 *    and footer still show `/media` even though the listing is an error.
 * 4. Press "Select" — `/media` is written into the *target path* field.
 *
 * Nothing told the user the value came from a different field: the footer
 * named a path, so the button looked correct. A wrong target path silently
 * scatters symlink folders into the media tree, which is the one thing this
 * dialog exists to prevent.
 *
 * A browse that fails, and every new opening, must leave the picker with no
 * selectable path, so "Select" cannot answer with a directory the user is no
 * longer looking at.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const MODALS = `
  <div id="path-picker-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <div class="picker-title" id="picker-title"></div>
    <div class="picker-breadcrumb" id="picker-breadcrumb"></div>
    <div class="picker-body" id="picker-body"></div>
    <span class="picker-footer-path" id="picker-footer-path">No folder selected</span>
    <button type="button" id="picker-select-btn" class="btn-accent">Select</button>
  </div>
  <input type="text" id="media_path_in_jellyfin" value="/media">
  <input type="text" id="target_path" value="/srv/secret">
  <div id="error-dialog-modal" class="modal" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

beforeEach(() => {
    document.body.innerHTML = MODALS;
    vi.resetModules();
    vi.unstubAllGlobals();
});

/** Stub `fetch` so `/media` lists and `/srv/secret` is rejected. */
function stubBrowse(denied = ['/srv/secret']) {
    vi.stubGlobal('fetch', vi.fn(async (url) => {
        const path = new URL(url).searchParams.get('path');
        if (denied.includes(path)) {
            return {
                ok: false,
                status: 403,
                json: async () => ({ status: 'error', message: 'Access to this path is not permitted' }),
            };
        }
        return {
            ok: true,
            status: 200,
            json: async () => ({ status: 'success', current: path, parent: null, dirs: ['Movies'] }),
        };
    }));
}

const selectBtn = () => document.getElementById('picker-select-btn');

describe('folder picker stale selection', () => {
    it('does not carry a path from a previous opening into another field', async () => {
        stubBrowse();
        const picker = await import('../../static/js/features/path-picker.js');

        // First use: reach /media and cancel.
        await picker.openPathPicker('media_path_in_jellyfin');
        picker.closePicker();

        // Second use: the field's own directory cannot be listed.
        await picker.openPathPicker('target_path');

        // The rejected handler must not leave a selectable path behind.
        expect(selectBtn().disabled).toBe(true);

        picker.confirmPicker();

        expect(document.getElementById('target_path').value).toBe('/srv/secret');
    });

    it('clears the breadcrumb and footer when a browse fails', async () => {
        stubBrowse();
        const picker = await import('../../static/js/features/path-picker.js');

        await picker.openPathPicker('media_path_in_jellyfin');
        // Close and reopen for a directory the server refuses.
        picker.closePicker();
        await picker.openPathPicker('target_path');

        // Neither element may keep naming the directory from the first run.
        expect(document.getElementById('picker-breadcrumb').textContent).not.toBe('/media');
        expect(document.getElementById('picker-footer-path').textContent).not.toBe('/media');
        expect(document.getElementById('picker-footer-path').textContent).toBe('No folder selected');
        // The failure itself is still explained in the listing.
        expect(document.getElementById('picker-body').textContent).toContain('HTTP 403');
    });

    it('enables Select once a directory loads, even if it started disabled', async () => {
        stubBrowse();
        const picker = await import('../../static/js/features/path-picker.js');

        // The template ships the button disabled; a successful browse must
        // turn it back on, or the picker can never confirm anything.
        selectBtn().disabled = true;
        await picker.openPathPicker('media_path_in_jellyfin');

        expect(selectBtn().disabled).toBe(false);
        picker.confirmPicker();
        expect(document.getElementById('media_path_in_jellyfin').value).toBe('/media');
    });

});
