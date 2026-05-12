// app.js – Application entry point

import { state, metadataTypes } from './core/state.js';
import { getEl, showToast, setLoading } from './core/ui.js';

import { initConfig, loadConfig, saveAllConfig, toggleGlobalScheduler, toggleCleanupScheduler } from './features/config.js';
import { initWizard, openWizardManual } from './features/wizard.js';
import { initMetadata, addMetadataRule, previewGrouping, getFilterValue } from './features/metadata.js';
import { initSync, syncAll, previewSyncAll, showConfirmSyncDialog } from './features/sync.js';
import { initCleanup, openCleanupModal } from './features/cleanup.js';
import { initExportImport, openExportModal, openImportModal, handleFileSelected } from './features/export-import.js';
import { initCoverGenerator } from './features/cover-generator.js';
import { initPathPicker, openPathPicker, closePicker, confirmPicker, pickerOutsideClick } from './features/path-picker.js';
import { initSidebarResizer } from './features/sidebar-resizer.js';
import { renderGroups, cancelEdit, toggleSortOrder, toggleSeasonal, toggleGroupScheduler, populateSeasonalDays, resetFormUI } from './features/groupings.js';

// Listen for cross-module events
document.addEventListener('groups-changed', () => renderGroups());

// Expose to window for inline HTML onclick handlers
window.addMetadataRule = addMetadataRule;
window.previewGrouping = previewGrouping;
window.cancelEdit = cancelEdit;
window.closePicker = closePicker;
window.confirmPicker = confirmPicker;
window.pickerOutsideClick = pickerOutsideClick;
window.openPathPicker = openPathPicker;
window.toggleSortOrder = toggleSortOrder;
window.toggleSeasonal = toggleSeasonal;
window.toggleGroupScheduler = toggleGroupScheduler;
window.toggleGlobalScheduler = toggleGlobalScheduler;
window.toggleCleanupScheduler = toggleCleanupScheduler;

function wireTopbarButtons() {
    // Sync button → confirmation dialog first
    const topbarSyncBtn = getEl('topbar-sync-btn');
    if (topbarSyncBtn) {
        topbarSyncBtn.onclick = async () => {
            setLoading(topbarSyncBtn, true);
            try { await syncAll(); }
            finally { setLoading(topbarSyncBtn, false); }
        };
    }

    // Preview button
    const topbarPreviewBtn = getEl('topbar-preview-btn');
    if (topbarPreviewBtn) {
        topbarPreviewBtn.onclick = async () => {
            setLoading(topbarPreviewBtn, true);
            try { await previewSyncAll(); }
            finally { setLoading(topbarPreviewBtn, false); }
        };
    }

    // Cleanup button
    const topbarCleanupBtn = getEl('topbar-cleanup-btn');
    if (topbarCleanupBtn) {
        topbarCleanupBtn.onclick = openCleanupModal;
    }

    // Export button
    const topbarExportBtn = getEl('topbar-export-btn');
    if (topbarExportBtn) {
        topbarExportBtn.onclick = openExportModal;
    }

    // Import button
    const topbarImportBtn = getEl('topbar-import-btn');
    if (topbarImportBtn) {
        topbarImportBtn.onclick = openImportModal;
    }

    // Wizard button
    const wizardBtn = getEl('topbar-wizard-btn');
    if (wizardBtn) {
        wizardBtn.onclick = openWizardManual;
    }
}

function wireConfirmSyncDialog() {
    const confirmGoBtn = getEl('confirm-sync-go-btn');
    const confirmPreviewBtn = getEl('confirm-sync-preview-btn');

    if (confirmGoBtn) {
        confirmGoBtn.onclick = async () => {
            getEl('confirm-sync-modal').style.display = 'none';
            const topbarSyncBtn = getEl('topbar-sync-btn');
            setLoading(topbarSyncBtn, true);
            try { await syncAll(); }
            finally { setLoading(topbarSyncBtn, false); }
        };
    }

    if (confirmPreviewBtn) {
        confirmPreviewBtn.onclick = async () => {
            getEl('confirm-sync-modal').style.display = 'none';
            await previewSyncAll();
        };
    }
}

function wireImportFilePicker() {
    const selectBtn = getEl('import-select-file-btn');
    const fileInput = getEl('import-file-input');
    if (selectBtn && fileInput) {
        selectBtn.onclick = () => fileInput.click();
        fileInput.onchange = handleFileSelected;
    }
}

function wireMiscButtons() {
    const clearResultsBtn = getEl('clear-sync-results');
    if (clearResultsBtn) {
        clearResultsBtn.onclick = () => {
            getEl('sync-results-panel').style.display = 'none';
            getEl('sync-results-content').innerHTML = '';
        };
    }
}

async function bootstrap() {
    initConfig();
    initMetadata();
    initSync();
    initCleanup();
    initExportImport();
    initCoverGenerator();
    initPathPicker();
    initSidebarResizer();

    wireTopbarButtons();
    wireConfirmSyncDialog();
    wireImportFilePicker();
    wireMiscButtons();

    const groupForm = getEl('group-form');
    groupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const source_type = getEl('source_type').value;
        const val = getFilterValue();

        if (!val) {
            showToast('Please enter or select a filter value', 'error');
            return;
        }

        const groupData = {
            name: getEl('group_name').value,
            source_category: getEl('source_category').value,
            source_type: source_type,
            source_value: val,
            sort_order: getEl('sort_order_enabled').checked ? (getEl('sort_order').value || '') : '',
            schedule_enabled: getEl('schedule_enabled').checked,
            schedule: getEl('group_schedule').value.trim(),
            seasonal_enabled: getEl('seasonal_enabled').checked,
            seasonal_start: `${getEl('seasonal_start_month').value}-${getEl('seasonal_start_day').value}`,
            seasonal_end: `${getEl('seasonal_end_month').value}-${getEl('seasonal_end_day').value}`,
            watch_state: getEl('watch_state').value
        };

        if (metadataTypes.includes(source_type)) {
            if (typeof window._currentMetadataRules !== 'undefined' && Array.isArray(window._currentMetadataRules)) {
                const validRules = window._currentMetadataRules.filter(r => r.value && r.value.trim() !== '');
                if (validRules.length > 0) {
                    groupData.rules = validRules.map(r => ({
                        operator: r.operator || 'AND',
                        type: r.type || (source_type === 'complex' ? 'genre' : source_type),
                        value: r.value
                    }));
                }
            }
        }

        if (!state.currentConfig.groups) state.currentConfig.groups = [];

        if (state.editingIndex >= 0) {
            state.currentConfig.groups[state.editingIndex] = groupData;
            state.editingIndex = -1;
        } else {
            state.currentConfig.groups.push(groupData);
        }

        await saveAllConfig();
        groupForm.reset();
        resetFormUI();
    });

    populateSeasonalDays();

    if (window.location.protocol === 'file:') {
        const warning = getEl('connection-warning');
        if (warning) warning.style.display = 'block';
    } else {
        await loadConfig();
    }

    initWizard();
}

document.addEventListener('DOMContentLoaded', bootstrap);
