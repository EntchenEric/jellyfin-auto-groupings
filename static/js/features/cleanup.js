// cleanup.js – Cleanup modal logic

import { showToast, getEl } from '../core/ui.js';

export async function openCleanupModal() {
    getEl('cleanup-modal').style.display = 'flex';
    getEl('cleanup-loading').style.display = 'flex';
    getEl('cleanup-content').style.display = 'none';
    getEl('cleanup-error').style.display = 'none';

    try {
        const response = await fetch('/api/cleanup');
        const result = await response.json();

        if (result.status === 'success') {
            const listContainer = getEl('cleanup-list');
            listContainer.innerHTML = '';

            if (!result.items || result.items.length === 0) {
                listContainer.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-secondary); font-style: italic;">No folders found in Target Directory.</div>';
            } else {
                result.items.forEach(item => {
                    const row = document.createElement('label');
                    row.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 0.8rem; border-bottom: 1px solid var(--glass-border); cursor: pointer; transition: background 0.15s; text-transform: none; font-weight: 400;';
                    row.onmouseover = () => row.style.background = 'rgba(255,255,255,0.05)';
                    row.onmouseout = () => row.style.background = 'transparent';

                    const left = document.createElement('div');
                    left.style.display = 'flex';
                    left.style.alignItems = 'center';
                    left.style.gap = '1rem';

                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.value = item.name;
                    checkbox.checked = true;
                    checkbox.style.cssText = 'width: 16px; height: 16px; accent-color: var(--error-color);';
                    checkbox.onchange = updateCleanupCount;

                    const nameSpan = document.createElement('span');
                    nameSpan.textContent = item.name;
                    nameSpan.style.color = 'var(--text-primary)';
                    nameSpan.style.fontFamily = 'monospace';

                    const badge = document.createElement('span');
                    if (item.is_configured) {
                        badge.textContent = 'Configured';
                        badge.style.cssText = 'font-size: 0.7rem; background: rgba(34, 197, 94, 0.2); color: #4ade80; padding: 0.2rem 0.5rem; border-radius: 4px;';
                    } else {
                        badge.textContent = 'Unconfigured';
                        badge.style.cssText = 'font-size: 0.7rem; background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 0.2rem 0.5rem; border-radius: 4px;';
                    }

                    left.appendChild(checkbox);
                    left.appendChild(nameSpan);
                    row.appendChild(left);
                    row.appendChild(badge);
                    listContainer.appendChild(row);
                });
            }

            getEl('cleanup-loading').style.display = 'none';
            getEl('cleanup-content').style.display = 'flex';
            updateCleanupCount();
        } else {
            getEl('cleanup-loading').style.display = 'none';
            getEl('cleanup-error').textContent = result.message || 'Failed to load folders';
            getEl('cleanup-error').style.display = 'block';
        }
    } catch (err) {
        getEl('cleanup-loading').style.display = 'none';
        getEl('cleanup-error').textContent = 'Network error fetching folders';
        getEl('cleanup-error').style.display = 'block';
    }
}

export function updateCleanupCount() {
    const checked = document.querySelectorAll('#cleanup-list input[type="checkbox"]:checked').length;
    const countSpan = getEl('cleanup-count');
    countSpan.textContent = checked > 0 ? `(${checked})` : '';
    getEl('confirm-cleanup-btn').disabled = checked === 0;
    getEl('confirm-cleanup-btn').style.opacity = checked === 0 ? '0.5' : '1';
}

export async function execCleanup() {
    const checkboxes = document.querySelectorAll('#cleanup-list input[type="checkbox"]:checked');
    const folders = Array.from(checkboxes).map(cb => cb.value);

    if (folders.length === 0) return;

    const btn = getEl('confirm-cleanup-btn');
    btn.innerHTML = '<span class="loading-spinner" style="display:inline-block; border-top-color:#fff; width:16px; height:16px;border-width:2px;margin-right:8px;"></span>Deleting...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/cleanup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folders })
        });
        const result = await response.json();

        btn.innerHTML = 'Delete Selected <span id="cleanup-count"></span>';
        btn.disabled = false;
        updateCleanupCount();

        if (result.status === 'success' || result.status === 'partial_success') {
            getEl('cleanup-modal').style.display = 'none';
            alert(`Successfully deleted ${result.deleted} folder(s). ${result.errors ? 'Errors: ' + result.errors.join(', ') : ''}`);
        } else {
            alert('Error deleting folders: ' + result.message);
        }
    } catch (err) {
        btn.innerHTML = 'Delete Selected <span id="cleanup-count"></span>';
        btn.disabled = false;
        updateCleanupCount();
        alert('Network error while deleting folders.');
    }
}

export function initCleanup() {
    // Cleanup button wired in topbar HTML
}
