// wizard.js – Setup wizard logic

import { state } from '../core/state.js';
import { apiPost, autoDetectPaths } from '../core/api.js';
import { testConnection } from './test-connection.js';
import { showToast, setLoading, showModal, hideModal, getEl } from '../core/ui.js';
import { saveAllConfig } from './config.js';

let wizardStep = 1;
let isWizardServerConnected = false;
const totalSteps = 4;

export function openWizardManual() {
    wizardStep = 1;
    isWizardServerConnected = false;
    getEl('wizard_jellyfin_url').value = state.currentConfig.jellyfin_url || '';
    getEl('wizard_api_key').value = state.currentConfig.api_key || '';
    getEl('wizard_media_path_in_jellyfin').value = state.currentConfig.media_path_in_jellyfin || '';
    getEl('wizard_media_path_on_host').value = state.currentConfig.media_path_on_host || '';
    getEl('wizard_target_path').value = state.currentConfig.target_path || '';

    getEl('wizard_jellyfin_url').oninput = () => { isWizardServerConnected = false; updateWizardUI(); };
    getEl('wizard_api_key').oninput = () => { isWizardServerConnected = false; updateWizardUI(); };

    getEl('wizard-next').onclick = wizardNext;
    getEl('wizard-back').onclick = wizardPrev;

    updateWizardUI();
    showModal('setup-wizard-modal');
}

function updateWizardUI() {
    for (let i = 1; i <= totalSteps; i++) {
        getEl(`wizard-step-${i}`).classList.toggle('active', i === wizardStep);
    }
    const progress = (wizardStep / totalSteps) * 100;
    getEl('wizard-progress-bar').style.width = `${progress}%`;

    const backBtn = getEl('wizard-back');
    const nextBtn = getEl('wizard-next');
    backBtn.style.visibility = wizardStep === 1 ? 'hidden' : 'visible';

    if (wizardStep === totalSteps) {
        nextBtn.textContent = 'Finish & Restart';
        nextBtn.onclick = finishWizard;
        nextBtn.disabled = false;
    } else {
        nextBtn.textContent = wizardStep === 1 ? 'Get Started' : 'Continue';
        nextBtn.onclick = wizardNext;
        if (wizardStep === 2) {
            nextBtn.disabled = !isWizardServerConnected;
            nextBtn.style.opacity = isWizardServerConnected ? '1' : '0.5';
            nextBtn.title = isWizardServerConnected ? '' : 'Please test your connection first';
        } else {
            nextBtn.disabled = false;
            nextBtn.style.opacity = '1';
            nextBtn.title = '';
        }
    }
}

export function wizardNext() {
    if (wizardStep < totalSteps) { wizardStep++; updateWizardUI(); }
}

export function wizardPrev() {
    if (wizardStep > 1) { wizardStep--; updateWizardUI(); }
}

export async function testWizardConnection() {
    const btn = getEl('wizard-test-btn');
    const statusDiv = getEl('wizard-conn-status');
    setLoading(btn, true);
    statusDiv.style.display = 'none';

    const url = getEl('wizard_jellyfin_url').value;
    const apiKey = getEl('wizard_api_key').value;
    const result = await testConnection(url, apiKey);

    if (result.success) {
        statusDiv.textContent = 'Connected successfully!';
        statusDiv.className = 'status-msg success';
        isWizardServerConnected = true;
        state.currentConfig.jellyfin_url = url;
        state.currentConfig.api_key = apiKey;
        updateWizardUI();
    } else {
        statusDiv.textContent = result.message;
        statusDiv.className = 'status-msg error';
        isWizardServerConnected = false;
        updateWizardUI();
    }
    statusDiv.style.display = 'block';
    setLoading(btn, false);
}

export async function runWizardAutoDetect() {
    const btn = getEl('wizard-detect-btn');
    setLoading(btn, true);

    state.currentConfig.jellyfin_url = getEl('wizard_jellyfin_url').value;
    state.currentConfig.api_key = getEl('wizard_api_key').value;

    try {
        await apiPost('/api/config', state.currentConfig);
        const res = await autoDetectPaths();
        if (res.status === 'success' && res.detected) {
            const d = res.detected;
            if (d.media_path_in_jellyfin) { getEl('wizard_media_path_in_jellyfin').value = d.media_path_in_jellyfin; getEl('badge-j-path').style.display = 'inline-flex'; }
            if (d.media_path_on_host) { getEl('wizard_media_path_on_host').value = d.media_path_on_host; getEl('badge-h-path').style.display = 'inline-flex'; }
            if (d.target_path) { getEl('wizard_target_path').value = d.target_path; getEl('badge-t-path').style.display = 'inline-flex'; }
            showToast('Paths detected!', 'success');
        } else {
            showToast(res.message || 'Detection failed', 'error');
        }
    } catch (err) {
        showToast('Auto-detect failed - network error', 'error');
    } finally {
        setLoading(btn, false);
    }
}

async function finishWizard() {
    const url = getEl('wizard_jellyfin_url').value.trim();
    const key = getEl('wizard_api_key').value.trim();
    const jPath = getEl('wizard_media_path_in_jellyfin').value.trim();
    const hPath = getEl('wizard_media_path_on_host').value.trim();
    const tPath = getEl('wizard_target_path').value.trim();

    if (!url || !key || !jPath || !hPath || !tPath) {
        showToast('All fields are required to complete the setup.', 'error');
        if (!url) getEl('wizard_jellyfin_url').focus();
        else if (!key) getEl('wizard_api_key').focus();
        else if (!jPath) getEl('wizard_media_path_in_jellyfin').focus();
        else if (!hPath) getEl('wizard_media_path_on_host').focus();
        else if (!tPath) getEl('wizard_target_path').focus();
        return;
    }

    const nextBtn = getEl('wizard-next');
    setLoading(nextBtn, true);

    state.currentConfig.jellyfin_url = url;
    state.currentConfig.api_key = key;
    state.currentConfig.media_path_in_jellyfin = jPath;
    state.currentConfig.media_path_on_host = hPath;
    state.currentConfig.target_path = tPath;

    try {
        await apiPost('/api/config', { ...state.currentConfig, setup_done: true });
        hideModal('setup-wizard-modal');
        window.location.reload();
    } catch (err) {
        showToast('Failed to finalise setup', 'error');
    } finally {
        setLoading(nextBtn, false);
    }
}

export function initWizard() {
    getEl('wizard-test-btn').onclick = testWizardConnection;
    getEl('wizard-detect-btn').onclick = runWizardAutoDetect;
    getEl('wizard-next').onclick = wizardNext;
    getEl('wizard-back').onclick = wizardPrev;

    if (!state.currentConfig.setup_done) {
        openWizardManual();
    }
}
