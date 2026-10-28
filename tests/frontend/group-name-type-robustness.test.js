/**
 * Regression tests for a group whose `name` is not a string.
 *
 * `POST /api/config` rejects a non-string `name` — `_validate_group_types()`
 * answers `'groups[0].name' must be a str` — but `GET /api/config` serves the
 * stored file as-is, and `config.py` only drops non-*object* group entries.
 * A hand-edited `config.json` or an imported file therefore reaches the
 * dashboard with `"name": 42`, an object, or an array.
 *
 * `renderGroups()` filtered with `(group.name || '').toLowerCase()`, which
 * threw `TypeError: (group.name || "").toLowerCase is not a function`. The
 * throw propagated out of `updateGlobalSyncExclusionsUI()` into
 * `loadConfig()`'s catch: the page reported "Failed to load configuration" and
 * rendered no groups at all, so a single typo in one name hid every other
 * group and there was no way to reach the Edit button that would fix it.
 *
 * The server is not changed here: rejecting the value on read would hide the
 * user's data. Instead the name is rendered as text — numbers and booleans as
 * their string form, so the group stays visible and repairable — and every
 * path that needs a *string* name (the scheduler exclusion list, the cleanup
 * call that names a directory) checks the type before using it.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const PAGE = `
  <div id="groups-list"></div>
  <span id="groups-count-badge"></span>
  <div id="global_sync_exclusions"></div>
  <input id="groups-search">
  <div id="error-dialog-modal" class="modal" style="display:none">
    <p id="error-dialog-message"></p>
  </div>
`;

/** The fields `editGroup()` reads, which the dashboard page does not carry. */
const EDIT_FIELDS = `
  <select id="source_category">
    <option value="jellyfin">Jellyfin (Integrated)</option>
    <option value="external">External (3rd Party)</option>
  </select>
  <select id="source_type"></select>
  <input id="group_name">
  <select id="sort_order"><option value=""></option></select>
  <input type="checkbox" id="sort_order_enabled"><div id="sort_order_panel"></div>
  <input type="checkbox" id="schedule_enabled"><div id="group_scheduler_panel"></div>
  <input id="group_schedule">
  <input type="checkbox" id="seasonal_enabled"><div id="seasonal_panel"></div>
  <select id="watch_state"><option value=""></option></select>
  <select id="item_type"><option value=""></option></select>
  <input type="checkbox" id="create_as_collection">
  <div id="group_form_title_probe"></div>
  <div id="group-form-title"></div>
  <button id="add-group-btn"></button><button id="cancel-edit-btn"></button>
  <form id="group-form">
    <select id="seasonal_start_month"><option value="01">01</option></select>
    <select id="seasonal_start_day"><option value="01">01</option></select>
    <select id="seasonal_end_month"><option value="01">01</option></select>
    <select id="seasonal_end_day"><option value="01">01</option></select>
  </form>
  <input id="source_value">
  <div id="source_value_container"></div>
  <div id="source_value_help"></div>
  <div id="metadata_rules_container"></div>
  <button id="add-rule-btn"></button>
`;

/** A usable group, so only the `name` under test is malformed. */
function group(name, extra = {}) {
    return {
        name,
        source_category: 'jellyfin',
        source_type: 'genre',
        source_value: 'Action',
        ...extra,
    };
}

async function mount(html = PAGE) {
    document.body.innerHTML = html;
    Element.prototype.scrollIntoView = () => {};
    vi.resetModules();
    const stateMod = await import('../../static/js/core/state.js');
    const groupings = await import('../../static/js/features/groupings.js');
    return { state: stateMod.state, groupings };
}

const NAMES = [
    ['a number', 42, '42'],
    ['a boolean', true, 'true'],
    ['an object', { nested: 1 }, ''],
    ['an array', ['a', 'b'], ''],
];

