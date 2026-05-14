// config.js – Configuration loading, saving, form bindings

import { state, sourceOptions, setState } from '../core/state.js';
import { apiGet, apiPost, loadConfig as apiLoadConfig, saveConfig as apiSaveConfig, fetchMetadata } from '../core/api.js';
import { showToast, setLoading, showModal, hideModal, getEl, showLoadingOverlay, updateLoadingStatus, hideLoadingOverlay } from '../core/ui.js';
import { updateSourceTypeOptions, updateSourceValueUI, refreshMetadata } from './metadata.js';
import { renderGroups } from './groupings.js';
import { updateValidationUI } from './test-connection.js';

export async function loadConfig() {
    try {
        const cfg = await apiLoadConfig();
        state.currentConfig = cfg;
        state.currentConfig.groups = state.currentConfig.groups || [];

        // Backwards compatibility / Data Migration
        state.currentConfig.groups.forEach(g => {
            if (!g.source_category) {
                if (['imdb_list', 'trakt_list'].includes(g.source_type)) {
                    g.source_category = 'external';
                } else {
                    g.source_category = 'jellyfin';
                    if (g.source_type === 'jellyfin_tag') g.source_type = 'tag';
                    if (g.source_type === 'people') g.source_type = 'actor';
                }
            } else if (g.source_type === 'people') {
                g.source_type = 'actor';
            }
            if (g.create_as_collection === undefined) {
                g.create_as_collection = false;
            }
        });

        getEl('jellyfin_url').value = state.currentConfig.jellyfin_url || '';
        getEl('api_key').value = state.currentConfig.api_key || '';
        getEl('target_path').value = state.currentConfig.target_path || '';
        getEl('media_path_in_jellyfin').value = state.currentConfig.media_path_in_jellyfin || state.currentConfig.jellyfin_root || '';
        getEl('media_path_on_host').value = state.currentConfig.media_path_on_host || state.currentConfig.host_root || '';
        getEl('trakt_client_id').value = state.currentConfig.trakt_client_id || '';
        getEl('tmdb_api_key').value = state.currentConfig.tmdb_api_key || '';
        getEl('mal_client_id').value = state.currentConfig.mal_client_id || '';
        getEl('auto_create_libraries').checked = !!state.currentConfig.auto_create_libraries;
        getEl('auto_set_library_covers').checked = !!state.currentConfig.auto_set_library_covers;
        getEl('target_path_in_jellyfin').value = state.currentConfig.target_path_in_jellyfin || '';

        // Scheduler settings
        const sched = state.currentConfig.scheduler || {};
        getEl('global_scheduler_enabled').checked = sched.global_enabled;
        getEl('global_sync_schedule').value = sched.global_schedule || '';
        toggleGlobalScheduler(getEl('global_scheduler_enabled'));
        getEl('cleanup_scheduler_enabled').checked = sched.cleanup_enabled !== false;
        getEl('cleanup_sync_schedule').value = sched.cleanup_schedule || '0 * * * *';
        toggleCleanupScheduler(getEl('cleanup_scheduler_enabled'));

        updateSourceTypeOptions();
        renderGroups();

        if (state.currentConfig.jellyfin_url && state.currentConfig.api_key) {
            await performSilentTest();
        }
    } catch (err) {
        showToast('Failed to load configuration', 'error');
    }
}

export async function saveAllConfig() {
    if (!state.currentConfig.scheduler) state.currentConfig.scheduler = {};
    state.currentConfig.scheduler.global_enabled = getEl('global_scheduler_enabled').checked;
    state.currentConfig.scheduler.global_schedule = getEl('global_sync_schedule').value.trim();
    state.currentConfig.scheduler.cleanup_enabled = getEl('cleanup_scheduler_enabled').checked;
    state.currentConfig.scheduler.cleanup_schedule = getEl('cleanup_sync_schedule').value.trim() || '0 * * * *';

    try {
        await apiSaveConfig(state.currentConfig);
        showToast('Settings saved', 'success');
        renderGroups();
        updateSourceTypeOptions();
    } catch (err) {
        // Error already shown by api.js
    }
}

export async function performSilentTest() {
    const data = {
        jellyfin_url: state.currentConfig.jellyfin_url,
        api_key: state.currentConfig.api_key
    };
    try {
        const result = await apiPost('/api/test-server', data);
        const isValid = result.status === 'success';
        updateValidationUI(isValid);
        if (isValid) refreshMetadata();
    } catch (err) {
        updateValidationUI(false);
    }
}

export function toggleGlobalScheduler(cb) {
    const panel = getEl('global_scheduler_panel');
    if (panel) panel.style.display = cb.checked ? 'block' : 'none';
}

export function toggleCleanupScheduler(cb) {
    const panel = getEl('cleanup_scheduler_panel');
    if (panel) panel.style.display = cb.checked ? 'block' : 'none';
}

export function initConfig() {
    const configForm = getEl('config-form');
    const saveBtn = getEl('save-btn');
    const apiConfigForm = getEl('api-config-form');
    const saveApisBtn = getEl('save-apis-btn');

    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        setLoading(saveBtn, true);
        state.currentConfig.jellyfin_url = getEl('jellyfin_url').value;
        state.currentConfig.api_key = getEl('api_key').value;
        state.currentConfig.target_path = getEl('target_path').value;
        state.currentConfig.media_path_in_jellyfin = getEl('media_path_in_jellyfin').value;
        state.currentConfig.media_path_on_host = getEl('media_path_on_host').value;
        state.currentConfig.auto_create_libraries = getEl('auto_create_libraries').checked;
        state.currentConfig.auto_set_library_covers = getEl('auto_set_library_covers').checked;
        state.currentConfig.target_path_in_jellyfin = getEl('target_path_in_jellyfin').value;
        await saveAllConfig();
        setLoading(saveBtn, false);

        if (state.currentConfig.jellyfin_url && state.currentConfig.api_key) {
            showLoadingOverlay(
                'Reconnecting to Jellyfin',
                'Fetching updated genres, actors, studios, and tags...'
            );
            try {
                await refreshMetadata(updateLoadingStatus);
            } catch (err) {
                // refreshMetadata throws on failure
            } finally {
                hideLoadingOverlay();
            }
        }
    });

    apiConfigForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        setLoading(saveApisBtn, true);
        state.currentConfig.trakt_client_id = getEl('trakt_client_id').value;
        state.currentConfig.tmdb_api_key = getEl('tmdb_api_key').value;
        state.currentConfig.mal_client_id = getEl('mal_client_id').value;
        await saveAllConfig();
        setLoading(saveApisBtn, false);
    });
}
