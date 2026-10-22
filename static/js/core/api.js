// api.js – Centralised API client with error handling

import { showToast, showErrorDialog } from './ui.js';

const DEFAULT_TIMEOUT_MS = 60000;
const AUTH_STORAGE_KEY = 'jfg_app_password';

class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
        this.name = 'ApiError';
    }
}

export function setAppPassword(password) {
    if (password) sessionStorage.setItem(AUTH_STORAGE_KEY, password);
    else sessionStorage.removeItem(AUTH_STORAGE_KEY);
}

/**
 * Base64-encode *text* as UTF-8 for a Basic auth header.
 *
 * `btoa()` only accepts Latin-1. For a password like "pässwort" it returned
 * the Latin-1 bytes, which the server decodes as UTF-8 and therefore never
 * matches; for anything outside Latin-1 (Cyrillic, CJK, emoji) it throws
 * `InvalidCharacterError` and the request is never sent. Encoding to UTF-8
 * bytes first matches how Flask/Werkzeug decode the header.
 *
 * @param {string} text
 * @returns {string} Base64 of the UTF-8 bytes.
 */
export function base64Utf8(text) {
    const bytes = new TextEncoder().encode(text);
    let binary = '';
    for (const byte of bytes) {
        binary += String.fromCharCode(byte);
    }
    return btoa(binary);
}

function authHeaders(extra = {}) {
    const headers = { ...extra };
    const pw = sessionStorage.getItem(AUTH_STORAGE_KEY);
    if (pw) {
        headers.Authorization = `Basic ${base64Utf8(`user:${pw}`)}`;
    }
    return headers;
}

async function apiRequest(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    // Internal flags drive retry/silent behaviour and must not be handed to
    // fetch() as request options.
    const { _silent, _authRetried, ...fetchOptions } = options;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(url, {
            ...fetchOptions,
            credentials: 'same-origin',
            headers: authHeaders(fetchOptions.headers),
            signal: controller.signal
        });
        if (res.status === 401 && !_authRetried) {
            const pw = prompt('Enter app password:');
            if (pw) {
                setAppPassword(pw);
                return apiRequest(url, { ...options, _authRetried: true }, timeoutMs);
            }
            throw new ApiError(401, 'Authentication required');
        }
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new ApiError(res.status, body.message || 'Request failed');
        }
        return res.json();
    } catch (err) {
        // Callers that render the failure inline (the folder picker, which is
        // itself a modal) pass _silent so an error dialog does not stack on
        // top of the UI they are about to update.
        if (!_silent) {
            if (err.name === 'AbortError') {
                showErrorDialog('Request timed out — server did not respond in time');
            } else if (err instanceof ApiError) {
                showErrorDialog(err.message);
            } else if (err instanceof TypeError) {
                showErrorDialog('Network error — check your connection');
            } else {
                showErrorDialog('Unexpected error occurred');
            }
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

export function apiGet(url, timeoutMs) {
    return apiRequest(url, {}, timeoutMs);
}

/**
 * GET a URL, letting the caller render any failure itself.
 * @param {string} url
 * @param {number} [timeoutMs]
 * @returns {Promise<object>}
 */
export function apiGetSilent(url, timeoutMs) {
    return apiRequest(url, { _silent: true }, timeoutMs);
}

export function apiPost(url, body, timeoutMs) {
    const opts = {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
    };
    // Only set body when provided — JSON.stringify(undefined) returns undefined,
    // which omits the body entirely rather than sending "undefined".
    if (body !== undefined) {
        opts.body = JSON.stringify(body);
    }
    return apiRequest(url, opts, timeoutMs);
}

// Convenience wrappers
export const loadConfig = () => apiGet('/api/config');
export const saveConfig = (cfg) => apiPost('/api/config', cfg);
export const testServer = (url, key) => apiPost('/api/test-server', { jellyfin_url: url, api_key: key });
export const fetchMetadata = () => apiGet('/api/jellyfin/metadata');
export const fetchUsers = () => apiGet('/api/jellyfin/users');
export const runSync = () => apiPost('/api/sync');
export const previewSync = () => apiPost('/api/sync/preview_all');
export const previewGroup = (type, value, watch_state, item_type) =>
    apiPost('/api/grouping/preview', { type, value, watch_state, item_type });
export const uploadCover = (groupName, image) =>
    apiPost('/api/upload_cover', { group_name: groupName, image });
export const getCleanupItems = () => apiGet('/api/cleanup');
export const performCleanup = (folders) => apiPost('/api/cleanup', { folders });
export const autoDetectPaths = () => apiPost('/api/jellyfin/auto-detect-paths');
export const browsePath = (path) => {
    const url = new URL('/api/browse', window.location.origin);
    url.searchParams.set('path', path);
    // Silent: the folder picker reports the error in its own body.
    return apiGetSilent(url.toString());
};
