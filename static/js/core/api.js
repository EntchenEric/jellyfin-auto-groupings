// api.js – Centralised API client with error handling

import { showToast } from './ui.js';

const DEFAULT_TIMEOUT_MS = 60000;

class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
        this.name = 'ApiError';
    }
}

async function apiRequest(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new ApiError(res.status, body.message || 'Request failed');
        }
        return res.json();
    } catch (err) {
        if (err.name === 'AbortError') {
            showToast('Request timed out — server did not respond in time', 'error');
        } else if (err instanceof ApiError) {
            showToast(err.message, 'error');
        } else if (err instanceof TypeError) {
            showToast('Network error — check your connection', 'error');
        } else {
            showToast('Unexpected error occurred', 'error');
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

export function apiGet(url, timeoutMs) {
    return apiRequest(url, {}, timeoutMs);
}

export function apiPost(url, body, timeoutMs) {
    return apiRequest(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify(body)
    }, timeoutMs);
}

// Convenience wrappers
export const loadConfig = () => apiGet('/api/config');
export const saveConfig = (cfg) => apiPost('/api/config', cfg);
export const testServer = (url, key) => apiPost('/api/test-server', { jellyfin_url: url, api_key: key });
export const fetchMetadata = () => apiGet('/api/jellyfin/metadata');
export const fetchUsers = () => apiGet('/api/jellyfin/users');
export const runSync = () => apiPost('/api/sync');
export const previewSync = () => apiPost('/api/sync/preview_all');
export const previewGroup = (type, value, watch_state) =>
    apiPost('/api/grouping/preview', { type, value, watch_state });
export const uploadCover = (groupName, image) =>
    apiPost('/api/upload_cover', { group_name: groupName, image });
export const getCleanupItems = () => apiGet('/api/cleanup');
export const performCleanup = (folders) => apiPost('/api/cleanup', { folders });
export const autoDetectPaths = () => apiPost('/api/jellyfin/auto-detect-paths');
export const browsePath = (path) => apiGet('/api/browse?path=' + encodeURIComponent(path));
