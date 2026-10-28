/**
 * Regression tests for a config whose `groups` key is missing or unusable.
 *
 * `GET /api/config` serves the stored file as it is on disk, and
 * `config.py` only repairs a `groups` value that is *present but not a list*
 * — a config written by hand, truncated by a failed write, or produced by an
 * older build can arrive with no `groups` key at all.
 *
 * `renderGroups()` had a guard for exactly that case, but it called
 * `updateGlobalSyncExclusionsUI()` before returning, and that helper read
 * `state.currentConfig.groups.map(...)` unguarded. The `TypeError` escaped
 * `renderGroups()` into `loadConfig()`'s catch, so the dashboard answered
 * "Failed to load configuration" and rendered nothing — the failure the guard
 * was written to prevent. The topbar buttons crashed the same way: Export read
 * `.length`, Sync read `.length`, and the group form iterated the list while
 * validating cron expressions.
 *
 * Every entry point that reads the list therefore normalises it first, and a
 * malformed *entry* is skipped rather than rendered or counted.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const PAGE = `
  <div id="groups-list"></div>
  <span id="groups-count-badge"></span>
  <div id="global_sync_exclusions"></div>
  <input id="groups-search">
  <div id="export-modal" class="modal" style="display:none">
    <div id="export-groups-container"></div>
    <div id="export-selection-list"></div>
    <input type="radio" name="export-type" value="all" checked>
    <input type="radio" name="export-type" value="selective">
  </div>
  <div id="error-dialog-modal" class="modal" style="display:none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

/** A config with a usable scheduler but no usable groups list. */
const CONFIGS = [
    ['missing', undefined],
    ['null', null],
    ['a string', 'nope'],
    ['a number', 7],
    ['an object', { length: 1 }],
];

async function mount() {
    document.body.innerHTML = PAGE;
    vi.resetModules();
    const stateMod = await import('../../static/js/core/state.js');
    const groupings = await import('../../static/js/features/groupings.js');
    return { state: stateMod.state, groupings };
}

describe('renderGroups with no usable groups list', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it.each(CONFIGS)('renders the empty state when groups is %s', async (_label, bad) => {
        const { state, groupings } = await mount();
        state.currentConfig = { scheduler: {} };
        state.currentConfig.groups = bad;

        expect(() => groupings.renderGroups()).not.toThrow();

        expect(document.querySelectorAll('#groups-list .group-card')).toHaveLength(0);
        // The empty state is what the user sees, so it has to be the
        // documented message and not a blank panel.
        expect(document.getElementById('groups-list').textContent).toContain(
            'No groupings defined yet',
        );
        expect(document.getElementById('groups-count-badge').textContent).toBe('0');
    });

    it('repairs the list in place so later reads see an array', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = { scheduler: { global_exclude_ids: [] } };

        groupings.renderGroups();

        expect(Array.isArray(state.currentConfig.groups)).toBe(true);
        expect(state.currentConfig.groups).toEqual([]);
    });

    it('survives a config object that is not an object at all', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = null;

        expect(() => groupings.renderGroups()).not.toThrow();
        expect(document.querySelectorAll('#groups-list .group-card')).toHaveLength(0);
    });
});

describe('renderGroups with malformed entries', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('skips null entries instead of throwing', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = {
            groups: [
                {
                    name: 'Drama',
                    source_category: 'jellyfin',
                    source_type: 'genre',
                    source_value: 'Drama',
                },
                null,
            ],
            scheduler: {},
        };

        expect(() => groupings.renderGroups()).not.toThrow();
        expect(document.querySelectorAll('#groups-list .group-card')).toHaveLength(1);
    });

    it('counts only renderable entries in the badge', async () => {
        const { state, groupings } = await mount();
        state.currentConfig = {
            groups: [
                { name: 'Drama', source_category: 'jellyfin', source_type: 'genre', source_value: 'Drama' },
                null,
            ],
            scheduler: {},
        };

        groupings.renderGroups();

        expect(document.getElementById('groups-count-badge').textContent).toBe('1');
        expect(document.querySelectorAll('#groups-list .group-card')).toHaveLength(1);
    });
});

describe('scheduler exclusions with no usable groups list', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it.each(CONFIGS)('does not throw when groups is %s', async (_label, bad) => {
        const { state, groupings } = await mount();
        state.currentConfig = { scheduler: {} };
        state.currentConfig.groups = bad;

        expect(() => groupings.updateGlobalSyncExclusionsUI()).not.toThrow();

        expect(
            document.getElementById('global_sync_exclusions').textContent,
        ).toContain('No groups defined yet');
    });
});

describe('topbar entry points with no usable groups list', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('opens the export dialog with an empty selection', async () => {
        const { state } = await mount();
        const exportImport = await import(
            '../../static/js/features/export-import.js'
        );
        state.currentConfig = { scheduler: {} };

        expect(() => exportImport.openExportModal()).not.toThrow();

        expect(
            document.getElementById('export-groups-container').textContent,
        ).toContain('No groups available to export');
    });

    it('reports an empty config from the sync dialog instead of throwing', async () => {
        const { state } = await mount();
        const sync = await import('../../static/js/features/sync.js');
        state.currentConfig = { scheduler: {} };

        expect(() => sync.showConfirmSyncDialog()).not.toThrow();

        expect(document.getElementById('error-dialog-message').textContent).toBe(
            'No groups to sync.',
        );
    });
});
