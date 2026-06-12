// config.js – Configuration loading, saving, form bindings

import { state, sourceOptions, setState } from '../core/state.js';
import { apiGet, apiPost, loadConfig as apiLoadConfig, saveConfig as apiSaveConfig, fetchMetadata } from '../core/api.js';
import { showToast, showErrorDialog, setLoading, showModal, hideModal, getEl, showLoadingOverlay, updateLoadingStatus, hideLoadingOverlay } from '../core/ui.js';
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

        // Show warning banner if environment overrides are active
        showEnvOverrideWarning(cfg._active_env_overrides || {});

        if (state.currentConfig.jellyfin_url && state.currentConfig.api_key) {
            await performSilentTest();
        }
    } catch (err) {
        showErrorDialog('Failed to load configuration');
    }
}

function validateCronField(expr) {
    if (!expr || !expr.trim()) return 'Cron expression must not be empty';
    const fields = expr.trim().split(/\s+/);
    if (fields.length !== 5) return `Cron must have 5 fields (has ${fields.length})`;
    return null; // Deeper validation done server-side
}

export async function saveAllConfig() {
    if (!state.currentConfig.scheduler) state.currentConfig.scheduler = {};
    state.currentConfig.scheduler.global_enabled = getEl('global_scheduler_enabled').checked;
    state.currentConfig.scheduler.global_schedule = getEl('global_sync_schedule').value.trim();
    state.currentConfig.scheduler.cleanup_enabled = getEl('cleanup_scheduler_enabled').checked;
    state.currentConfig.scheduler.cleanup_schedule = getEl('cleanup_sync_schedule').value.trim() || '0 * * * *';

    // Client-side cron validation
    if (state.currentConfig.scheduler.global_enabled) {
        const err = validateCronField(state.currentConfig.scheduler.global_schedule);
        if (err) { showErrorDialog(`Global schedule: ${err}`); return; }
    }
    if (state.currentConfig.scheduler.cleanup_enabled) {
        const err = validateCronField(state.currentConfig.scheduler.cleanup_schedule);
        if (err) { showErrorDialog(`Cleanup schedule: ${err}`); return; }
    }
    for (const g of state.currentConfig.groups) {
        if (g.schedule_enabled && g.schedule) {
            const err = validateCronField(g.schedule);
            if (err) { showErrorDialog(`Group '${g.name}': ${err}`); return; }
        }
    }

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

export function syncDomToState() {
    state.currentConfig.jellyfin_url = getEl('jellyfin_url').value;
    state.currentConfig.api_key = getEl('api_key').value;
    state.currentConfig.target_path = getEl('target_path').value;
    state.currentConfig.media_path_in_jellyfin = getEl('media_path_in_jellyfin').value;
    state.currentConfig.media_path_on_host = getEl('media_path_on_host').value;
    state.currentConfig.auto_create_libraries = getEl('auto_create_libraries').checked;
    state.currentConfig.auto_set_library_covers = getEl('auto_set_library_covers').checked;
    state.currentConfig.target_path_in_jellyfin = getEl('target_path_in_jellyfin').value;
    state.currentConfig.trakt_client_id = getEl('trakt_client_id').value;
    state.currentConfig.tmdb_api_key = getEl('tmdb_api_key').value;
    state.currentConfig.mal_client_id = getEl('mal_client_id').value;
}

export function initConfig() {
    const configForm = getEl('config-form');
    const saveBtn = getEl('save-btn');
    const apiConfigForm = getEl('api-config-form');
    const saveApisBtn = getEl('save-apis-btn');

    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        setLoading(saveBtn, true);
        syncDomToState();
        await saveAllConfig();
        setLoading(saveBtn, false);

        if (state.currentConfig.jellyfin_url && state.currentConfig.api_key) {
            showLoadingOverlay(
                'Reconnecting to Jellyfin',
                'Fetching updated genres, actors, studios, and tags...',
                1
            );
            try {
                await refreshMetadata(updateLoadingStatus);
                updateLoadingStatus('Done', true);
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
        syncDomToState();
        await saveAllConfig();
        setLoading(saveApisBtn, false);
    });
}

/**
 * Shows an info banner in the config UI when environment variable overrides
 * are active. The banner lists which config values are being overridden at
 * runtime so the user is aware the saved config is not the effective value.
 * @param {object} activeOverrides - Map of config key -> env var name
 */
function showEnvOverrideWarning(activeOverrides) {
    const keys = Object.keys(activeOverrides);
    const existingBanner = document.getElementById('env-override-warning');
    if (existingBanner) existingBanner.remove();

    if (keys.length === 0) return;

    const labelMap = {
        api_key: 'Jellyfin API Key',
        trakt_client_id: 'Trakt Client ID',
        tmdb_api_key: 'TMDb API Key',
        mal_client_id: 'MAL Client ID',
        anilist_api_url: 'AniList API URL',
    };

    const items = keys.map(k => {
        const label = labelMap[k] || k;
        const env = activeOverrides[k];
        return `<li><strong>${label}</strong> overridden by <code>${env}</code></li>`;
    }).join('');

    const banner = document.createElement('div');
    banner.id = 'env-override-warning';
    banner.className = 'status-msg info sidebar-error-card';
    banner.innerHTML = `
        <h3 class="sidebar-error-heading">&#x1f6a7; Environment Overrides Active</h3>
        <p class="sidebar-error-text">The saved config values for these fields are being
        ignored at runtime in favor of environment variables:</p>
        <ul style="margin:0.3rem 0 0 1rem;padding:0;font-size:0.85rem;line-height:1.5;">
            ${items}
        </ul>
        <p class="sidebar-error-text" style="margin-top:0.3rem;">
        To use the saved values, unset the corresponding environment variables and restart.</p>
    `;

    // Insert after the connectivity warning
    const sidebar = document.getElementById('sidebar');
    const connWarning = document.getElementById('connection-warning');
    if (sidebar && connWarning) {
        connWarning.insertAdjacentElement('afterend', banner);
    } else if (sidebar) {
        sidebar.prepend(banner);
    }
}
