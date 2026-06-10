// sync.js – Sync and preview sync logic

import { state } from '../core/state.js';
import { apiPost } from '../core/api.js';
import { showToast, showErrorDialog, getEl } from '../core/ui.js';

export async function syncAll() {
    const result = await apiPost('/api/sync');
    if (result.status === 'success') {
        const totalLinks = result.results.reduce((acc, r) => acc + r.links, 0);
        showToast(`Sync complete! Created ${totalLinks} symbolic links.`, 'success');

        const resultsPanel = getEl('sync-results-panel');
        const resultsContent = getEl('sync-results-content');
        if (resultsPanel && resultsContent && result.results) {
            resultsContent.innerHTML = '';
            result.results.forEach(r => {
                const entry = document.createElement('div');
                entry.className = 'sync-result-entry';
                const groupSpan = document.createElement('span');
                groupSpan.textContent = r.group;
                entry.appendChild(groupSpan);
                const linksSpan = document.createElement('span');
                linksSpan.className = 'sync-result-links';
                linksSpan.textContent = `${r.links} links`;
                entry.appendChild(linksSpan);
                if (r.error) {
                    const errorSpan = document.createElement('span');
                    errorSpan.className = 'sync-result-error';
                    errorSpan.textContent = `(${r.error})`;
                    entry.appendChild(errorSpan);
                }
                resultsContent.appendChild(entry);
            });
            resultsPanel.style.display = 'block';
        }
    } else {
        showErrorDialog(result.message || 'Sync failed');
    }
}

export async function previewSyncAll() {
    const result = await apiPost('/api/sync/preview_all');
    if (result.status === 'success') {
        const container = getEl('preview-sync-results');
        container.innerHTML = '';

        if (result.results && result.results.length > 0) {
            result.results.forEach(groupResult => {
                const groupCard = document.createElement('div');
                groupCard.className = 'sync-preview-card';

                const header = document.createElement('div');
                header.className = 'sync-preview-header';

                const name = document.createElement('strong');
                name.className = 'sync-preview-name';
                name.textContent = groupResult.group;

                const badge = document.createElement('span');
                badge.className = 'sync-preview-badge';
                badge.textContent = `${groupResult.links} items`;

                header.appendChild(name);
                header.appendChild(badge);
                groupCard.appendChild(header);

                if (groupResult.error) {
                    const err = document.createElement('div');
                    err.className = 'sync-preview-error';
                    err.textContent = `Error: ${groupResult.error}`;
                    groupCard.appendChild(err);
                } else if (groupResult.items && groupResult.items.length > 0) {
                    const list = document.createElement('ul');
                    list.className = 'sync-preview-list';
                    groupResult.items.forEach((item) => {
                        const li = document.createElement('li');
                        li.textContent = item.Year ? `${item.Name} (${item.Year})` : item.Name;
                        list.appendChild(li);
                    });
                    groupCard.appendChild(list);
                } else {
                    const empty = document.createElement('div');
                    empty.className = 'sync-preview-empty';
                    empty.textContent = 'No items found for this group.';
                    groupCard.appendChild(empty);
                }

                container.appendChild(groupCard);
            });
        } else {
            container.innerHTML = '<div class="sync-preview-empty">No groupings configured.</div>';
        }

        getEl('preview-sync-modal').style.display = 'flex';
    } else {
        showErrorDialog(result.message || 'Preview failed');
    }
}

export function showConfirmSyncDialog() {
    const groupCount = state.currentConfig.groups.length;
    if (groupCount === 0) {
        showErrorDialog('No groups to sync.');
        return;
    }
    const countEl = getEl('confirm-sync-group-count');
    if (countEl) countEl.textContent = groupCount;
    getEl('confirm-sync-modal').style.display = 'flex';
}

export function initSync() {
    // Buttons wired via app.js
}
