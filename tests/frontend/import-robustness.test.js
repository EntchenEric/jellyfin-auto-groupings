/**
 * Regression tests for importing a configuration file.
 *
 * `performImport()` replaced `state.currentConfig` wholesale for a "full
 * config" file and appended to `groups` for a selective import. Two problems
 * followed from that:
 *
 *  - A full-config file without a `groups` key (an older export, or a
 *    hand-written one) left `state.currentConfig.groups` undefined, and the
 *    next `renderGroups()` threw from `updateGlobalSyncExclusionsUI()`'s
 *    `groups.map(...)`, leaving the dashboard blank.
 *  - A rejected `saveConfig()` left the in-memory config already mutated, so
 *    the UI showed groups the server had never stored and the following save
 *    kept failing for a reason nothing pointed at.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { state } from '../../static/js/core/state.js';

const saveConfig = vi.fn(async () => ({ status: 'success' }));

vi.mock('../../static/js/core/api.js', () => ({
    saveConfig: (...args) => saveConfig(...args),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
}));

import { handleFileSelected } from '../../static/js/features/export-import.js';

function mountImportModal() {
    document.body.innerHTML = `
        <div id="import-modal" class="modal" style="display:flex"></div>
        <div id="import-step-1"></div>
        <div id="import-step-2" style="display:none"></div>
        <div id="cancel-import-top"></div>
        <div id="import-warning"></div>
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
    // FileReader is asynchronous.
    await vi.waitFor(() => expect(state.pendingImportData).not.toBe(null));
}

/** Click the modal's confirm button and let the import settle. */
async function clickConfirm() {
    document.getElementById('confirm-import').onclick();
    await new Promise((resolve) => setTimeout(resolve, 20));
}

beforeEach(() => {
    mountImportModal();
    saveConfig.mockClear();
    saveConfig.mockImplementation(async () => ({ status: 'success' }));
    state.currentConfig = { groups: [], scheduler: {} };
    state.pendingImportData = null;
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe('importing a full configuration', () => {
    it('fills in an empty groups list when the file has none', async () => {
        await selectFile({ jellyfin_url: 'http://jellyfin:8096', api_key: 'secret' });
        await clickConfirm();

        expect(Array.isArray(state.currentConfig.groups)).toBe(true);
        expect(state.currentConfig.groups).toEqual([]);
    });

    it('fills in a scheduler object when the file has none', async () => {
        await selectFile({ jellyfin_url: 'http://jellyfin:8096', api_key: 'secret' });
        await clickConfirm();

        expect(state.currentConfig.scheduler).toBeTypeOf('object');
        expect(state.currentConfig.scheduler).not.toBeNull();
    });

    it('replaces groups with the imported ones', async () => {
        await selectFile({
            jellyfin_url: 'http://jellyfin:8096',
            api_key: 'secret',
            groups: [{ name: 'Action', source_type: 'genre' }],
        });
        await clickConfirm();

        expect(state.currentConfig.groups).toHaveLength(1);
        expect(state.currentConfig.groups[0].name).toBe('Action');
    });

    it('rejects a non-list groups value instead of storing it', async () => {
        await selectFile({
            jellyfin_url: 'http://jellyfin:8096',
            api_key: 'secret',
            groups: 'not-a-list',
        });
        await clickConfirm();

        expect(Array.isArray(state.currentConfig.groups)).toBe(true);
        expect(state.currentConfig.groups).toEqual([]);
    });
});

describe('importing selected groupings', () => {
    it('appends the selected groups to the existing ones', async () => {
        state.currentConfig = {
            groups: [{ name: 'Existing', source_type: 'genre' }],
            scheduler: {},
        };
        await selectFile({ groups: [{ name: 'Imported', source_type: 'genre' }] });
        await clickConfirm();

        expect(state.currentConfig.groups.map((g) => g.name)).toEqual([
            'Existing',
            'Imported',
        ]);
    });

    it('keeps the in-memory config unchanged when the server rejects the save', async () => {
        state.currentConfig = {
            groups: [{ name: 'Existing', source_type: 'genre' }],
            scheduler: {},
        };
        const before = JSON.parse(JSON.stringify(state.currentConfig));
        saveConfig.mockImplementation(async () => {
            throw new Error('Invalid config');
        });

        await selectFile({ groups: [{ name: 'Imported', source_type: 'genre' }] });
        await clickConfirm();

        expect(state.currentConfig).toEqual(before);
    });

    it('keeps the modal open when the save fails', async () => {
        saveConfig.mockImplementation(async () => {
            throw new Error('Invalid config');
        });

        await selectFile({ groups: [{ name: 'Imported', source_type: 'genre' }] });
        await clickConfirm();

        expect(document.getElementById('import-modal').style.display).not.toBe('none');
    });
});
