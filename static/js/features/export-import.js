// export-import.js – Export and import modal logic

import { state } from '../core/state.js';
import { saveConfig } from '../core/api.js';
import { showToast, showErrorDialog, showModal, hideModal, getEl } from '../core/ui.js';
import { renderGroups } from './groupings.js';

//: Copy the template shows for a full-config import; restored on every visit
//: because the same element also carries the "entries skipped" note.
const OVERWRITE_WARNING =
    'WARNING: This will overwrite your entire current configuration!';

export function openExportModal() {
    const container = getEl('export-groups-container');
    container.innerHTML = '';

    if (state.currentConfig.groups.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.9rem;">No groups available to export.</p>';
    } else {
        state.currentConfig.groups.forEach((g, i) => {
            const item = document.createElement('div');
            item.className = 'modal-item';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = true;
            cb.className = 'export-check item-checkbox';
            cb.dataset.index = i;
            item.appendChild(cb);

            const labelDiv = document.createElement('div');
            const nameDiv = document.createElement('div');
            nameDiv.className = 'item-name';
            nameDiv.textContent = g.name || 'Unnamed Group';
            const typeDiv = document.createElement('div');
            typeDiv.className = 'item-type';
            typeDiv.textContent = g.source_type || '';
            labelDiv.appendChild(nameDiv);
            labelDiv.appendChild(typeDiv);
            item.appendChild(labelDiv);

            container.appendChild(item);
        });
    }

    document.querySelector('input[name="export-type"][value="all"]').checked = true;
    toggleExportSelection();

    // Wire radio button change events (removes dependency on HTML onchange)
    document.querySelectorAll('input[name="export-type"]').forEach(radio => {
        radio.onchange = toggleExportSelection;
    });

    showModal('export-modal');
}

export function toggleExportSelection() {
    const type = document.querySelector('input[name="export-type"]:checked').value;
    getEl('export-selection-list').style.display = (type === 'selective') ? 'block' : 'none';
}

export function execExport() {
    const type = document.querySelector('input[name="export-type"]:checked').value;
    let dataToExport = {};
    let filename = 'jellyfin-groupings-export.json';

    if (type === 'all') {
        dataToExport = state.currentConfig;
        filename = 'jellyfin-config-full.json';
    } else {
        const selectedIndices = Array.from(document.querySelectorAll('.export-check:checked'))
            .map(cb => parseInt(cb.dataset.index));

        if (selectedIndices.length === 0) {
            showErrorDialog('Please select at least one grouping.');
            return;
        }
        dataToExport = { groups: selectedIndices.map(i => state.currentConfig.groups[i]) };
        filename = 'jellyfin-selected-groupings.json';
    }

    downloadJSON(dataToExport, filename);
    hideModal('export-modal');
}

export function openImportModal() {
    state.pendingImportData = null;
    getEl('import-step-1').style.display = 'block';
    getEl('import-step-2').style.display = 'none';
    getEl('cancel-import-top').style.display = 'block';
    showModal('import-modal');
}

export function handleFileSelected(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const text = e.target.result;
            if (!text || text.trim().length === 0) {
                showErrorDialog('The selected file is empty');
                return;
            }
            const data = JSON.parse(text);
            state.pendingImportData = data;
            setupImportStep2(data);
        } catch (err) {
            if (err instanceof SyntaxError) {
                showErrorDialog('Invalid JSON file — please check the file format');
            } else {
                showErrorDialog('Failed to process import file: ' + err.message);
            }
        }
    };
    reader.onerror = () => {
        showErrorDialog('Failed to read the selected file');
    };
    reader.readAsText(file);
    event.target.value = '';
}

/**
 * Decide what an import payload offers, before any of the modal is rewritten.
 *
 * `data.groups || ...` accepted any truthy value, so a file with
 * `"groups": "not-a-list"` entered the selective branch and threw
 * `groups.forEach is not a function` — after step 2 had already been shown and
 * before the confirm button was wired. The user got a raw `TypeError` in the
 * dialog and a modal whose "Import Selected" button did nothing. Entries in a
 * real list can be malformed the same way: `"groups": [null]` threw while
 * reading `.name`.
 *
 * @param {unknown} data Parsed import payload.
 * @returns {{kind: 'full'} | {kind: 'groups', groups: object[], skipped: number} | {kind: 'invalid', reason: string}}
 */
function classifyImportPayload(data) {
    if (!data || typeof data !== 'object') {
        return { kind: 'invalid', reason: 'Incompatible file structure' };
    }

    // A full config is recognised by its connection keys, and is accepted
    // whatever its `groups` value holds — normalizeImportedConfig() repairs it.
    if (data.jellyfin_url !== undefined && data.api_key !== undefined) {
        return { kind: 'full' };
    }

    const raw = Array.isArray(data) ? data : data.groups;
    if (!Array.isArray(raw)) {
        return {
            kind: 'invalid',
            reason: 'Incompatible file structure — "groups" must be a list',
        };
    }

    const groups = raw.filter(
        (group) => group && typeof group === 'object' && !Array.isArray(group)
    );
    if (groups.length === 0) {
        return {
            kind: 'invalid',
            reason: 'No groupings found in this file',
        };
    }

    return { kind: 'groups', groups, skipped: raw.length - groups.length };
}

