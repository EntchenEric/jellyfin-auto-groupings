// sync.js – Sync and preview sync logic

import { state } from '../core/state.js';
import { runSync, previewSync } from '../core/api.js';
import { showToast, showErrorDialog, showModal, getEl } from '../core/ui.js';

export async function syncAll() {
    const result = await runSync();
    if (result.status === 'success') {
        // A missing or non-array `results` would throw on `.reduce` and leave
        // the button spinning with no explanation; treat it as an empty run.
        const results = Array.isArray(result.results) ? result.results : [];
        const totalLinks = results.reduce(
            (acc, r) => acc + (Number(r && r.links) || 0),
            0,
        );
        // Per-group failures are reported in the results panel, but the toast
        // used to say "Sync complete!" in green whatever happened, so a run
        // where every group errored looked like a success. Mirror cleanup.js:
        // name the failure count and use the warning colour.
        const failed = results.filter(r => r && r.error).length;
        if (failed > 0) {
            const noun = failed === 1 ? 'group' : 'groups';
            showToast(
                `Sync finished with ${failed} ${noun} failed — ` +
                `created ${totalLinks} symbolic links.`,
                'warning',
            );
        } else {
            showToast(
                `Sync complete! Created ${totalLinks} symbolic links.`,
                'success',
            );
        }

        const resultsPanel = getEl('sync-results-panel');
        const resultsContent = getEl('sync-results-content');
        if (resultsPanel && resultsContent && results.length > 0) {
            resultsContent.innerHTML = '';
            results.forEach(r => {
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
    const result = await previewSync();
    if (result.status === 'success') {
        const container = getEl('preview-sync-results');
        if (!container) return;
        container.innerHTML = '';

        // Previously a non-array `results` fell through to the "no groupings"
        // branch, telling the user their config was empty after a run that
        // had returned something else entirely.
        const results = Array.isArray(result.results) ? result.results : [];
        if (results.length > 0) {
            results.forEach(groupResult => {
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
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'sync-preview-empty';
            // Only an array answers the question the user asked. Anything else
            // is a malformed response, and saying "No groupings configured"
            // there sent them looking for a config problem that does not exist.
            emptyDiv.textContent = Array.isArray(result.results)
                ? 'No groupings configured.'
                : 'The preview response was malformed. Please try again.';
            container.appendChild(emptyDiv);
        }

        showModal('preview-sync-modal');
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
    // "1 groupings" reads as a bug to the user; the noun follows the count.
    const nounEl = getEl('confirm-sync-group-noun');
    if (nounEl) nounEl.textContent = groupCount === 1 ? 'grouping' : 'groupings';
    showModal('confirm-sync-modal');
}

export function initSync() {
    // Buttons wired via app.js
}
