// path-picker.js – Folder path picker and auto-detect logic

import { state } from '../core/state.js';
import { autoDetectPaths as apiAutoDetect } from '../core/api.js';
import { showToast, showErrorDialog, getEl } from '../core/ui.js';

/** @type {string|null} ID of the form input field being picked for */
let _pickerTargetId = null;
/** @type {string|null} Currently browsed directory path */
let _pickerCurrentPath = null;


/**
 * Join a base path with a name, handling the root case correctly.
 *
 * When *base* is ``"/"``, ``base + name`` would produce ``"/dirname"``, so
 * a simple ``base.replace(/\/$/, '') + '/' + name`` is not safe — it would
 * produce ``"""/dirname"`` for the root path.
 *
 * @param {string} base  Base directory path.
 * @param {string} name  Child directory name.
 * @returns {string} Joined path.
 */
function joinPath(base, name) {
    // Normalise trailing slash: keep exactly one for root, strip otherwise.
    const normalized = base === '/' ? '' : base.replace(/\/+$/, '');
    return normalized + '/' + name;
}


export async function openPathPicker(fieldId) {
    _pickerTargetId = fieldId;
    const currentVal = getEl(fieldId).value;
    const titleEl = getEl('picker-title');
    if (fieldId === 'target_path') {
        titleEl.textContent = 'Select Target Path';
    } else if (fieldId === 'media_path_in_jellyfin') {
        titleEl.textContent = 'Select Media Path (Jellyfin side)';
    } else {
        titleEl.textContent = 'Select Media Path (this machine)';
    }
    getEl('path-picker-modal').style.display = 'flex';
    await browseDir(currentVal || '');
}


export async function browseDir(path) {
    const bodyEl = getEl('picker-body');
    bodyEl.innerHTML =
        '<p style="padding:1.5rem; text-align:center; color:var(--text-secondary);">Loading...</p>';
    let result;
    try {
        const resp = await fetch('/api/browse?path=' + encodeURIComponent(path));
        result = await resp.json();
    } catch (e) {
        bodyEl.innerHTML = `<p class="picker-empty">Could not load directory: ${e.message}</p>`;
        return;
    }
    if (result.status !== 'success') {
        bodyEl.innerHTML = `<p class="picker-empty">${result.message}</p>`;
        return;
    }
    _pickerCurrentPath = result.current;
    getEl('picker-breadcrumb').textContent = result.current;
    getEl('picker-footer-path').textContent = result.current;

    bodyEl.innerHTML = '';

    if (result.parent) {
        const up = document.createElement('button');
        up.className = 'picker-item picker-up';
        up.innerHTML = '<span class="picker-item-icon">..</span> (go up)';
        up.onclick = () => browseDir(result.parent);
        bodyEl.appendChild(up);
    }

    if (result.dirs.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'picker-empty';
        empty.textContent = 'No subdirectories here.';
        bodyEl.appendChild(empty);
    } else {
        result.dirs.forEach(name => {
            const btn = document.createElement('button');
            btn.className = 'picker-item';
            const fullPath = joinPath(result.current, name);
            const icon = document.createElement('span');
            icon.className = 'picker-item-icon';
            icon.textContent = '[ ]';
            btn.appendChild(icon);
            btn.appendChild(document.createTextNode(' ' + name));
            btn.title = fullPath;
            btn.onclick = () => browseDir(fullPath);
            bodyEl.appendChild(btn);
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
            showErrorDialog('Auto-detection finished but could not find matching host paths.');
        } else {
            showErrorDialog(result.message || 'Auto-detection failed');
        }
    } catch (err) {
        showErrorDialog('Auto-detection failed - API unreachable');
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
