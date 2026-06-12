// api.js – Centralised API client with error handling

import { showToast, showErrorDialog } from './ui.js';

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
            showErrorDialog('Request timed out — server did not respond in time');
        } else if (err instanceof ApiError) {
            showErrorDialog(err.message);
        } else if (err instanceof TypeError) {
            showErrorDialog('Network error — check your connection');
        } else {
            showErrorDialog('Unexpected error occurred');
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
export const previewGroup = (type, value, watch_state) =>
    apiPost('/api/grouping/preview', { type, value, watch_state });
export const uploadCover = (groupName, image) =>
    apiPost('/api/upload_cover', { group_name: groupName, image });
export const getCleanupItems = () => apiGet('/api/cleanup');
export const performCleanup = (folders) => apiPost('/api/cleanup', { folders });
export const autoDetectPaths = () => apiPost('/api/jellyfin/auto-detect-paths');
export const browsePath = (path) => {
    const url = new URL('/api/browse', window.location.origin);
    url.searchParams.set('path', path);
    return apiGet(url.toString());
};
