// groupings.js – CRUD operations for groupings

import { state, sourceOptions, sortLabels } from '../core/state.js';
import { saveConfig } from '../core/api.js';
import { showToast, getEl, showErrorDialog } from '../core/ui.js';
import { updateSourceTypeOptions, updateSourceValueUI, getFilterValue } from './metadata.js';
import { openCoverGenerator } from './cover-generator.js';

let _searchFilter = '';

export function renderGroups() {
    const groupsList = getEl('groups-list');
    groupsList.innerHTML = '';

    if (!state.currentConfig.groups || state.currentConfig.groups.length === 0) {
        groupsList.innerHTML = '<div class="groups-empty-state"><p class="groups-empty-icon">📁</p><p class="groups-empty-title">No groupings defined yet</p><p class="groups-empty-desc">Create your first grouping above, or use the <strong>Wizard</strong> for a guided setup.</p></div>';
        updateGlobalSyncExclusionsUI();
        updateGroupCount();
        return;
    }

    updateGlobalSyncExclusionsUI();
    updateGroupCount();

    let visibleCount = 0;
    const filter = _searchFilter.toLowerCase().trim();

    state.currentConfig.groups.forEach((group, index) => {
        const groupName = (group.name || '').toLowerCase();
        if (filter && !groupName.includes(filter)) {
            return;
        }
        visibleCount++;

        const card = document.createElement('div');
        card.className = 'group-card';

        const catLabel = group.source_category === 'external' ? 'External' : 'Jellyfin';
        const typeLabel = sourceOptions[group.source_category]?.find(opt => opt.value === group.source_type)?.label || group.source_type;

        const infoDiv = document.createElement('div');
        infoDiv.className = 'group-info';

        const h4 = document.createElement('h4');
        h4.textContent = group.name || 'Unnamed Group';
        if (group.sort_order) {
            const badge = document.createElement('span');
            badge.className = 'badge badge-sort';
            badge.textContent = sortLabels[group.sort_order] || group.sort_order;
            h4.appendChild(badge);
        }
        if (group.seasonal_enabled) {
            const badge = document.createElement('span');
            badge.className = 'badge badge-seasonal';
            badge.textContent = `${group.seasonal_start} to ${group.seasonal_end}`;
            h4.appendChild(badge);
        }
        if (group.create_as_collection) {
            const badge = document.createElement('span');
            badge.className = 'badge badge-collection';
            badge.textContent = 'Collection';
            h4.appendChild(badge);
        }
        infoDiv.appendChild(h4);

        const metaDiv = document.createElement('div');
        metaDiv.className = 'group-meta';
        const catSpan = document.createElement('span');
        catSpan.className = 'group-category-label';
        catSpan.textContent = catLabel;
        metaDiv.appendChild(catSpan);
        metaDiv.appendChild(document.createTextNode(` • ${typeLabel}: ${group.source_value || ''}`));
        infoDiv.appendChild(metaDiv);
        card.appendChild(infoDiv);

        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'group-actions';

        const coverBtn = document.createElement('button');
        coverBtn.className = 'secondary-btn group-action-btn group-action-btn--cover';
        coverBtn.title = 'Group Cover';
        coverBtn.textContent = 'Cover';
        coverBtn.onclick = () => openCoverGenerator(index);
        actionsDiv.appendChild(coverBtn);

        const editBtn = document.createElement('button');
        editBtn.className = 'secondary-btn group-action-btn group-action-btn--edit';
        editBtn.title = 'Edit Group';
        editBtn.textContent = 'Edit';
        editBtn.onclick = () => editGroup(index);
        actionsDiv.appendChild(editBtn);

        const delBtn = document.createElement('button');
        delBtn.className = 'delete-btn';
        delBtn.title = 'Remove Group';
        delBtn.innerHTML = '<svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="icon-delete"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg>';
        delBtn.appendChild(document.createTextNode(' Remove'));
        delBtn.onclick = () => deleteGroup(index);
        actionsDiv.appendChild(delBtn);

        card.appendChild(actionsDiv);
        groupsList.appendChild(card);
    });

    if (filter && visibleCount === 0) {
        const emptyMsg = document.createElement('p');
        emptyMsg.style.cssText = 'color: var(--text-secondary); text-align: center; font-style: italic; margin-top: 2rem;';
        emptyMsg.textContent = `No groups match "${_searchFilter}".`;
        groupsList.appendChild(emptyMsg);
    }

    updateGroupCount(visibleCount);
}

