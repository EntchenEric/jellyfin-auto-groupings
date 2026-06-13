// api.js – Centralised API client with error handling

import { showToast, showErrorDialog } from './ui.js';

const DEFAULT_TIMEOUT_MS = 60000;

let _basicAuthUser = '';
let _basicAuthPass = '';

class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
        this.name = 'ApiError';
    }
}

export function setBasicAuthCredentials(user, pass) {
    _basicAuthUser = user || '';
    _basicAuthPass = pass || '';
}

export async function loginWithPassword(password) {
    setBasicAuthCredentials('user', password);
    return apiGet('/api/config');
}

function buildHeaders(extra = {}) {
    const headers = { ...extra };
    if (_basicAuthPass) {
        headers['Authorization'] = 'Basic ' + btoa(`${_basicAuthUser}:${_basicAuthPass}`);
    }
    return headers;
}

async function apiRequest(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS, silent = false) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(url, {
            ...options,
            credentials: 'same-origin',
            signal: controller.signal,
            headers: buildHeaders(options.headers || {})
        });
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new ApiError(res.status, body.message || 'Request failed');
        }
        return res.json();
    } catch (err) {
        if (!silent) {
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

export function apiGet(url, timeoutMs, silent) {
    return apiRequest(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }, timeoutMs, silent);
}

export function apiPost(url, body, timeoutMs, silent) {
    return apiRequest(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify(body)
    }, timeoutMs, silent);
}

export function apiDelete(url, timeoutMs) {
    return apiRequest(url, {
        method: 'DELETE',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }, timeoutMs);
}

// Convenience wrappers
export const loadConfig = () => apiGet('/api/config');
export const saveConfig = (cfg) => apiPost('/api/config', cfg);
export const testServer = (url, key) => apiPost('/api/test-server', { jellyfin_url: url, api_key: key });
export const fetchMetadata = () => apiGet('/api/jellyfin/metadata');
export const fetchUsers = () => apiGet('/api/jellyfin/users');
export const runSync = () => apiPost('/api/sync');
export const previewSync = (silent = false) => apiPost('/api/sync/preview_all', {}, DEFAULT_TIMEOUT_MS, silent);
export const previewGroup = (type, value, watch_state) =>
    apiPost('/api/grouping/preview', { type, value, watch_state });
export const uploadCover = (groupName, image) =>
    apiPost('/api/upload_cover', { group_name: groupName, image });
export const getCleanupItems = () => apiGet('/api/cleanup');
export const performCleanup = (folders) => apiPost('/api/cleanup', { folders });
export const autoDetectPaths = () => apiPost('/api/jellyfin/auto-detect-paths');
export const browsePath = (path) => apiGet('/api/browse?path=' + encodeURIComponent(path));
