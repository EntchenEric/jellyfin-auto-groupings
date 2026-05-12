// api.js – Centralised API client with error handling

import { showToast } from './ui.js';

class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
        this.name = 'ApiError';
    }
}

async function apiRequest(url, options = {}) {
    try {
        const res = await fetch(url, options);
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new ApiError(res.status, body.message || 'Request failed');
        }
        return res.json();
    } catch (err) {
        if (err instanceof ApiError) {
            showToast(err.message, 'error');
        } else if (err instanceof TypeError) {
            showToast('Network error — check your connection', 'error');
        } else {
            showToast('Unexpected error occurred', 'error');
        }
        throw err;
    }
}

export function apiGet(url) {
    return apiRequest(url);
}

export function apiPost(url, body) {
    return apiRequest(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
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
