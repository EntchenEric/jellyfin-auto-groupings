// path-picker.js – Folder path picker and auto-detect logic

import { state } from '../core/state.js';
import { autoDetectPaths as apiAutoDetect } from '../core/api.js';
import { showToast, getEl } from '../core/ui.js';

let _pickerTargetId = null;
let _pickerCurrentPath = null;

export async function openPathPicker(fieldId) {
    _pickerTargetId = fieldId;
    const currentVal = getEl(fieldId).value;
    getEl('picker-title').textContent =
        fieldId === 'target_path' ? 'Select Target Path' :
            fieldId === 'media_path_in_jellyfin' ? 'Select Media Path (Jellyfin side)' :
                'Select Media Path (this machine)';
    getEl('path-picker-modal').style.display = 'flex';
    await browseDir(currentVal || '');
}

export async function browseDir(path) {
    getEl('picker-body').innerHTML =
        '<p style="padding:1.5rem; text-align:center; color:var(--text-secondary);">Loading...</p>';
    let result;
    try {
        const resp = await fetch('/api/browse?path=' + encodeURIComponent(path));
        result = await resp.json();
    } catch (e) {
        getEl('picker-body').innerHTML = `<p class="picker-empty">Could not load directory: ${e.message}</p>`;
        return;
    }
    if (result.status !== 'success') {
        getEl('picker-body').innerHTML = `<p class="picker-empty">${result.message}</p>`;
        return;
    }
    _pickerCurrentPath = result.current;
    getEl('picker-breadcrumb').textContent = result.current;
    getEl('picker-footer-path').textContent = result.current;

    const body = getEl('picker-body');
    body.innerHTML = '';

    if (result.parent) {
        const up = document.createElement('button');
        up.className = 'picker-item picker-up';
        up.innerHTML = '<span class="picker-item-icon">..</span> (go up)';
        up.onclick = () => browseDir(result.parent);
        body.appendChild(up);
    }

    if (result.dirs.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'picker-empty';
        empty.textContent = 'No subdirectories here.';
        body.appendChild(empty);
    } else {
        result.dirs.forEach(name => {
            const btn = document.createElement('button');
            btn.className = 'picker-item';
            const fullPath = result.current.replace(/\/$/, '') + '/' + name;
            const icon = document.createElement('span');
            icon.className = 'picker-item-icon';
            icon.textContent = '[ ]';
            btn.appendChild(icon);
            btn.appendChild(document.createTextNode(' ' + name));
            btn.title = fullPath;
            btn.onclick = () => browseDir(fullPath);
            body.appendChild(btn);
        });
    }
}

export function confirmPicker() {
    if (_pickerTargetId && _pickerCurrentPath) {
        getEl(_pickerTargetId).value = _pickerCurrentPath;
    }
    closePicker();
}

export function closePicker() {
    getEl('path-picker-modal').style.display = 'none';
    _pickerTargetId = null;
}

export function pickerOutsideClick(e) {
    if (e.target === getEl('path-picker-modal')) closePicker();
}

export async function autoDetectPaths() {
    const detectBtn = getEl('auto-detect-btn');
    detectBtn.classList.add('btn-loading');
    try {
        const result = await apiAutoDetect();
        if (result.status === 'success' && result.detected.media_path_on_host) {
            getEl('media_path_in_jellyfin').value = result.detected.media_path_in_jellyfin;
            getEl('media_path_on_host').value = result.detected.media_path_on_host;
            getEl('target_path').value = result.detected.target_path;
            getEl('target_path_in_jellyfin').value = result.detected.target_path_in_jellyfin;
            state.currentConfig.media_path_in_jellyfin = result.detected.media_path_in_jellyfin;
            state.currentConfig.media_path_on_host = result.detected.media_path_on_host;
            state.currentConfig.target_path = result.detected.target_path;
            state.currentConfig.target_path_in_jellyfin = result.detected.target_path_in_jellyfin;
            showToast('Paths auto-detected! Remember to Save.', 'success');
        } else if (result.status === 'success') {
            showToast('Auto-detection finished but could not find matching host paths.', 'error');
        } else {
            showToast(result.message || 'Auto-detection failed', 'error');
        }
    } catch (err) {
        showToast('Auto-detection failed - API unreachable', 'error');
    } finally {
        detectBtn.classList.remove('btn-loading');
    }
}

export async function autoDetectIfEmpty() {
    const targetEl = getEl('target_path');
    const jfEl = getEl('media_path_in_jellyfin');
    const hostEl = getEl('media_path_on_host');
    if (targetEl.value && jfEl.value && hostEl.value) return;
    try {
        const result = await apiAutoDetect();
        if (result.status !== 'success') return;
        const d = result.detected;
        if (!targetEl.value && d.target_path) { targetEl.value = d.target_path; state.currentConfig.target_path = d.target_path; }
        if (!jfEl.value && d.media_path_in_jellyfin) { jfEl.value = d.media_path_in_jellyfin; state.currentConfig.media_path_in_jellyfin = d.media_path_in_jellyfin; }
        if (!hostEl.value && d.media_path_on_host) { hostEl.value = d.media_path_on_host; state.currentConfig.media_path_on_host = d.media_path_on_host; }
        if (d.target_path_in_jellyfin) { getEl('target_path_in_jellyfin').value = d.target_path_in_jellyfin; state.currentConfig.target_path_in_jellyfin = d.target_path_in_jellyfin; }
        showToast('Paths auto-filled - review and save.', 'success');
    } catch (_) { /* silently ignore */ }
}

export function initPathPicker() {
    // Path picker buttons wired via HTML onclicks
}
