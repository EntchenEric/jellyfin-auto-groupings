// app.js – Application entry point

import { state, metadataTypes } from './core/state.js';
import { getEl, showToast, showErrorDialog, setLoading, showLoadingOverlay, updateLoadingStatus, hideLoadingOverlay, hideModal } from './core/ui.js';

import { initConfig, loadConfig, saveAllConfig, toggleGlobalScheduler, toggleCleanupScheduler } from './features/config.js';
import { initWizard, openWizardManual } from './features/wizard.js';
import { initMetadata, addMetadataRule, previewGrouping, getFilterValue, refreshMetadata } from './features/metadata.js';
import { fetchUsers } from './core/api.js';
import { initSync, syncAll, previewSyncAll, showConfirmSyncDialog } from './features/sync.js';
import { initCleanup, openCleanupModal } from './features/cleanup.js';
import { initExportImport, openExportModal, openImportModal, handleFileSelected } from './features/export-import.js';
import { initCoverGenerator } from './features/cover-generator.js';
import { initPathPicker, openPathPicker, closePicker, confirmPicker, pickerOutsideClick } from './features/path-picker.js';
import { initSidebarResizer } from './features/sidebar-resizer.js';
import { renderGroups, cancelEdit, toggleSortOrder, toggleSeasonal, toggleGroupScheduler, populateSeasonalDays, resetFormUI, initGroupSearch } from './features/groupings.js';

// Listen for cross-module events
document.addEventListener('groups-changed', () => renderGroups());

// Expose to window for inline HTML onclick handlers (path-picker modal)
window.closePicker = closePicker;
window.confirmPicker = confirmPicker;
window.pickerOutsideClick = pickerOutsideClick;
window.openPathPicker = openPathPicker;

// Expose for JS-injected buttons (group edit inline)
window.cancelEdit = cancelEdit;

// Keyboard shortcuts — scoped so they don't fire when typing in inputs
function wireKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Don't trigger shortcuts when user is typing in an input/textarea/select
        const tag = e.target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        // Don't trigger when a modal is open
        const visibleModal = document.querySelector('.modal[style*="display: flex"], .modal[style*="display: block"]');
        if (visibleModal) return;

        switch (e.key.toLowerCase()) {
            case 's':
                // S = Sync (only when not holding modifier keys)
                if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                    e.preventDefault();
                    const topbarSyncBtn = getEl('topbar-sync-btn');
                    if (topbarSyncBtn) {
                        setLoading(topbarSyncBtn, true);
                        syncAll().finally(() => setLoading(topbarSyncBtn, false));
                    }
                }
                break;
            case 'd':
                // D = Dry-run / Preview
                if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                    e.preventDefault();
                    const topbarPreviewBtn = getEl('topbar-preview-btn');
                    if (topbarPreviewBtn) {
                        setLoading(topbarPreviewBtn, true);
                        previewSyncAll().finally(() => setLoading(topbarPreviewBtn, false));
                    }
                }
                break;
            case 'c':
                // C = Cleanup
                if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                    e.preventDefault();
                    openCleanupModal();
                }
                break;
        }
    });
}

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
            hideModal('confirm-sync-modal');
            const topbarSyncBtn = getEl('topbar-sync-btn');
            setLoading(topbarSyncBtn, true);
            try { await syncAll(); }
            finally { setLoading(topbarSyncBtn, false); }
        };
    }

    if (confirmPreviewBtn) {
        confirmPreviewBtn.onclick = async () => {
            hideModal('confirm-sync-modal');
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

function wireHamburgerButton() {
    const hamburger = getEl('hamburger-btn');
    if (hamburger) {
        hamburger.addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });
    }
}

function wireBrowseButtons() {
    // Browse buttons use data-path-field attribute
    document.querySelectorAll('.browse-btn[data-path-field]').forEach(btn => {
        btn.addEventListener('click', () => {
            const field = btn.getAttribute('data-path-field');
            if (field) {
                openPathPicker(field);
            }
        });
    });
}

function wireSchedulerToggles() {
    const globalToggle = getEl('global_scheduler_enabled');
    if (globalToggle) {
        globalToggle.addEventListener('change', () => toggleGlobalScheduler(globalToggle));
    }
    const cleanupToggle = getEl('cleanup_scheduler_enabled');
    if (cleanupToggle) {
        cleanupToggle.addEventListener('change', () => toggleCleanupScheduler(cleanupToggle));
    }
}

function wireGroupFormEvents() {
    // Wire sort order toggle
    const sortOrderToggle = getEl('sort_order_enabled');
    if (sortOrderToggle) {
        sortOrderToggle.addEventListener('change', () => toggleSortOrder(sortOrderToggle));
    }

    // Wire schedule toggle
    const scheduleToggle = getEl('schedule_enabled');
    if (scheduleToggle) {
        scheduleToggle.addEventListener('change', () => toggleGroupScheduler(scheduleToggle));
    }

    // Wire seasonal toggle
    const seasonalToggle = getEl('seasonal_enabled');
    if (seasonalToggle) {
        seasonalToggle.addEventListener('change', () => toggleSeasonal(seasonalToggle));
    }

    // Wire preview button
    const previewBtn = getEl('preview-fetch-btn');
    if (previewBtn) {
        previewBtn.addEventListener('click', () => previewGrouping());
    }

    // Wire add condition button
    const addRuleBtn = getEl('add-rule-btn');
    if (addRuleBtn) {
        addRuleBtn.addEventListener('click', () => addMetadataRule());
    }

    // Wire cancel edit button
    const cancelEditBtn = getEl('cancel-edit-btn');
    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', () => cancelEdit());
    }
}

function wirePasswordToggles() {
    const eyeSvg = '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    const eyeSlashSvg = '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
    document.querySelectorAll('.toggle-password-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (!input) return;
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            btn.classList.toggle('visible', isPassword);
            btn.setAttribute('aria-label', isPassword ? 'Hide API key' : 'Show API key');
            btn.innerHTML = isPassword ? eyeSlashSvg : eyeSvg;
        });
    });
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
    initGroupSearch();

    wireKeyboardShortcuts();
    wireTopbarButtons();
    wireConfirmSyncDialog();
    wireImportFilePicker();
    wirePasswordToggles();
    wireMiscButtons();
    wireHamburgerButton();
    wireBrowseButtons();
    wireSchedulerToggles();
    wireGroupFormEvents();

    const groupForm = getEl('group-form');
    groupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const source_type = getEl('source_type').value;
        const val = getFilterValue();

        if (!val) {
            showErrorDialog('Please enter or select a filter value');
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
            watch_state: getEl('watch_state').value,
            create_as_collection: getEl('create_as_collection').checked
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

        if (state.currentConfig.jellyfin_url && state.currentConfig.api_key) {
            showLoadingOverlay(
                'Connecting to Jellyfin',
                'Fetching genres, actors, studios, and tags...',
                3
            );
            try {
                await refreshMetadata(updateLoadingStatus);
                updateLoadingStatus('Loading users...', true);
                const data = await fetchUsers();
                updateLoadingStatus('Ready', true);
                if (data.status === 'success') {
                    state.cachedUsers = data.users;
                }
            } catch (err) {
                showErrorDialog('Failed to load data from Jellyfin');
            } finally {
                hideLoadingOverlay();
            }
        }
    }

    initWizard();
}

document.addEventListener('DOMContentLoaded', bootstrap);
