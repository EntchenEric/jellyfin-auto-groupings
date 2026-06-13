// sync.js – Sync and preview sync logic

import { state } from '../core/state.js';
import { apiPost, previewSync } from '../core/api.js';
import { showToast, showErrorDialog, getEl, showModal } from '../core/ui.js';

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

                const groupSpan = document.createElement('span');
                groupSpan.textContent = r.group;
                entry.appendChild(groupSpan);

                const linksSpan = document.createElement('span');
                linksSpan.style.cssText = 'color:var(--accent-color); font-weight:600;';
                linksSpan.textContent = `${r.links} links`;
                entry.appendChild(linksSpan);

                if (r.error) {
                    const errSpan = document.createElement('span');
                    errSpan.style.cssText = 'color:var(--error-color); margin-left:0.5rem;';
                    errSpan.textContent = `(${r.error})`;
                    entry.appendChild(errSpan);
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
        showErrorDialog(result.message || 'Preview failed');
    }
}

export async function showConfirmSyncDialog() {
    const groupCount = state.currentConfig.groups.length;
    if (groupCount === 0) {
        showErrorDialog('No groups to sync.');
        return;
    }
    const countEl = getEl('confirm-sync-group-count');
    const itemCountEl = getEl('confirm-sync-item-count');
    if (countEl) countEl.textContent = groupCount;
    if (itemCountEl) itemCountEl.textContent = '…';
    showModal('confirm-sync-modal');

    try {
        const result = await previewSync(true);
        if (result.status === 'success' && result.results) {
            const totalLinks = result.results.reduce((acc, r) => acc + (r.links || 0), 0);
            if (itemCountEl) itemCountEl.textContent = totalLinks;
        } else if (itemCountEl) {
            itemCountEl.textContent = groupCount;
        }
    } catch {
        if (itemCountEl) itemCountEl.textContent = groupCount;
    }
}

export function initSync() {
    // Buttons wired via app.js
}
