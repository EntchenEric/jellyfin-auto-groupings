// cleanup.js – Cleanup modal logic

import { getCleanupItems, performCleanup } from '../core/api.js';
import { showToast, showErrorDialog, getEl, showModal } from '../core/ui.js';

export async function openCleanupModal() {
    showModal('cleanup-modal');
    getEl('cleanup-loading').style.display = 'flex';
    getEl('cleanup-content').style.display = 'none';
    getEl('cleanup-error').style.display = 'none';

    try {
        const result = await getCleanupItems();

        if (result.status === 'success') {
            const listContainer = getEl('cleanup-list');
            listContainer.innerHTML = '';

            if (!result.items || result.items.length === 0) {
                const emptyDiv = document.createElement('div');
                emptyDiv.className = 'cleanup-empty';
                emptyDiv.textContent = 'No folders found in Target Directory.';
                listContainer.appendChild(emptyDiv);
            } else {
                result.items.forEach(item => {
                    const row = document.createElement('label');
                    row.className = 'cleanup-item';

                    const left = document.createElement('div');
                    left.className = 'cleanup-item-left';

                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.value = item.name;
                    checkbox.checked = true;
                    checkbox.className = 'cleanup-item-checkbox';
                    checkbox.onchange = updateCleanupCount;

                    const nameSpan = document.createElement('span');
                    nameSpan.className = 'cleanup-item-name';
                    nameSpan.textContent = item.name;

                    const badge = document.createElement('span');
                    if (item.is_configured) {
                        badge.textContent = 'Configured';
                        badge.className = 'cleanup-badge-configured';
                    } else {
                        badge.textContent = 'Unconfigured';
                        badge.className = 'cleanup-badge-unconfigured';
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
    btn.innerHTML = '<span class="loading-spinner cleanup-spinner-inline"></span>Deleting...';
    btn.disabled = true;

    try {
        const result = await performCleanup(folders);

        btn.innerHTML = 'Delete Selected <span id="cleanup-count"></span>';
        btn.disabled = false;
        updateCleanupCount();

        if (result.status === 'success' || result.status === 'partial_success') {
            showToast(`Successfully deleted ${result.deleted} folder(s).${result.errors ? ' Errors: ' + result.errors.join(', ') : ''}`, result.status === 'partial_success' ? 'warning' : 'success');
            // Refresh the modal list instead of closing
            openCleanupModal();
        } else {
            showErrorDialog('Error deleting folders: ' + result.message);
            updateCleanupCount();
        }
    } catch (err) {
        btn.innerHTML = 'Delete Selected <span id="cleanup-count"></span>';
        btn.disabled = false;
        updateCleanupCount();
        showErrorDialog('Network error while deleting folders.');
    }
}

/**
 * Controls this module has already bound, so repeated init calls do not stack
 * duplicate listeners.
 * @type {WeakSet<Element>}
 */
const boundCleanupControls = new WeakSet();

export function initCleanup() {
    // `execCleanup()` was exported but never called: the modal's Delete button
    // lost its inline `onclick` when the frontend was modularised, so the only
    // action in the Clean Up Folders dialog did nothing at all. Bootstrap calls
    // this, which is where the cover and folder-picker dialogs wire theirs.
    const confirmBtn = getEl('confirm-cleanup-btn');
    if (confirmBtn && !boundCleanupControls.has(confirmBtn)) {
        boundCleanupControls.add(confirmBtn);
        confirmBtn.addEventListener('click', () => {
            void execCleanup();
        });
    }
}