function updateGroupCount(visibleCount) {
    const badge = getEl('groups-count-badge');
    if (!badge) return;
    const total = state.currentConfig.groups?.length || 0;
    if (visibleCount !== undefined) {
        badge.textContent = visibleCount === total ? `${total}` : `${visibleCount}/${total}`;
    } else {
        badge.textContent = `${total}`;
    }
}

export function initGroupSearch() {
    const searchInput = getEl('groups-search');
    if (!searchInput) return;
    searchInput.addEventListener('input', () => {
        _searchFilter = searchInput.value;
        renderGroups();
    });
}

export function editGroup(index) {
    state.editingIndex = index;
    const group = state.currentConfig.groups[index];

    getEl('group_name').value = group.name;
    getEl('source_category').value = group.source_category || 'jellyfin';
    updateSourceTypeOptions();
    getEl('source_type').value = group.source_type;
    const hasSortOrder = !!(group.sort_order);
    getEl('sort_order_enabled').checked = hasSortOrder;
    getEl('sort_order_panel').style.display = hasSortOrder ? 'block' : 'none';
    getEl('sort_order').value = group.sort_order || '';

    const hasSchedule = !!(group.schedule_enabled);
    getEl('schedule_enabled').checked = hasSchedule;
    getEl('group_scheduler_panel').style.display = hasSchedule ? 'block' : 'none';
    getEl('group_schedule').value = group.schedule || '';

    const isSeasonal = !!(group.seasonal_enabled);
    getEl('seasonal_enabled').checked = isSeasonal;
    getEl('seasonal_panel').style.display = isSeasonal ? 'block' : 'none';
    if (group.seasonal_start) {
        const [sm, sd] = group.seasonal_start.split('-');
        getEl('seasonal_start_month').value = sm;
        getEl('seasonal_start_day').value = sd;
    }
    if (group.seasonal_end) {
        const [em, ed] = group.seasonal_end.split('-');
        getEl('seasonal_end_month').value = em;
        getEl('seasonal_end_day').value = ed;
    }
    getEl('watch_state').value = group.watch_state || '';
    getEl('create_as_collection').checked = !!group.create_as_collection;

    updateSourceValueUI(group.source_value);

    getEl('group-form-title').textContent = 'Edit Grouping';
    getEl('add-group-btn').textContent = 'Update Grouping';
    getEl('cancel-edit-btn').style.display = 'block';

    getEl('group-form').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

export function cancelEdit() {
    state.editingIndex = -1;
    getEl('group-form').reset();
    resetFormUI();
}

export function resetFormUI() {
    getEl('group-form-title').textContent = 'Create New Grouping';
    getEl('add-group-btn').textContent = 'Add Grouping';
    getEl('cancel-edit-btn').style.display = 'none';
    getEl('sort_order_enabled').checked = false;
    getEl('sort_order_panel').style.display = 'none';
    getEl('schedule_enabled').checked = false;
    getEl('group_scheduler_panel').style.display = 'none';
    getEl('seasonal_enabled').checked = false;
    getEl('seasonal_panel').style.display = 'none';
    getEl('watch_state').value = '';
    getEl('create_as_collection').checked = false;
    updateSourceTypeOptions();
}

export async function deleteGroup(index) {
    if (typeof index !== 'number' || index < 0 || index >= state.currentConfig.groups.length) {
        showToast('Invalid group index', 'error');
        return;
    }
    if (!confirm('Permanently remove this grouping?')) return;
    const groupName = state.currentConfig.groups[index]?.name;
    if (state.editingIndex === index) cancelEdit();
    const removedGroup = state.currentConfig.groups.splice(index, 1)[0];
    try {
        await saveConfig(state.currentConfig);
    } catch (e) {
        // Re-insert at the original position. If the array was modified
        // between the splice and the save failure, append at the end.
        if (index <= state.currentConfig.groups.length) {
            state.currentConfig.groups.splice(index, 0, removedGroup);
        } else {
            state.currentConfig.groups.push(removedGroup);
        }
        showToast('Failed to save after deleting group', 'error');
        return;
    }
    renderGroups();

    if (groupName) {
        try {
            await fetch('/api/cleanup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folders: [groupName] })
            });
        } catch (e) {
            showToast('Failed to clean up folder from disk: ' + e.message, 'error');
        }
    }
}

