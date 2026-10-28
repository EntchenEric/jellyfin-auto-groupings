/**
 * Regression tests for `loadConfig()` and `editGroup()` against a config that
 * carries an unusable `source_category`.
 *
 * The migration in `loadConfig()` only filled a *missing* category. A value
 * that was present but unknown (`"External"` from an import, a future
 * release's category, a number) was copied through untouched, and
 * `updateSourceTypeOptions()` then threw on it. The throw escaped into the
 * loader's `catch`, so the dashboard answered "Failed to load configuration"
 * and rendered no groups even though the config had loaded fine.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const PAGE = `
  <input id="jellyfin_url"><input id="api_key">
  <input id="target_path"><input id="media_path_in_jellyfin">
  <input id="media_path_on_host"><input id="target_path_in_jellyfin">
  <input id="trakt_client_id"><input id="tmdb_api_key"><input id="mal_client_id">
  <input type="checkbox" id="auto_create_libraries">
  <input type="checkbox" id="auto_set_library_covers">
  <input type="checkbox" id="global_scheduler_enabled">
  <input type="text" id="global_sync_schedule">
  <input type="checkbox" id="cleanup_scheduler_enabled">
  <input type="text" id="cleanup_sync_schedule">
  <div id="global_sync_exclusions"></div>
  <select id="source_category">
    <option value="jellyfin">Jellyfin (Integrated)</option>
    <option value="external">External (3rd Party)</option>
  </select>
  <select id="source_type"></select>
  <input type="text" id="source_value">
  <div id="source_value_container"></div>
  <div id="source_value_help"></div>
  <div id="metadata_rules_container"></div>
  <button type="button" id="add-rule-btn"></button>
  <div id="groups-list"></div>
  <span id="groups-count-badge"></span>
  <div id="status-msg"></div>
  <div id="sidebar"></div>
  <div id="connection-warning"></div>
  <div id="error-dialog-modal" class="modal" style="display:none">
    <p id="error-dialog-message"></p>
  </div>
`;

/** Extra fields `editGroup()` reads that the config page above omits. */
const EDIT_FIELDS = `
  <input id="group_name"><select id="sort_order"><option value=""></option></select>
  <input type="checkbox" id="sort_order_enabled"><div id="sort_order_panel"></div>
  <input type="checkbox" id="schedule_enabled"><div id="group_scheduler_panel"></div>
  <input id="group_schedule">
  <input type="checkbox" id="seasonal_enabled"><div id="seasonal_panel"></div>
  <select id="watch_state"><option value=""></option></select>
  <select id="item_type"><option value=""></option></select>
  <input type="checkbox" id="create_as_collection">
  <div id="group-form-title"></div><button id="add-group-btn"></button>
  <button id="cancel-edit-btn"></button>
  <form id="group-form">
    <select id="seasonal_start_month"><option value="01">01</option></select>
    <select id="seasonal_start_day"><option value="01">01</option></select>
    <select id="seasonal_end_month"><option value="01">01</option></select>
    <select id="seasonal_end_day"><option value="01">01</option></select>
  </form>
`;

async function mount(html = PAGE) {
    document.body.innerHTML = html;
    // jsdom implements no layout, so `scrollIntoView` is missing entirely.
    // `editGroup()` calls it to bring the form into view; stub it rather than
    // weakening the production code for a browser-only API.
    Element.prototype.scrollIntoView = () => {};
    vi.resetModules();
    const stateMod = await import('../../static/js/core/state.js');
    const config = await import('../../static/js/features/config.js');
    const groupings = await import('../../static/js/features/groupings.js');
    return { state: stateMod.state, config, groupings };
}

/** Serve *config* to `/api/config` and nothing else. */
function stubConfigFetch(config) {
    globalThis.fetch = vi.fn(async (url) => {
        if (String(url).includes('/api/config')) {
            return {
                ok: true,
                status: 200,
                json: async () => config,
            };
        }
        return { ok: true, status: 200, json: async () => ({ status: 'success' }) };
    });
}

describe('loadConfig with an unknown source category', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('loads the page instead of showing an error dialog', async () => {
        const { config, state } = await mount();
        stubConfigFetch({
            groups: [
                { name: 'Docs', source_category: 'External', source_type: 'imdb_list', source_value: 'ls1' },
                { name: 'Horror', source_category: 'jellyfin', source_type: 'genre', source_value: 'Horror' },
            ],
            scheduler: {},
        });

        await config.loadConfig();

        expect(state.currentConfig.groups).toHaveLength(2);
        expect(document.getElementById('groups-list').children.length).toBe(2);
        // The dashboard's error dialog stays closed.
        expect(document.getElementById('error-dialog-modal').style.display).toBe('none');
    });

    it('repairs the stored category from the group source type', async () => {
        const { config, state } = await mount();
        stubConfigFetch({
            groups: [
                { name: 'Docs', source_category: 'nonsense', source_type: 'tmdb_list', source_value: '1' },
            ],
            scheduler: {},
        });

        await config.loadConfig();

        expect(state.currentConfig.groups[0].source_category).toBe('external');
    });

    it('drops non-object group entries instead of failing the whole load', async () => {
        const { config, state } = await mount();
        stubConfigFetch({
            groups: [null, 'oops', { name: 'Keep', source_type: 'genre', source_value: 'X' }],
            scheduler: {},
        });

        await config.loadConfig();

        expect(state.currentConfig.groups).toHaveLength(1);
        expect(state.currentConfig.groups[0].name).toBe('Keep');
    });

    it('treats a non-list groups value as empty', async () => {
        const { config, state } = await mount();
        stubConfigFetch({ groups: 'not-a-list', scheduler: {} });

        await config.loadConfig();

        expect(state.currentConfig.groups).toEqual([]);
    });
});

describe('editGroup with an unknown source category', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('opens the form and keeps the group pairing consistent', async () => {
        const { state, groupings } = await mount(PAGE + EDIT_FIELDS);
        state.currentConfig.groups = [
            { name: 'Docs', source_category: 'External', source_type: 'imdb_list', source_value: 'ls1' },
        ];

        expect(() => groupings.editGroup(0)).not.toThrow();
        expect(document.getElementById('source_category').value).toBe('external');
        expect(document.getElementById('source_type').value).toBe('imdb_list');
        expect(document.getElementById('group_name').value).toBe('Docs');
    });

    it('moves a mislabelled external type into the external category', async () => {
        const { state, groupings } = await mount(PAGE + EDIT_FIELDS);
        state.currentConfig.groups = [
            { name: 'Docs', source_category: 'jellyfin', source_type: 'tmdb_list', source_value: '1' },
        ];

        expect(() => groupings.editGroup(0)).not.toThrow();
        expect(document.getElementById('source_category').value).toBe('external');
        expect(document.getElementById('source_type').value).toBe('tmdb_list');
    });
});
