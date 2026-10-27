/**
 * Regression tests for how the sync results are reported.
 *
 * Two defects lived here, both hidden by mocks that only ever returned a
 * well-formed success:
 *
 * - `syncAll()` reduced over `result.results` without a guard, so a response
 *   without that key threw a `TypeError` inside the click handler and the
 *   button stayed in its loading state with no message. A per-group `error`
 *   was rendered in the results panel but the toast still said "Sync
 *   complete!" in green, so a run where *every* group failed looked healthy.
 * - `previewSyncAll()` fell through to "No groupings configured." whenever
 *   `results` was not an array, blaming the user's config for a malformed
 *   response.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const DOM = `
  <div id="status-msg" role="status" aria-live="polite"></div>
  <div id="sync-results-panel" style="display: none">
    <div id="sync-results-content"></div>
  </div>
  <div id="preview-sync-modal" class="modal" style="display: none">
    <div id="preview-sync-results"></div>
  </div>
  <div id="error-dialog-modal" class="modal" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
`;

beforeEach(() => {
    document.body.innerHTML = DOM;
    document.body.className = '';
    vi.resetModules();
});

/** Import `sync.js` with the API module stubbed to answer with *response*. */
async function loadSync(response) {
    vi.doMock('../../static/js/core/api.js', () => ({
        runSync: async () => response,
        previewSync: async () => response,
    }));
    return import('../../static/js/features/sync.js');
}

describe('syncAll result reporting', () => {
    it('reports a fully successful run in the success style', async () => {
        const { syncAll } = await loadSync({
            status: 'success',
            results: [{ group: 'A', links: 2 }, { group: 'B', links: 3 }],
        });

        await syncAll();

        const toast = document.getElementById('status-msg');
        expect(toast.textContent).toContain('Sync complete!');
        expect(toast.textContent).toContain('5');
        expect(toast.className).toContain('success');
    });

    it('warns instead of claiming success when a group failed', async () => {
        const { syncAll } = await loadSync({
            status: 'success',
            results: [
                { group: 'A', links: 2 },
                { group: 'B', links: 0, error: 'fetch failed' },
            ],
        });

        await syncAll();

        const toast = document.getElementById('status-msg');
        expect(toast.textContent).not.toContain('Sync complete!');
        expect(toast.textContent).toContain('1 group');
        expect(toast.textContent).toContain('failed');
        expect(toast.className).toContain('warning');
    });

    it('pluralises the failed-group count', async () => {
        const { syncAll } = await loadSync({
            status: 'success',
            results: [
                { group: 'A', links: 0, error: 'x' },
                { group: 'B', links: 0, error: 'y' },
            ],
        });

        await syncAll();

        expect(document.getElementById('status-msg').textContent).toContain(
            '2 groups failed',
        );
    });

    it('survives a response without a results array', async () => {
        const { syncAll } = await loadSync({ status: 'success' });

        await expect(syncAll()).resolves.toBeUndefined();

        const toast = document.getElementById('status-msg');
        expect(toast.textContent).toContain('0');
        expect(toast.className).toContain('success');
    });

    it('ignores a non-numeric links value when totalling', async () => {
        const { syncAll } = await loadSync({
            status: 'success',
            results: [{ group: 'A', links: 2 }, { group: 'B', links: null }],
        });

        await syncAll();

        expect(document.getElementById('status-msg').textContent).toContain(
            'Created 2',
        );
    });

    it('shows the server message when the run itself failed', async () => {
        const { syncAll } = await loadSync({
            status: 'error',
            message: 'Server settings or target path not configured',
        });

        await syncAll();

        const msg = document.getElementById('error-dialog-message');
        expect(msg.textContent).toContain('not configured');
    });
});

describe('previewSyncAll result reporting', () => {
    it('does not blame the config for a malformed response', async () => {
        const { previewSyncAll } = await loadSync({
            status: 'success',
            results: 'nope',
        });

        await previewSyncAll();

        const container = document.getElementById('preview-sync-results');
        // "No groupings configured." is the wrong diagnosis here; the empty
        // render is acceptable as long as nothing throws.
        expect(container.textContent).not.toContain('No groupings configured');
    });

    it('says the config is empty only for a genuinely empty list', async () => {
        const { previewSyncAll } = await loadSync({
            status: 'success',
            results: [],
        });

        await previewSyncAll();

        expect(
            document.getElementById('preview-sync-results').textContent,
        ).toContain('No groupings configured');
    });
});
