/**
 * Regression tests for the export dialog's Download button.
 *
 * `execExport()` was exported from `features/export-import.js` but nothing
 * ever called it: `initExportImport()` was an empty stub, and the modal's
 * buttons had lost their inline `onclick` attributes when the frontend was
 * modularised. Opening Export and clicking "Download Export" therefore did
 * nothing — the dialog stayed open and no file was written.
 *
 * `initExportImport()` now binds the button, and `bootstrap()` calls it.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/** The subset of the export dialog partial that the wiring touches. */
const MODAL = `
  <div id="export-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <input type="radio" name="export-type" value="all" checked>
    <input type="radio" name="export-type" value="selective">
    <div id="export-selection-list"></div>
    <div id="export-groups-container"></div>
    <button type="button" id="export-download-btn">Download Export</button>
  </div>
  <div id="error-dialog-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

beforeEach(() => {
    document.body.innerHTML = MODAL;
    vi.resetModules();
    vi.restoreAllMocks();
    delete globalThis.fetch;
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('initExportImport', () => {
    it('downloads the configuration when the Download button is clicked', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = {
            jellyfin_url: 'http://jellyfin:8096',
            api_key: 'key',
            groups: [{ name: 'Action', source_type: 'genre', source_value: 'Action' }],
        };

        // jsdom implements neither createObjectURL nor a real download, so both
        // ends of the anchor click are stubbed; the assertion is that the
        // click happens at all.
        globalThis.URL.createObjectURL = vi.fn(() => 'blob:export');
        globalThis.URL.revokeObjectURL = vi.fn();
        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(() => {});

        const { initExportImport } = await import(
            '../../static/js/features/export-import.js'
        );
        initExportImport();

        document.getElementById('export-download-btn').click();

        expect(clickSpy).toHaveBeenCalled();
        expect(globalThis.URL.createObjectURL).toHaveBeenCalled();
    });

    it('closes the dialog after a successful export', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { jellyfin_url: 'u', api_key: 'k', groups: [] };

        globalThis.URL.createObjectURL = vi.fn(() => 'blob:export');
        globalThis.URL.revokeObjectURL = vi.fn();
        vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

        const { initExportImport } = await import(
            '../../static/js/features/export-import.js'
        );
        initExportImport();
        document.getElementById('export-modal').style.display = 'flex';

        document.getElementById('export-download-btn').click();

        expect(document.getElementById('export-modal').style.display).toBe('none');
    });

    it('does not stack handlers when initialised twice', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { jellyfin_url: 'u', api_key: 'k', groups: [] };

        globalThis.URL.createObjectURL = vi.fn(() => 'blob:export');
        globalThis.URL.revokeObjectURL = vi.fn();
        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(() => {});

        const { initExportImport } = await import(
            '../../static/js/features/export-import.js'
        );
        initExportImport();
        initExportImport();

        document.getElementById('export-download-btn').click();

        // One download per click: a stacked handler would write two files.
        expect(clickSpy).toHaveBeenCalledTimes(1);
    });

    it('selects nothing to export without a selection and reports it', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [{ name: 'Action' }] };

        globalThis.URL.createObjectURL = vi.fn(() => 'blob:export');
        globalThis.URL.revokeObjectURL = vi.fn();
        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(() => {});

        const { initExportImport } = await import(
            '../../static/js/features/export-import.js'
        );
        initExportImport();

        // Selective export with an empty group list must warn instead of
        // producing an empty file.
        document.querySelector('input[name="export-type"][value="selective"]').checked = true;
        document.getElementById('export-download-btn').click();

        expect(clickSpy).not.toHaveBeenCalled();
        expect(document.getElementById('error-dialog-message').textContent).toContain(
            'at least one grouping'
        );
    });
});
