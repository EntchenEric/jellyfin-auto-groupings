/**
 * Regression tests for the client-side timeout on sync endpoints.
 *
 * `apiRequest()` aborted every request after a flat 60 s. That is a sensible
 * cap for a config read, but a sync rebuilds each group directory link by
 * link and walks the whole Jellyfin library: the server allows its worker
 * 120 s by default and the README tells operators of large libraries to raise
 * that further. The client therefore gave up on work the server was still
 * doing and told the user "Request timed out", while the sync kept filling
 * directories in the background — the next attempt then answered `409`
 * because the first run still held the lock.
 *
 * A `?slow=1` style server delay is not reachable from a unit test, so these
 * tests assert the budget handed to the timer and the endpoints that get it.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/** The shortest budget that is unambiguous evidence of a long-run allowance. */
const LONG_MS = 5 * 60 * 1000;

let timers;

beforeEach(() => {
    document.body.innerHTML = `
        <div id="error-dialog-modal" class="modal" style="display: none">
            <p id="error-dialog-message"></p>
        </div>
        <div id="status-msg"></div>
    `;
    vi.resetModules();
    // Capture every scheduled timeout instead of waiting it out.
    timers = [];
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn, ms) => {
        timers.push(ms);
        return 0;
    });
    vi.spyOn(globalThis, 'clearTimeout').mockImplementation(() => {});
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    delete globalThis.fetch;
});

/** Answer every fetch with an empty success body. */
function stubFetch() {
    globalThis.fetch = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ status: 'success', results: [] }),
    }));
}

describe('sync request timeout budget', () => {
    it('gives a sync far more than the default read budget', async () => {
        stubFetch();
        const { runSync } = await import('../../static/js/core/api.js');

        await runSync();

        expect(Math.max(...timers)).toBeGreaterThanOrEqual(LONG_MS);
    });

    it('gives a preview the same long budget', async () => {
        stubFetch();
        const { previewSync } = await import('../../static/js/core/api.js');

        await previewSync();

        expect(Math.max(...timers)).toBeGreaterThanOrEqual(LONG_MS);
    });

    it('keeps the short budget for ordinary reads', async () => {
        stubFetch();
        const { loadConfig } = await import('../../static/js/core/api.js');

        await loadConfig();

        expect(Math.max(...timers)).toBeLessThan(LONG_MS);
    });

    it('posts a sync to the documented endpoint', async () => {
        stubFetch();
        const { runSync } = await import('../../static/js/core/api.js');

        await runSync();

        const [url, opts] = globalThis.fetch.mock.calls[0];
        expect(url).toBe('/api/sync');
        expect(opts.method).toBe('POST');
    });

    it('explains that a timed-out sync may still be running', async () => {
        globalThis.fetch = vi.fn(async () => {
            const err = new Error('aborted');
            err.name = 'AbortError';
            throw err;
        });
        const { apiGet } = await import('../../static/js/core/api.js');

        await apiGet('/api/config').catch(() => {});

        // `showErrorDialog` needs the modal elements above; the message must
        // not suggest a plain retry, because a sync still holds the run lock.
        const msg = document.getElementById('error-dialog-message').textContent;
        expect(msg).toMatch(/still be running/i);
        expect(msg).toMatch(/wait/i);
    });
});
