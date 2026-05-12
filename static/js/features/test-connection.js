// test-connection.js – Unified test connection logic

import { state } from '../core/state.js';
import { testServer } from '../core/api.js';
import { showToast, setLoading, getEl } from '../core/ui.js';
import { updateSourceTypeOptions, refreshMetadata } from './metadata.js';
import { autoDetectIfEmpty } from './path-picker.js';
import { saveAllConfig } from './config.js';

export function updateValidationUI(isValid) {
    state.isServerValidated = isValid;
    const statusDot = getEl('status-dot');
    const statusText = getEl('status-text');
    const maintenanceCard = getEl('maintenance-card');
    const groupingsSection = getEl('groupings-section');
    const schedulerCard = getEl('scheduler-card');

    const pathFieldIds = ['target_path', 'media_path_in_jellyfin', 'media_path_on_host', 'target_path_in_jellyfin'];
    const pathGroupIds = ['target_path_group', 'media_path_in_jellyfin_group', 'media_path_on_host_group', 'target_path_in_jellyfin_group'];

    if (isValid) {
        statusDot.className = 'connection-dot online';
        statusText.textContent = 'Connected';
        maintenanceCard.classList.remove('locked-section');
        groupingsSection.classList.remove('locked-section');
        if (schedulerCard) schedulerCard.classList.remove('locked-section');
        pathFieldIds.forEach(id => { const el = getEl(id); if (el) el.disabled = false; });
        pathGroupIds.forEach(id => {
            const el = getEl(id);
            if (el) { el.classList.remove('path-field-locked'); el.querySelectorAll('button').forEach(b => b.disabled = false); }
        });
    } else {
        statusDot.className = 'connection-dot offline';
        statusText.textContent = 'Disconnected';
        maintenanceCard.classList.add('locked-section');
        groupingsSection.classList.add('locked-section');
        if (schedulerCard) schedulerCard.classList.add('locked-section');
        pathFieldIds.forEach(id => { const el = getEl(id); if (el) el.disabled = true; });
        pathGroupIds.forEach(id => {
            const el = getEl(id);
            if (el) { el.classList.add('path-field-locked'); el.querySelectorAll('button').forEach(b => b.disabled = true); }
        });
    }
    updateSourceTypeOptions();
}

export async function testConnection(url, apiKey) {
    try {
        const result = await testServer(url, apiKey);
        if (result.status === 'success') {
            return { success: true, message: result.message };
        } else {
            return { success: false, message: result.message || 'Connection failed' };
        }
    } catch (err) {
        return { success: false, message: 'API unreachable' };
    }
}

export async function testConnectionFromSidebar() {
    const testBtn = getEl('test-btn');
    setLoading(testBtn, true);
    const url = getEl('jellyfin_url').value;
    const apiKey = getEl('api_key').value;

    const result = await testConnection(url, apiKey);
    if (result.success) {
        showToast(result.message, 'success');
        updateValidationUI(true);
        state.currentConfig.jellyfin_url = url;
        state.currentConfig.api_key = apiKey;
        state.currentConfig.target_path = getEl('target_path').value;
        await saveAllConfig();
        await refreshMetadata();
        await autoDetectIfEmpty();
    } else {
        showToast(result.message, 'error');
        updateValidationUI(false);
    }
    setLoading(testBtn, false);
}
