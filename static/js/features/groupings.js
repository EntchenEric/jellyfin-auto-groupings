// groupings.js – CRUD operations for groupings

import { state, sourceOptions, sortLabels, resolveSourceCategory } from '../core/state.js';
import { saveConfig, apiPost } from '../core/api.js';
import { showToast, getEl, showErrorDialog, showConfirmDialog } from '../core/ui.js';
import { updateSourceTypeOptions, updateSourceValueUI, getFilterValue } from './metadata.js';
import { openCoverGenerator } from './cover-generator.js';

let _searchFilter = '';

/**
 * Text to show for a group's ``name``.
 *
 * ``config.json`` is user-editable and an import can come from any source, so
 * a group can carry ``"name": 42``, an object, or an array. `renderGroups()`
 * called `.toLowerCase()` on the value while filtering, which threw
 * `TypeError: (group.name || "").toLowerCase is not a function`; the throw
 * escaped into `loadConfig()`'s catch, so the dashboard reported "Failed to
 * load configuration" and rendered no groups at all. Numbers and booleans are
 * shown as their text form — that is what a hand-edited file most plausibly
 * meant, and it keeps the group visible so it can be repaired through Edit.
 * Any other type has no sensible text form and reads as unnamed.
 *
 * @param {unknown} name The stored group name.
 * @returns {string} The name as display text, or ``""`` when unusable.
 */
export function groupNameText(name) {
    if (typeof name === 'string') return name;
    if (typeof name === 'number' || typeof name === 'boolean') {
        return String(name);
    }
    return '';
}

/**
 * The groups list as an iterable array.
 *
 * `renderGroups()` already tolerated a missing or non-list `groups` value, but
 * it then called `updateGlobalSyncExclusionsUI()`, which reads
 * `state.currentConfig.groups.map(...)` unguarded. `GET /api/config` serves the
 * stored file, so a config without a `groups` key (or with `"groups": null`)
 * threw `Cannot read properties of undefined (reading 'map')` from inside the
 * exclusions helper. The throw escaped `renderGroups()` and blanked the whole
 * dashboard on "Failed to load configuration" — the very failure the guard in
 * `renderGroups()` was added to prevent.
 *
 * @returns {object[]} Usable group objects; never `undefined`.
 */
function currentGroups() {
    if (!state.currentConfig || typeof state.currentConfig !== 'object') {
        state.currentConfig = {};
    }
    if (!Array.isArray(state.currentConfig.groups)) {
        state.currentConfig.groups = [];
    }
    return state.currentConfig.groups;
}