describe('renderGroups with a non-string group name', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it.each(NAMES)('renders every group when one name is %s', async (_label, bad, text) => {
        const { state, groupings } = await mount();
        state.currentConfig = { groups: [group(bad), group('Drama')], scheduler: {} };

        expect(() => groupings.renderGroups()).not.toThrow();

        const cards = document.querySelectorAll('#groups-list .group-card');
        expect(cards).toHaveLength(2);
        // The malformed group is still listed, under its text form or as
        // unnamed, so the user can open it and correct the name.
        expect(cards[0].querySelector('h4').textContent).toBe(
            text || 'Unnamed Group',
        );
        expect(cards[1].querySelector('h4').textContent).toBe('Drama');
    });

    it('does not hide usable groups behind the bad one', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = {
            groups: [group(42), group('Horror'), group('Comedy')],
            scheduler: {},
        };

        groupings.renderGroups();

        expect(
            Array.from(document.querySelectorAll('#groups-list h4')).map(
                (h) => h.textContent,
            ),
        ).toEqual(['42', 'Horror', 'Comedy']);
    });

    it('keeps the group count badge accurate', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = { groups: [group(42), group('Drama')], scheduler: {} };

        groupings.renderGroups();

        expect(document.getElementById('groups-count-badge').textContent).toBe('2');
    });

    it('matches a text-form name when filtering', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = {
            groups: [group(42), group('Drama')],
            scheduler: {},
        };
        groupings.initGroupSearch();
        const search = document.getElementById('groups-search');
        search.value = '42';
        search.dispatchEvent(new Event('input'));

        expect(document.querySelectorAll('#groups-list .group-card')).toHaveLength(1);
        expect(document.getElementById('groups-count-badge').textContent).toBe('1/2');
    });
});

describe('groupNameText', () => {
    it('keeps a string unchanged, including one that is empty', async () => {
        const { groupings } = await mount();
        expect(groupings.groupNameText('Action')).toBe('Action');
        expect(groupings.groupNameText('')).toBe('');
    });

    it('renders numbers and booleans as text', async () => {
        const { groupings } = await mount();
        expect(groupings.groupNameText(42)).toBe('42');
        expect(groupings.groupNameText(0)).toBe('0');
        expect(groupings.groupNameText(false)).toBe('false');
    });

    it('treats structures and null as unusable', async () => {
        const { groupings } = await mount();
        expect(groupings.groupNameText({ a: 1 })).toBe('');
        expect(groupings.groupNameText(['a'])).toBe('');
        expect(groupings.groupNameText(null)).toBe('');
        expect(groupings.groupNameText(undefined)).toBe('');
    });
});

describe('scheduler exclusions with a non-string group name', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('lists only groups whose name is a string', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = {
            groups: [group(42), group('Drama')],
            scheduler: { global_enabled: false, global_schedule: '', global_exclude_ids: [] },
        };

        expect(() => groupings.updateGlobalSyncExclusionsUI()).not.toThrow();

        const labels = Array.from(
            document.querySelectorAll('#global_sync_exclusions label'),
        ).map((l) => l.textContent);
        expect(labels).toEqual(['Drama']);
    });

    it('drops a non-string id from the stored exclusion list', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = {
            groups: [group(42), group('Drama')],
            scheduler: { global_exclude_ids: [42, 'Drama'] },
        };

        groupings.updateGlobalSyncExclusionsUI();

        expect(state.currentConfig.scheduler.global_exclude_ids).toEqual(['Drama']);
    });

    it.each([
        ['a string', 'Drama'],
        ['a number', 5],
        ['an object', { a: 1 }],
    ])('replaces a %s exclusion list instead of throwing', async (_label, bad) => {
        const { state, groupings } = await mount();
        state.currentConfig = {
            groups: [group('Drama')],
            scheduler: { global_exclude_ids: bad },
        };

        expect(() => groupings.updateGlobalSyncExclusionsUI()).not.toThrow();

        expect(state.currentConfig.scheduler.global_exclude_ids).toEqual([]);
        // The group is still offered, so the user can re-exclude it.
        expect(
            document.querySelectorAll('#global_sync_exclusions label'),
        ).toHaveLength(1);
    });

    it.each([
        ['a string', 'nope'],
        ['a number', 7],
        ['an array', [1]],
    ])('replaces a scheduler that is %s', async (_label, bad) => {
        const { state, groupings } = await mount();
        state.currentConfig = { groups: [group('Drama')], scheduler: bad };

        expect(() => groupings.updateGlobalSyncExclusionsUI()).not.toThrow();

        expect(state.currentConfig.scheduler).toEqual({ global_exclude_ids: [] });
    });
});

describe('editGroup with a non-string group name', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('opens the form with the name as text instead of throwing', async () => {
        const { groupings, state } = await mount(PAGE + EDIT_FIELDS);
        state.currentConfig = { groups: [group(42)], scheduler: {} };

        expect(() => groupings.editGroup(0)).not.toThrow();

        // An `<input>` value is always text; assigning a number would stringify
        // it anyway, but going through the helper keeps every call site honest.
        expect(document.getElementById('group_name').value).toBe('42');
    });

    it('opens the form for a structurally unusable name', async () => {
        const { groupings, state } = await mount(PAGE + EDIT_FIELDS);
        state.currentConfig = { groups: [group({ a: 1 })], scheduler: {} };

        expect(() => groupings.editGroup(0)).not.toThrow();
        expect(document.getElementById('group_name').value).toBe('');
    });
});
