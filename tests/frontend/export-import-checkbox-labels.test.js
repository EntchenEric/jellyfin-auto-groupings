/**
 * Regression tests for the accessible names of the export/import checkboxes.
 *
 * Both dialogs build their selection list in JavaScript: one row per grouping,
 * each holding a checkbox. The row used to be a plain `<div>`, which left the
 * checkbox with no accessible name at all — a screen reader announced it as
 * just "checkbox", with nothing saying *which* grouping it would export or
 * import (WCAG 1.3.1 and 4.1.2). Clicking the group name did nothing either,
 * because a `<div>` does not forward a click to the checkbox it sits next to;
 * only the 18px box itself was a target.
 *
 * Each row is now a `<label>` wrapping its checkbox, and the checkbox carries
 * an explicit `aria-label` naming the grouping. The label's own text would
 * otherwise be read as "Action genre", so the name is set on the checkbox
 * rather than inherited from the whole row.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/** The subset of the export dialog the list rendering touches. */
const EXPORT_MODAL = `
  <div id="export-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <input type="radio" name="export-type" value="all" checked>
    <input type="radio" name="export-type" value="selective">
    <div id="export-selection-list"></div>
    <div id="export-groups-container"></div>
    <button type="button" id="export-download-btn">Download Export</button>
  </div>
  <div id="import-modal" class="modal" aria-hidden="true" style="display: none">
    <div id="import-step-1"></div>
    <div id="import-step-2"></div>
    <div id="cancel-import-top"></div>
    <div id="import-warning"></div>
    <div id="import-selection-list"></div>
    <div id="import-groups-container"></div>
    <button type="button" id="confirm-import"></button>
  </div>
  <div id="error-dialog-modal" class="modal" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

const saveConfig = vi.fn(async () => ({ status: 'success' }));

beforeEach(() => {
    document.body.innerHTML = EXPORT_MODAL;
    vi.resetModules();
    vi.restoreAllMocks();
    saveConfig.mockClear();
    vi.doMock('../../static/js/core/api.js', () => ({
        saveConfig,
        apiGet: vi.fn(),
        apiPost: vi.fn(),
    }));
});

afterEach(() => {
    vi.restoreAllMocks();
});

/** Load the module with a two-group config already in state. */
async function withGroups() {
    const { state } = await import('../../static/js/core/state.js');
    state.currentConfig = {
        jellyfin_url: 'http://jellyfin:8096',
        api_key: 'key',
        groups: [
            { name: 'Action', source_type: 'genre', source_value: 'Action' },
            { name: 'Anime/Action', source_type: 'tag', source_value: 'anime' },
        ],
    };
    return import('../../static/js/features/export-import.js');
}

/** Text a screen reader would use as the name of *el*. */
function accessibleName(el) {
    return (
        el.getAttribute('aria-label') ||
        el.labels?.[0]?.textContent?.trim() ||
        ''
    );
}

/**
 * Read a Blob as text.
 *
 * jsdom's `Blob` implements neither `text()` nor `arrayBuffer()`, so the
 * export payload is read through `FileReader`, which it does implement.
 *
 * @param {Blob} blob
 * @returns {Promise<string>}
 */
function readBlob(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsText(blob);
    });
}

describe('export dialog checkbox labels', () => {
    it('names every checkbox after the grouping it exports', async () => {
        const { openExportModal } = await withGroups();
        openExportModal();

        const boxes = [...document.querySelectorAll('#export-groups-container .export-check')];
        expect(boxes).toHaveLength(2);
        expect(boxes.map(accessibleName)).toEqual([
            'Export grouping Action',
            'Export grouping Anime/Action',
        ]);
    });

    it('wraps each checkbox in its row label so the name is clickable', async () => {
        const { openExportModal } = await withGroups();
        openExportModal();

        const box = document.querySelector('#export-groups-container .export-check');
        const row = box.closest('.modal-item');
        expect(row.tagName).toBe('LABEL');
        expect(row.contains(box)).toBe(true);
        // The group name lives inside the same row, so clicking it reaches the
        // checkbox through the label rather than beside it.
        expect(row.textContent).toContain('Action');
    });

    it('still exports the selected groupings after the markup change', async () => {
        const { openExportModal, execExport } = await withGroups();
        globalThis.URL.createObjectURL = vi.fn(() => 'blob:export');
        globalThis.URL.revokeObjectURL = vi.fn();
        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(() => {});

        openExportModal();
        // Switch to selective mode: opening the dialog resets the radio to
        // "all", which exports the whole config and ignores the checkboxes.
        document.querySelector('input[name="export-type"][value="selective"]').checked = true;
        // Deselect the second grouping: the surviving one must still be read
        // from `data-index`, which the label wrapper must not disturb.
        const boxes = document.querySelectorAll('.export-check');
        boxes[1].checked = false;
        execExport();

        expect(clickSpy).toHaveBeenCalledTimes(1);
        const blob = globalThis.URL.createObjectURL.mock.calls[0][0];
        const payload = JSON.parse(await readBlob(blob));
        expect(payload.groups.map((g) => g.name)).toEqual(['Action']);
    });

    it('falls back to a descriptive name when the group has none', async () => {
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [{ source_type: 'genre' }] };
        const { openExportModal } = await import(
            '../../static/js/features/export-import.js'
        );

        openExportModal();

        const box = document.querySelector('.export-check');
        expect(accessibleName(box)).toBe('Export grouping Unnamed Group');
    });
});

describe('import dialog checkbox labels', () => {
    it('names every checkbox after the grouping it imports', async () => {
        const { handleFileSelected } = await withGroups();

        // Drive the real file-selection path so the import list is built by
        // the same code the dialog uses.
        const file = new File(
            [JSON.stringify({
                groups: [
                    { name: 'Action', source_type: 'genre', source_value: 'Action' },
                    { name: 'Anime/Action', source_type: 'tag', source_value: 'anime' },
                ],
            })],
            'groups.json',
            { type: 'application/json' },
        );
        handleFileSelected({ target: { files: [file], value: 'groups.json' } });

        await vi.waitFor(() =>
            expect(
                document.querySelectorAll('#import-groups-container .import-check'),
            ).toHaveLength(2),
        );

        const boxes = [...document.querySelectorAll('#import-groups-container .import-check')];
        expect(boxes.map(accessibleName)).toEqual([
            'Import grouping Action',
            'Import grouping Anime/Action',
        ]);
        expect(boxes[0].closest('.modal-item').tagName).toBe('LABEL');
    });
});
