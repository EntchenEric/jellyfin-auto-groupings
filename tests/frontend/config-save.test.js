/**
 * Regression tests for `saveAllConfig()`'s success signal.
 *
 * The group form used to `await saveAllConfig()` and then unconditionally
 * clear itself. `saveAllConfig()` swallowed every failure — the client-side
 * cron check returned early, and the request error was caught and dropped —
 * so a rejected save was indistinguishable from a successful one: the form
 * cleared, the entry stayed in memory, and the *next* save from anywhere in
 * the UI failed again for a reason nothing pointed at.
 *
 * `saveAllConfig()` now resolves to `true` only when the server accepted the
 * config, and the form rolls its in-memory change back on `false` while
 * keeping the typed values.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { saveAllConfig } from '../../static/js/features/config.js';
import { state } from '../../static/js/core/state.js';

/** Render the inputs `saveAllConfig()` reads before posting. */
function mountSchedulerInputs() {
    document.body.innerHTML = `
        <input type="checkbox" id="global_scheduler_enabled">
        <input type="text" id="global_sync_schedule" value="0 3 * * *">
        <input type="checkbox" id="cleanup_scheduler_enabled">
        <input type="text" id="cleanup_sync_schedule" value="0 * * * *">
        <div id="groups-list"></div>
        <div id="global_sync_exclusions"></div>
        <div id="group-count"></div>
        <select id="source_category"><option value="jellyfin" selected>jellyfin</option></select>
        <select id="source_type"></select>
        <div id="status-msg"></div>
    `;
    state.currentConfig = { groups: [], scheduler: {} };
    state.cachedMetadata = {};
    state.editingIndex = -1;
}

beforeEach(() => {
    mountSchedulerInputs();
});

afterEach(() => {
    vi.restoreAllMocks();
    delete globalThis.fetch;
});

describe('saveAllConfig', () => {
    it('resolves true when the server accepts the config', async () => {
        globalThis.fetch = vi.fn(async () => ({
            ok: true,
            status: 200,
            json: async () => ({ status: 'success' }),
        }));

        await expect(saveAllConfig()).resolves.toBe(true);
    });

    it('resolves false when the server rejects the config', async () => {
        globalThis.fetch = vi.fn(async () => ({
            ok: false,
            status: 400,
            json: async () => ({
                status: 'error',
                message: 'Invalid config field type(s)',
                errors: ["groups[1].name duplicates groups[0].name ('Dup')"],
            }),
        }));

        await expect(saveAllConfig()).resolves.toBe(false);
    });

    it('resolves false when the request itself fails', async () => {
        globalThis.fetch = vi.fn(async () => {
            throw new TypeError('Failed to fetch');
        });

        await expect(saveAllConfig()).resolves.toBe(false);
    });

    it('resolves false when a group cron expression is invalid', async () => {
        state.currentConfig.groups = [
            { name: 'Action', schedule_enabled: true, schedule: 'not a cron' },
        ];
        globalThis.fetch = vi.fn(async () => ({
            ok: true,
            status: 200,
            json: async () => ({ status: 'success' }),
        }));

        await expect(saveAllConfig()).resolves.toBe(false);
        // The invalid schedule must not reach the server at all.
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it('resolves false when the global cron expression is invalid', async () => {
        document.getElementById('global_scheduler_enabled').checked = true;
        document.getElementById('global_sync_schedule').value = '* *';
        globalThis.fetch = vi.fn(async () => ({
            ok: true,
            status: 200,
            json: async () => ({ status: 'success' }),
        }));

        await expect(saveAllConfig()).resolves.toBe(false);
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });
});