export async function clearAllGroups() {
    if (!confirm('Are you sure you want to remove ALL groupings? This cannot be undone.')) return;
    const groupNames = state.currentConfig.groups.map(g => g.name).filter(Boolean);
    const backup = state.currentConfig.groups;
    state.currentConfig.groups = [];
    try {
        await saveConfig(state.currentConfig);
    } catch (e) {
        state.currentConfig.groups = backup;
        showToast('Failed to save after clearing groups', 'error');
        return;
    }
    renderGroups();

    if (groupNames.length > 0) {
        try {
            await fetch('/api/cleanup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folders: groupNames })
            });
        } catch (e) {
            showToast('Failed to clean up folders from disk: ' + e.message, 'error');
        }
    }
}

export function toggleSortOrder(checkbox) {
    getEl('sort_order_panel').style.display = checkbox.checked ? 'block' : 'none';
}

export function toggleSeasonal(checkbox) {
    getEl('seasonal_panel').style.display = checkbox.checked ? 'block' : 'none';
}

export function toggleGroupScheduler(cb) {
    const panel = getEl('group_scheduler_panel');
    if (panel) panel.style.display = cb.checked ? 'block' : 'none';
}

export function populateSeasonalDays() {
    const startDaySelect = getEl('seasonal_start_day');
    const endDaySelect = getEl('seasonal_end_day');
    [startDaySelect, endDaySelect].forEach(select => {
        select.innerHTML = '';
        for (let i = 1; i <= 31; i++) {
            const opt = document.createElement('option');
            opt.value = i.toString().padStart(2, '0');
            opt.textContent = i;
            select.appendChild(opt);
        }
    });
}

export function updateGlobalSyncExclusionsUI() {
    const container = getEl('global_sync_exclusions');
    if (!container) return;
    container.innerHTML = '';

    if (!state.currentConfig.scheduler) {
        state.currentConfig.scheduler = { global_enabled: false, global_schedule: '', global_exclude_ids: [] };
    }
    if (!state.currentConfig.scheduler.global_exclude_ids) {
        state.currentConfig.scheduler.global_exclude_ids = [];
    }

    const validGroupNames = state.currentConfig.groups.map(g => g.name).filter(Boolean);
    state.currentConfig.scheduler.global_exclude_ids = state.currentConfig.scheduler.global_exclude_ids.filter(id => validGroupNames.includes(id));

    const excludedIds = state.currentConfig.scheduler.global_exclude_ids;

    state.currentConfig.groups.forEach((group) => {
        if (!group.name) return;
        const label = document.createElement('label');
        label.className = 'exclusion-checkbox-label';

        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = excludedIds.includes(group.name);
        cb.onchange = (e) => {
            const idx = excludedIds.indexOf(group.name);
            if (e.target.checked) {
                if (idx === -1) excludedIds.push(group.name);
            } else {
                if (idx !== -1) excludedIds.splice(idx, 1);
            }
        };

        label.appendChild(cb);
        label.appendChild(document.createTextNode(group.name));
        container.appendChild(label);
    });

    if (state.currentConfig.groups.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.8rem; font-style: italic;">No groups defined yet.</p>';
    }
}