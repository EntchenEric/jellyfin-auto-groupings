// export-import.js – Export and import modal logic

import { state } from '../core/state.js';
import { saveConfig } from '../core/api.js';
import { showToast, getEl } from '../core/ui.js';
import { loadConfig } from './config.js';
import { renderGroups } from './groupings.js';

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
            cb.className = 'export-check';
            cb.dataset.index = i;
            cb.setAttribute('style', 'width:18px; height:18px; accent-color: var(--accent-color);');
            item.appendChild(cb);

            const labelDiv = document.createElement('div');
            const nameDiv = document.createElement('div');
            nameDiv.setAttribute('style', 'font-weight:600; font-size:0.95rem;');
            nameDiv.textContent = g.name || 'Unnamed Group';
            const typeDiv = document.createElement('div');
            typeDiv.setAttribute('style', 'font-size:0.8rem; color:var(--text-secondary);');
            typeDiv.textContent = g.source_type || '';
            labelDiv.appendChild(nameDiv);
            labelDiv.appendChild(typeDiv);
            item.appendChild(labelDiv);

            container.appendChild(item);
        });
    }

    document.querySelector('input[name="export-type"][value="all"]').checked = true;
    toggleExportSelection();
    getEl('export-modal').style.display = 'flex';
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
            alert('Please select at least one grouping.');
            return;
        }
        dataToExport = { groups: selectedIndices.map(i => state.currentConfig.groups[i]) };
        filename = 'jellyfin-selected-groupings.json';
    }

    downloadJSON(dataToExport, filename);
    getEl('export-modal').style.display = 'none';
}

export function openImportModal() {
    state.pendingImportData = null;
    getEl('import-step-1').style.display = 'block';
    getEl('import-step-2').style.display = 'none';
    getEl('cancel-import-top').style.display = 'block';
    getEl('import-modal').style.display = 'flex';
}

export function handleFileSelected(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const data = JSON.parse(e.target.result);
            state.pendingImportData = data;
            setupImportStep2(data);
        } catch (err) {
            showToast('Invalid JSON file', 'error');
        }
    };
    reader.readAsText(file);
    event.target.value = '';
}

function setupImportStep2(data) {
    getEl('import-step-1').style.display = 'none';
    getEl('import-step-2').style.display = 'block';
    getEl('cancel-import-top').style.display = 'none';

    const warning = getEl('import-warning');
    const selectionList = getEl('import-selection-list');
    const container = getEl('import-groups-container');
    const confirmBtn = getEl('confirm-import');

    container.innerHTML = '';

    const isFullConfig = data.jellyfin_url !== undefined && data.api_key !== undefined;
    const groups = data.groups || (Array.isArray(data) ? data : null);

    if (isFullConfig) {
        warning.style.display = 'block';
        selectionList.style.display = 'none';
        confirmBtn.textContent = 'Overwrite All';
        confirmBtn.onclick = () => performImport('full');
    } else if (groups) {
        warning.style.display = 'none';
        selectionList.style.display = 'block';
        confirmBtn.textContent = 'Import Selected';

        groups.forEach((g, i) => {
            const item = document.createElement('div');
            item.className = 'modal-item';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = true;
            cb.className = 'import-check';
            cb.dataset.index = i;
            cb.setAttribute('style', 'width:18px; height:18px; accent-color: var(--accent-color);');
            item.appendChild(cb);

            const labelDiv = document.createElement('div');
            const nameDiv = document.createElement('div');
            nameDiv.setAttribute('style', 'font-weight:600; font-size:0.95rem;');
            nameDiv.textContent = g.name || 'Unnamed Group';
            const typeDiv = document.createElement('div');
            typeDiv.setAttribute('style', 'font-size:0.8rem; color:var(--text-secondary);');
            typeDiv.textContent = `${g.source_type || ''}: ${g.source_value || ''}`;
            labelDiv.appendChild(nameDiv);
            labelDiv.appendChild(typeDiv);
            item.appendChild(labelDiv);

            container.appendChild(item);
        });
        confirmBtn.onclick = () => performImport('groups', groups);
    } else {
        showToast('Incompatible file structure', 'error');
        getEl('import-modal').style.display = 'none';
    }
}

async function performImport(type, sourceGroups = null) {
    if (type === 'full') {
        state.currentConfig = state.pendingImportData;
    } else {
        const selectedIndices = Array.from(document.querySelectorAll('.import-check:checked'))
            .map(cb => parseInt(cb.dataset.index));
        const toImport = selectedIndices.map(i => sourceGroups[i]);
        state.currentConfig.groups = [...state.currentConfig.groups, ...toImport];
    }

    await saveConfig(state.currentConfig);
    getEl('import-modal').style.display = 'none';
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
    URL.revokeObjectURL(url);
}

export function initExportImport() {
    // Modal buttons wired via HTML onclicks; init registers if needed
}
