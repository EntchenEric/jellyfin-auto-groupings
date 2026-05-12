// sync.js – Sync and preview sync logic

import { state } from '../core/state.js';
import { apiPost } from '../core/api.js';
import { showToast, getEl } from '../core/ui.js';

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
                entry.setAttribute('style', 'display:flex; justify-content:space-between; padding:0.3rem 0; border-bottom:1px solid var(--glass-border); font-size:0.85rem;');
                entry.innerHTML = `<span>${r.group}</span><span style="color:var(--accent-color); font-weight:600;">${r.links} links</span>`;
                if (r.error) entry.innerHTML += `<span style="color:var(--error-color); margin-left:0.5rem;">(${r.error})</span>`;
                resultsContent.appendChild(entry);
            });
            resultsPanel.style.display = 'block';
        }
    } else {
        showToast(result.message || 'Sync failed', 'error');
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
                groupCard.style.cssText = 'background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: 1rem;';

                const header = document.createElement('div');
                header.style.cssText = 'display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; border-bottom: 1px solid var(--glass-border); padding-bottom: 0.5rem;';

                const name = document.createElement('strong');
                name.textContent = groupResult.group;
                name.style.fontSize = '1.1rem';

                const badge = document.createElement('span');
                badge.textContent = `${groupResult.links} items`;
                badge.style.cssText = 'background: var(--accent-color); color: #fff; padding: 0.3rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; white-space: nowrap;';

                header.appendChild(name);
                header.appendChild(badge);
                groupCard.appendChild(header);

                if (groupResult.error) {
                    const err = document.createElement('div');
                    err.style.cssText = 'color: var(--error-color); font-size: 0.85rem; margin-top: 0.5rem;';
                    err.textContent = `Error: ${groupResult.error}`;
                    groupCard.appendChild(err);
                } else if (groupResult.items && groupResult.items.length > 0) {
                    const list = document.createElement('ul');
                    list.style.cssText = 'margin: 0; padding-left: 1.2rem; font-size: 0.85rem; color: var(--text-secondary); max-height: 150px; overflow-y: auto;';
                    groupResult.items.forEach((item) => {
                        const li = document.createElement('li');
                        li.textContent = item.Year ? `${item.Name} (${item.Year})` : item.Name;
                        list.appendChild(li);
                    });
                    groupCard.appendChild(list);
                } else {
                    const empty = document.createElement('div');
                    empty.style.cssText = 'color: var(--text-secondary); font-size: 0.85rem; font-style: italic;';
                    empty.textContent = 'No items found for this group.';
                    groupCard.appendChild(empty);
                }

                container.appendChild(groupCard);
            });
        } else {
            container.innerHTML = '<div style="color: var(--text-secondary); font-style: italic; padding: 1rem;">No groupings configured.</div>';
        }

        getEl('preview-sync-modal').style.display = 'flex';
    } else {
        showToast(result.message || 'Preview failed', 'error');
    }
}

export function showConfirmSyncDialog() {
    const groupCount = state.currentConfig.groups.length;
    if (groupCount === 0) {
        showToast('No groups to sync.', 'error');
        return;
    }
    const countEl = getEl('confirm-sync-group-count');
    if (countEl) countEl.textContent = groupCount;
    getEl('confirm-sync-modal').style.display = 'flex';
}

export function initSync() {
    // Buttons wired via app.js
}
