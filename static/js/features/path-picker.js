// path-picker.js – Folder path picker and auto-detect logic

import { state } from '../core/state.js';
import { autoDetectPaths as apiAutoDetect, browsePath } from '../core/api.js';
import { showModal, hideModal, showToast, showErrorDialog, getEl } from '../core/ui.js';

/** @type {string|null} ID of the form input field being picked for */
let _pickerTargetId = null;
/** @type {string|null} Currently browsed directory path */
let _pickerCurrentPath = null;


/**
 * Forget the currently browsed directory.
 *
 * ``_pickerCurrentPath`` used to be write-only on success. Opening the
 * picker for another field after a failed browse left the *previous* run's
 * directory selectable: the breadcrumb and footer still named it, and
 * "Select" wrote it into the other field. A wrong target path silently
 * scatters symlink folders into the media tree.
 *
 * @returns {void}
 */
function clearPickerSelection() {
    _pickerCurrentPath = null;
    const pathEl = getEl('picker-footer-path');
    if (pathEl) pathEl.textContent = 'No folder selected';
    const crumbEl = getEl('picker-breadcrumb');
    if (crumbEl) crumbEl.textContent = '/';
    // A disabled "Select" is the visible signal that there is nothing to
    // confirm; leaving it enabled let the button answer with a directory the
    // user is no longer looking at.
    const selectBtn = getEl('picker-select-btn');
    if (selectBtn) selectBtn.disabled = true;
}

/**
 * Record the directory currently on screen as the selectable one.
 *
 * @param {string} path Absolute path just listed.
 * @returns {void}
 */
function setPickerSelection(path) {
    _pickerCurrentPath = path;
    const selectBtn = getEl('picker-select-btn');
    if (selectBtn) selectBtn.disabled = false;
}


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
    // Every opening starts with nothing selectable: the field being picked is
    // new, so a path left over from the previous one must not answer for it.
    clearPickerSelection();
    showModal('path-picker-modal');
    await browseDir(currentVal || '');
}


export async function browseDir(path) {
    const bodyEl = getEl('picker-body');
    // No path is selectable until this browse succeeds; the previous
    // directory is not what the user is about to look at.
    clearPickerSelection();
    bodyEl.innerHTML =
        '<p style="padding:1.5rem; text-align:center; color:var(--text-secondary);">Loading...</p>';
    let result;
    try {
        // Routed through the shared API client rather than a bare fetch() so
        // the Basic-Auth header is attached when APP_PASSWORD is set. A raw
        // fetch() sent no credentials, so the picker showed "HTTP 401" for
        // every directory even though the rest of the SPA worked.
        result = await browsePath(path);
    } catch (e) {
        // ApiError carries the server's message ("Access to this path is not
        // permitted", "Invalid path"); a transport failure has none, so fall
        // back to the status code or a generic hint.
        const detail = e && e.message ? e.message : 'directory could not be read';
        const status = e && e.status ? ` (HTTP ${e.status})` : '';
        // Built with textContent, not innerHTML: the server echoes the
        // rejected path back in its message, and a folder named
        // `<img src=x onerror=...>` would otherwise run as markup in the
        // dashboard origin (stored XSS from a filesystem name).
        const p = document.createElement('p');
        p.className = 'picker-empty';
        p.textContent = `Could not load directory${status}: ${detail}`;
        bodyEl.innerHTML = '';
        bodyEl.appendChild(p);
        return;
    }
    if (result.status !== 'success') {
        const p = document.createElement('p');
        p.className = 'picker-empty';
        p.textContent = result.message || 'Could not load directory';
        bodyEl.innerHTML = '';
        bodyEl.appendChild(p);
        return;
    }
    setPickerSelection(result.current);
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
    hideModal('path-picker-modal');
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
        // ``detected`` is read only after this guard: a success body without
        // it (an older server, a proxy error page answering 200), or a body
        // that is not an object at all, threw ``Cannot read properties of
        // undefined`` and the Auto-Detect button then reported nothing.
        const detected = result && typeof result === 'object' ? result.detected : null;
        const ok = !!result && result.status === 'success';
        if (ok && detected && detected.media_path_on_host) {
            getEl('media_path_in_jellyfin').value = detected.media_path_in_jellyfin;
            getEl('media_path_on_host').value = detected.media_path_on_host;
            getEl('target_path').value = detected.target_path;
            getEl('target_path_in_jellyfin').value = detected.target_path_in_jellyfin;
            state.currentConfig.media_path_in_jellyfin = detected.media_path_in_jellyfin;
            state.currentConfig.media_path_on_host = detected.media_path_on_host;
            state.currentConfig.target_path = detected.target_path;
            state.currentConfig.target_path_in_jellyfin = detected.target_path_in_jellyfin;
            showToast('Paths auto-detected! Remember to Save.', 'success');
        } else if (ok) {
            showErrorDialog('Auto-detection finished but could not find matching host paths.');
        } else {
            showErrorDialog((result && result.message) || 'Auto-detection failed');
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
        if (!targetEl.value && d.target_path) {
            targetEl.value = d.target_path;
            state.currentConfig.target_path = d.target_path;
        }
        if (!jfEl.value && d.media_path_in_jellyfin) {
            jfEl.value = d.media_path_in_jellyfin;
            state.currentConfig.media_path_in_jellyfin = d.media_path_in_jellyfin;
        }
        if (!hostEl.value && d.media_path_on_host) {
            hostEl.value = d.media_path_on_host;
            state.currentConfig.media_path_on_host = d.media_path_on_host;
        }
        if (d.target_path_in_jellyfin) {
            getEl('target_path_in_jellyfin').value = d.target_path_in_jellyfin;
            state.currentConfig.target_path_in_jellyfin = d.target_path_in_jellyfin;
        }
        showToast('Paths auto-filled - review and save.', 'success');
    } catch (_) { /* silently ignore */ }
}

export function initPathPicker() {
    // Path picker buttons wired via HTML onclicks
}
