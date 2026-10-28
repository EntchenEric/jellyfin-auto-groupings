/**
 * Regression tests for malformed selective-import payloads.
 *
 * `setupImportStep2()` chose its branch with `data.groups || (Array.isArray(data) ? data : null)`.
 * Any truthy value therefore took the selective path, which immediately ran
 * `groups.forEach(...)`:
 *
 *  - `"groups": "not-a-list"` threw `TypeError: groups.forEach is not a
 *    function`. Step 2 had already been shown and `#confirm-import` had no
 *    handler yet, so the dialog displayed a raw internal error and its
 *    "Import Selected" button did nothing at all.
 *  - `"groups": [null]` threw while reading `g.name`, with the same result.
 *
 * The payload is now classified before the modal is rewritten: a non-list
 * `groups` (or a list with no usable object) is rejected on step 1, and
 * unusable entries inside an otherwise valid list are filtered out and
 * reported instead of aborting the import.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { state } from '../../static/js/core/state.js';

const saveConfig = vi.fn(async () => ({ status: 'success' }));

vi.mock('../../static/js/core/api.js', () => ({
    saveConfig: (...args) => saveConfig(...args),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
}));

import { handleFileSelected } from '../../static/js/features/export-import.js';

const WARNING_TEXT = 'WARNING: This will overwrite your entire current configuration!';

function mountImportModal() {
    document.body.innerHTML = `
        <div id="import-modal" class="modal" style="display:none"></div>
        <div id="import-step-1" style="display:block"></div>
        <div id="import-step-2" style="display:none"></div>
        <div id="cancel-import-top" style="display:block"></div>
        <div id="import-warning" style="display:none">${WARNING_TEXT}</div>
        <div id="import-selection-list"></div>
        <div id="import-groups-container"></div>
        <button id="confirm-import"></button>
        <div id="error-dialog-modal" class="modal" style="display:none">
            <p id="error-dialog-message"></p>
        </div>
        <div id="groups-list"></div>
        <div id="global_sync_exclusions"></div>
        <div id="groups-count-badge"></div>
        <div id="status-msg"></div>
    `;
}

/** Feed *data* through the hidden file input the way a user would. */
async function selectFile(data) {
    const file = new File([JSON.stringify(data)], 'config.json', {
        type: 'application/json',
    });
    handleFileSelected({ target: { files: [file], value: 'config.json' } });
    // FileReader is asynchronous. Either step 2 becomes visible, or the
    // payload was rejected and the error dialog is populated — wait for the
    // handler to have run rather than for a fixed delay.
    await vi.waitFor(() => {
        const advanced =
            document.getElementById('import-step-2').style.display === 'flex';
        const rejected = errorMessage() !== '';
        expect(advanced || rejected).toBe(true);
    });
}

function errorMessage() {
    return document.getElementById('error-dialog-message').textContent;
}

beforeEach(() => {
    mountImportModal();
    saveConfig.mockClear();
    saveConfig.mockImplementation(async () => ({ status: 'success' }));
    state.currentConfig = { groups: [], scheduler: {} };
    state.pendingImportData = null;
});

describe('a groups value that is not a list', () => {
    it('does not surface an internal TypeError', async () => {
        await selectFile({ groups: 'not-a-list' });

        expect(errorMessage()).not.toContain('forEach');
        expect(errorMessage()).not.toContain('not a function');
    });

    it('explains that groups must be a list', async () => {
        await selectFile({ groups: 'not-a-list' });

        expect(errorMessage()).toContain('must be a list');
    });

    it('leaves the modal on step 1 so another file can be chosen', async () => {
        await selectFile({ groups: 'not-a-list' });

        expect(document.getElementById('import-step-2').style.display).toBe('none');
        expect(document.getElementById('import-step-1').style.display).toBe('block');
    });

    it('discards the rejected payload instead of leaving it staged', async () => {
        await selectFile({ groups: 'not-a-list' });

        expect(state.pendingImportData).toBeNull();
    });
});

describe('a groups list containing unusable entries', () => {
    it('does not surface an internal TypeError for a null entry', async () => {
        await selectFile({ groups: [null] });

        expect(errorMessage()).not.toContain('reading');
        expect(errorMessage()).not.toContain('null');
    });

    it('rejects a list with no usable grouping at all', async () => {
        await selectFile({ groups: [null, 'Action', 42] });

        expect(errorMessage()).toContain('No groupings found');
        expect(document.getElementById('import-step-2').style.display).toBe('none');
    });

    it('imports the valid entries and reports the skipped ones', async () => {
        await selectFile({
            groups: [null, { name: 'Action', source_type: 'genre' }],
        });

        const warning = document.getElementById('import-warning');
        expect(warning.style.display).toBe('block');
        expect(warning.textContent).toContain('1 entry was');
        expect(
            document.querySelectorAll('#import-groups-container .modal-item')
        ).toHaveLength(1);
    });
});

describe('the overwrite warning', () => {
    it('is shown for a full-config import', async () => {
        await selectFile({ jellyfin_url: 'http://jellyfin:8096', api_key: 'secret' });

        const warning = document.getElementById('import-warning');
        expect(warning.style.display).toBe('block');
        expect(warning.textContent).toBe(WARNING_TEXT);
        expect(document.getElementById('confirm-import').textContent).toBe('Overwrite All');
    });

    it('is restored after an import that reused it for the skipped note', async () => {
        await selectFile({
            groups: [null, { name: 'Action', source_type: 'genre' }],
        });
        expect(document.getElementById('import-warning').textContent).not.toBe(WARNING_TEXT);

        // Reopening the modal and importing a full config must not inherit the
        // previous run's text.
        document.getElementById('import-step-1').style.display = 'block';
        document.getElementById('import-step-2').style.display = 'none';
        await selectFile({ jellyfin_url: 'http://jellyfin:8096', api_key: 'secret' });

        expect(document.getElementById('import-warning').textContent).toBe(WARNING_TEXT);
    });

    it('is hidden for a clean selective import', async () => {
        await selectFile({ groups: [{ name: 'Action', source_type: 'genre' }] });

        expect(document.getElementById('import-warning').style.display).toBe('none');
        expect(document.getElementById('confirm-import').textContent).toBe('Import Selected');
    });
});
