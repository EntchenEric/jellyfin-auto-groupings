/**
 * Regression tests for the loading-state helper.
 *
 * The sync and preview handlers used `fn().finally(() => setLoading(btn,
 * false))` without awaiting the result. `finally()` passes the rejection on to
 * the promise it returns, and nothing consumed that promise, so every failed
 * sync raised an *unhandled rejection* in addition to the error dialog
 * `apiRequest()` had already shown. The app's `unhandledrejection` listener
 * turned that into a second error toast: one click, two complaints, and a
 * console error that looks like a crash in unrelated code.
 *
 * The helper also has to clear the loading state on every exit path, because a
 * button stuck in its loading class is unusable until the page is reloaded.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const BUTTON = `<button id="action-btn">Run</button>`;

beforeEach(() => {
    document.body.innerHTML = BUTTON;
    vi.resetModules();
});

/** Load `app.js` and return the helper, with bootstrap kept inert. */
async function load() {
    // `app.js` registers a DOMContentLoaded bootstrap that would fetch config
    // and load metadata; the helper under test needs none of that.
    document.dispatchEvent = document.dispatchEvent.bind(document);
    return import('../../static/js/app.js');
}

describe('withLoading', () => {
    it('toggles the loading class around a successful run', async () => {
        const { withLoading } = await load();
        const btn = document.getElementById('action-btn');
        const seen = [];

        await withLoading(btn, async () => {
            seen.push(btn.classList.contains('btn-loading'));
        });

        expect(seen).toEqual([true]);
        expect(btn.classList.contains('btn-loading')).toBe(false);
    });

    it('clears the loading class and does not reject when the work fails', async () => {
        const { withLoading } = await load();
        const btn = document.getElementById('action-btn');
        const onUnhandled = vi.fn();
        window.addEventListener('unhandledrejection', onUnhandled);

        // The failure is reported by apiRequest(); the helper must absorb it
        // rather than let it escape as an unhandled rejection.
        await expect(
            withLoading(btn, async () => { throw new Error('sync failed'); })
        ).resolves.toBeUndefined();

        // Give the rejection a macrotask to surface if it were unhandled.
        await new Promise((resolve) => setTimeout(resolve, 10));
        window.removeEventListener('unhandledrejection', onUnhandled);

        expect(btn.classList.contains('btn-loading')).toBe(false);
        expect(onUnhandled).not.toHaveBeenCalled();
    });

    it('clears the loading class for a missing button', async () => {
        const { withLoading } = await load();

        await expect(
            withLoading(null, async () => {})
        ).resolves.toBeUndefined();
    });
});