function setupImportStep2(data) {
    // Classify first: the previous code switched to step 2 and only then read
    // the payload, so a malformed file left the modal half-converted.
    const payload = classifyImportPayload(data);
    if (payload.kind === 'invalid') {
        // Do not leave a rejected payload staged: the file input is reset for
        // the next attempt, and a lingering pendingImportData is a config the
        // user never confirmed.
        state.pendingImportData = null;
        showErrorDialog(payload.reason);
        // Stay on step 1 so the user can pick another file without reopening
        // the Import modal.
        return;
    }

    getEl('import-step-1').style.display = 'none';
    getEl('import-step-2').style.display = 'flex';
    getEl('cancel-import-top').style.display = 'none';

    const warning = getEl('import-warning');
    const selectionList = getEl('import-selection-list');
    const container = getEl('import-groups-container');
    const confirmBtn = getEl('confirm-import');

    container.innerHTML = '';

    const isFullConfig = payload.kind === 'full';
    const groups = isFullConfig ? null : payload.groups;

    // `#import-warning` carries the overwrite copy in the template and is
    // reused for the "some entries were skipped" note, so each branch states
    // its own text instead of inheriting whatever the previous import left.
    if (isFullConfig) {
        warning.textContent = OVERWRITE_WARNING;
        warning.style.display = 'block';
        selectionList.style.display = 'none';
        confirmBtn.textContent = 'Overwrite All';
        confirmBtn.onclick = () => performImport('full');
    } else {
        if (payload.skipped > 0) {
            // Silently importing fewer groupings than the file lists would
            // look like the import dropped data.
            warning.textContent =
                `${payload.skipped} entr${payload.skipped === 1 ? 'y was' : 'ies were'} ` +
                'not a valid grouping and will not be imported.';
            warning.style.display = 'block';
        } else {
            warning.style.display = 'none';
        }
        selectionList.style.display = 'block';
        confirmBtn.textContent = 'Import Selected';

        groups.forEach((g, i) => {
            const item = document.createElement('div');
            item.className = 'modal-item';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = true;
            cb.className = 'import-check item-checkbox';
            cb.dataset.index = i;
            item.appendChild(cb);

            const labelDiv = document.createElement('div');
            const nameDiv = document.createElement('div');
            nameDiv.className = 'item-name';
            nameDiv.textContent = g.name || 'Unnamed Group';
            const typeDiv = document.createElement('div');
            typeDiv.className = 'item-type';
            typeDiv.textContent = `${g.source_type || ''}: ${g.source_value || ''}`;
            labelDiv.appendChild(nameDiv);
            labelDiv.appendChild(typeDiv);
            item.appendChild(labelDiv);

            container.appendChild(item);
        });
        confirmBtn.onclick = () => performImport('groups', groups);
    }
}

/**
 * Normalise an imported full-config payload into a config the UI can render.
 *
 * An export written by an older version, or a hand-edited file, may have no
 * `groups` key at all or a `groups` value that is not a list. Assigning that
 * payload straight to `state.currentConfig` left `groups` undefined (or a
 * string), and the `renderGroups()` that runs on the next `groups-changed`
 * event then threw from `groups.map(...)`, blanking the dashboard. The same
 * applies to `scheduler`, which `updateGlobalSyncExclusionsUI()` treats as an
 * object.
 *
 * @param {object} data Parsed import payload.
 * @returns {object} A config object with usable `groups` and `scheduler`.
 */
function normalizeImportedConfig(data) {
    const config =
        data && typeof data === 'object' && !Array.isArray(data) ? data : {};

    if (Array.isArray(config.groups)) {
        config.groups = config.groups.filter(
            (group) => group && typeof group === 'object' && !Array.isArray(group)
        );
    } else {
        config.groups = [];
    }

    if (
        !config.scheduler ||
        typeof config.scheduler !== 'object' ||
        Array.isArray(config.scheduler)
    ) {
        config.scheduler = {};
    }

    return config;
}

async function performImport(type, sourceGroups = null) {
    // Snapshot first: the import mutates `state.currentConfig`, and a rejected
    // save has to leave the UI showing exactly what the server still stores.
    const previousConfig = state.currentConfig;
    const previousGroups = Array.isArray(previousConfig?.groups)
        ? previousConfig.groups
        : [];

    if (type === 'full') {
        state.currentConfig = normalizeImportedConfig(state.pendingImportData);
    } else {
        const selectedIndices = Array.from(document.querySelectorAll('.import-check:checked'))
            .map(cb => parseInt(cb.dataset.index, 10))
            .filter(index => Number.isInteger(index) && index >= 0 && index < sourceGroups.length);

        if (selectedIndices.length === 0) {
            showErrorDialog('Please select at least one grouping to import.');
            return;
        }

        const toImport = selectedIndices.map(i => sourceGroups[i]);
        state.currentConfig = {
            ...previousConfig,
            groups: [...previousGroups, ...toImport],
        };
    }

    try {
        await saveConfig(state.currentConfig);
    } catch (err) {
        // api.js has already shown the failure. Keep the modal open so the user can pick
        // a different file, and restore the config the server still holds.
        state.currentConfig = previousConfig;
        return;
    }

    hideModal('import-modal');
    state.pendingImportData = null;
    showToast('Import successful!', 'success');
    renderGroups();
}

function downloadJSON(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 4)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    // Revoke asynchronously: revoking synchronously right after click() can
    // abort the download in some browsers (e.g. Firefox/Safari) before the
    // browser has had a chance to start fetching the blob URL.
    setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function initExportImport() {
    // Modal buttons wired via HTML onclicks; init registers if needed
}