export function renderGroups() {
    const groupsList = getEl('groups-list');
    if (!groupsList) return;
    groupsList.innerHTML = '';

    if (currentGroups().length === 0) {
        groupsList.innerHTML = '<div class="groups-empty-state"><p class="groups-empty-icon">📁</p><p class="groups-empty-title">No groupings defined yet</p><p class="groups-empty-desc">Create your first grouping above, or use the <strong>Wizard</strong> for a guided setup.</p></div>';
        updateGlobalSyncExclusionsUI();
        updateGroupCount();
        return;
    }

    updateGlobalSyncExclusionsUI();
    updateGroupCount();

    let visibleCount = 0;
    const filter = _searchFilter.toLowerCase().trim();

    currentGroups().forEach((group, index) => {
        if (!group || typeof group !== 'object') return;
        const groupName = groupNameText(group.name).toLowerCase();
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
        h4.textContent = groupNameText(group.name) || 'Unnamed Group';
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
        // The icon is decorative and the visible "Remove" text is the label,
        // so the <svg> is hidden from assistive technology rather than
        // announced as an unnamed graphic before that text (WCAG 1.1.1).
        delBtn.innerHTML = '<svg aria-hidden="true" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="icon-delete"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg>';
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
    // Count only entries that render as cards: a hand-edited `null` in the
    // list is not a grouping, and counting it made the badge disagree with the
    // number of cards on screen.
    const total = currentGroups().filter(
        (group) => group && typeof group === 'object',
    ).length;
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
    const group = currentGroups()[index];
    // An out-of-range index is reachable from a stale "Edit" button after the
    // list changed underneath it; without this the form threw on
    // `group.name` and the click silently did nothing.
    if (!group || typeof group !== 'object') {
        showToast('That grouping is no longer available', 'error');
        return;
    }
    state.editingIndex = index;

    getEl('group_name').value = groupNameText(group.name);
    // Resolve the category from the group's own source type: a stored value
    // this build does not know, or a `source_type` that belongs to the other
    // category, would otherwise leave one of the two selects on no option and
    // the form would save whichever value the select happened to fall back to.
    getEl('source_category').value = resolveSourceCategory(
        group.source_category,
        group.source_type,
    );
    updateSourceTypeOptions(group.source_type);
    getEl('source_type').value = group.source_type || '';
    if (group.source_type && getEl('source_type').value !== group.source_type) {
        // The type belongs to the other category (or the option is missing
        // because its API key is unset). Rebuild against the category that
        // actually offers it so the pairing stays consistent.
        getEl('source_category').value = resolveSourceCategory(null, group.source_type);
        updateSourceTypeOptions(group.source_type);
        getEl('source_type').value = group.source_type;
    }
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
    // Rebuild the day lists for the stored months before selecting a day:
    // the form's day select only offers the days that exist in the month, so
    // assigning "31" to a February group would otherwise be a silent no-op.
    setSeasonalDate('seasonal_start', group.seasonal_start);
    setSeasonalDate('seasonal_end', group.seasonal_end);
    getEl('watch_state').value = group.watch_state || '';
    getEl('item_type').value = group.item_type || '';
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
    getEl('item_type').value = '';
    getEl('create_as_collection').checked = false;
    // The day lists belong to the months that were last selected; re-sync
    // them so the cleared form cannot offer "31" while February is shown.
    syncSeasonalDayLists();
    updateSourceTypeOptions();
}

export async function deleteGroup(index) {
    const groups = currentGroups();
    if (typeof index !== 'number' || index < 0 || index >= groups.length) {
        showToast('Invalid group index', 'error');
        return;
    }
    if (!await showConfirmDialog('Delete Grouping', 'Permanently remove this grouping?', 'Delete', 'Cancel')) return;
    const groupName = groups[index]?.name;
    // Only a string names a directory the cleanup endpoint can delete; any
    // other stored type is rejected there with an error the user cannot act
    // on after the group is already gone.
    const removableName = typeof groupName === 'string' && groupName ? groupName : '';
    if (state.editingIndex === index) cancelEdit();
    const removedGroup = groups.splice(index, 1)[0];
    try {
        await saveConfig(state.currentConfig);
    } catch (e) {
        // Re-insert at the original position. If the array was modified
        // between the splice and the save failure, append at the end.
        const current = currentGroups();
        if (index <= current.length) {
            current.splice(index, 0, removedGroup);
        } else {
            current.push(removedGroup);
        }
        showToast('Failed to save after deleting group', 'error');
        return;
    }
    renderGroups();

    if (removableName) {
        try {
            await apiPost('/api/cleanup', { folders: [removableName] });
        } catch (e) {
            showToast('Failed to clean up folder from disk: ' + e.message, 'error');
        }
    }
}

export async function clearAllGroups() {
    if (!await showConfirmDialog('Clear All Groupings', 'Are you sure you want to remove ALL groupings? This cannot be undone.', 'Clear All', 'Cancel')) return;
    const groups = currentGroups();
    const groupNames = groups
        .map(g => (g && typeof g === 'object' ? g.name : undefined))
        .filter(name => typeof name === 'string' && name);
    const backup = groups;
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
            await apiPost('/api/cleanup', { folders: groupNames });
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

/**
 * Number of days in *month* (``"01"``.."12"``), assuming a leap year.
 *
 * February gets 29 so a Feb-29 boundary stays selectable; the backend
 * validates with the same leap-year assumption.
 *
 * @param {string} month  Two-digit month string.
 * @returns {number} Day count for that month, or 31 for an unknown month.
 */
function daysInMonth(month) {
    const monthNumber = parseInt(month, 10);
    if (!Number.isFinite(monthNumber) || monthNumber < 1 || monthNumber > 12) {
        return 31;
    }
    // Day 0 of the next month is the last day of this one.
    return new Date(2024, monthNumber, 0).getDate();
}

/**
 * Fill a seasonal day select with only the days that exist in *month*.
 *
 * The previous implementation always offered 1-31 for every month, so
 * picking "31" for February produced ``02-31``. That shape passes a
 * month/day range check but is not a real date, and the backend used to
 * accept it and then treat the whole window as "always in season" — the
 * group was never cleaned up when its season ended.
 *
 * The previously selected day is preserved when it still exists, otherwise
 * it is clamped to the last valid day. An empty select starts at day 01, so a
 * brand-new form never defaults to a month-end boundary the user did not
 * choose.
 *
 * @param {HTMLSelectElement} select  The day select to rebuild.
 * @param {string} month  Two-digit month string.
 * @returns {void}
 */
function fillSeasonalDays(select, month) {
    if (!select) return;
    const previous = select.value;
    const maxDay = daysInMonth(month);
    select.innerHTML = '';
    for (let i = 1; i <= maxDay; i++) {
        const opt = document.createElement('option');
        opt.value = i.toString().padStart(2, '0');
        opt.textContent = i;
        select.appendChild(opt);
    }
    if (!previous) {
        select.value = '01';
        return;
    }
    const keep = parseInt(previous, 10);
    select.value = keep >= 1 && keep <= maxDay
        ? previous
        : maxDay.toString().padStart(2, '0');
}

/**
 * Set a seasonal date pair from an ``MM-DD`` string stored in the config.
 *
 * A stored value from before the validation fix can name a day that does not
 * exist in its month (``02-31``). Assigning that value to the rebuilt select
 * leaves it empty, and the form then saved ``02-`` — which the API rejects.
 * Such a legacy day is clamped to the last day of the month it belongs to.
 *
 * @param {string} prefix  ``"seasonal_start"`` or ``"seasonal_end"``.
 * @param {string|undefined} value  Stored ``MM-DD`` value.
 * @returns {void}
 */
export function setSeasonalDate(prefix, value) {
    if (typeof value !== 'string') return;
    const [month, day] = value.split('-');
    if (!month || !day) return;
    const monthSelect = getEl(`${prefix}_month`);
    const daySelect = getEl(`${prefix}_day`);
    if (!monthSelect || !daySelect) return;
    monthSelect.value = month;
    fillSeasonalDays(daySelect, month);
    const maxDay = daysInMonth(month);
    const wanted = parseInt(day, 10);
    daySelect.value = wanted >= 1 && wanted <= maxDay
        ? day.padStart(2, '0')
        : maxDay.toString().padStart(2, '0');
}

/**
 * Rebuild every seasonal day select from its currently selected month.
 *
 * @returns {void}
 */
export function syncSeasonalDayLists() {
    ['seasonal_start', 'seasonal_end'].forEach(prefix => {
        const monthSelect = getEl(`${prefix}_month`);
        const daySelect = getEl(`${prefix}_day`);
        if (!monthSelect || !daySelect) return;
        fillSeasonalDays(daySelect, monthSelect.value);
    });
}

/**
 * Populate both seasonal day selects and keep them in step with their months.
 *
 * @returns {void}
 */
export function populateSeasonalDays() {
    ['seasonal_start', 'seasonal_end'].forEach(prefix => {
        const monthSelect = getEl(`${prefix}_month`);
        const daySelect = getEl(`${prefix}_day`);
        if (!monthSelect || !daySelect) return;
        fillSeasonalDays(daySelect, monthSelect.value);
        monthSelect.onchange = () => fillSeasonalDays(daySelect, monthSelect.value);
    });
}

/**
 * Render the scheduler exclusion checkboxes and prune stale ids.
 *
 * An exclusion id is a group *name*, so an id that no longer names a group is
 * dropped rather than kept forever in the saved config.
 *
 * Both structures this reads are user-editable in `config.json` and arrive
 * unchanged from `GET /api/config`, so each is normalised before use: a
 * `scheduler` that is not an object is replaced with defaults, and a
 * `global_exclude_ids` that is not a list with an empty one. The previous code
 * only replaced a *falsy* scheduler and a *falsy* id list, so a string, a
 * number, or an object survived — and the assignment then threw
 * `Cannot create property 'global_exclude_ids' on string 'nope'`, or
 * `global_exclude_ids.filter is not a function`. Both escaped
 * `renderGroups()` and blanked the dashboard.
 *
 * @returns {void}
 */
export function updateGlobalSyncExclusionsUI() {
    const container = getEl('global_sync_exclusions');
    if (!container) return;
    container.innerHTML = '';

    // `config.json` is user-editable and an import can carry any shape here.
    if (
        !state.currentConfig.scheduler ||
        typeof state.currentConfig.scheduler !== 'object' ||
        Array.isArray(state.currentConfig.scheduler)
    ) {
        state.currentConfig.scheduler = {};
    }
    // A falsy check is not enough: a stored string, number, or object has no
    // `.filter()` either, and the next line calls it.
    if (!Array.isArray(state.currentConfig.scheduler.global_exclude_ids)) {
        state.currentConfig.scheduler.global_exclude_ids = [];
    }

    // Only real strings can be an exclusion id: the same value is a group
    // name in the scheduler, and a number or object there would never match
    // `group.name` in the checkbox comparison below.
    const validGroupNames = currentGroups()
        .map(g => (g && typeof g === 'object' ? g.name : undefined))
        .filter(name => typeof name === 'string' && name);
    state.currentConfig.scheduler.global_exclude_ids = state.currentConfig.scheduler.global_exclude_ids.filter(id => validGroupNames.includes(id));

    const excludedIds = state.currentConfig.scheduler.global_exclude_ids;

    currentGroups().forEach((group) => {
        if (!group || typeof group !== 'object') return;
        const name = group.name;
        if (typeof name !== 'string' || !name) return;
        const label = document.createElement('label');
        label.className = 'exclusion-checkbox-label';

        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = excludedIds.includes(name);
        cb.onchange = (e) => {
            const idx = excludedIds.indexOf(name);
            if (e.target.checked) {
                if (idx === -1) excludedIds.push(name);
            } else {
                if (idx !== -1) excludedIds.splice(idx, 1);
            }
        };

        label.appendChild(cb);
        label.appendChild(document.createTextNode(name));
        container.appendChild(label);
    });

    if (currentGroups().length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.8rem; font-style: italic;">No groups defined yet.</p>';
    }
}