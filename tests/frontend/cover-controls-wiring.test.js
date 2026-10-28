/**
 * Regression tests for the cover dialog's control wiring.
 *
 * The template used inline `oninput="renderCover()"` / `onchange="renderCover()"`
 * attributes. Inline handlers resolve their names on `window`, but
 * `cover-generator.js` only *exports* `renderCover`, so every keystroke in the
 * "Cover Text" field threw `ReferenceError: renderCover is not defined` and the
 * preview stayed frozen at whatever `openCoverGenerator()` had drawn.
 *
 * The Apply and Download buttons were in the same state for a different
 * reason: nothing had ever bound them, so clicking either did nothing. Both
 * now go through `initCoverGenerator()`, which is what `app.js` calls on
 * bootstrap.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

/** The subset of the dialog partial that the wiring touches. */
const MODAL = `
  <div id="cover-generator-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <input id="cover-text" value="My Group">
    <select id="cover-theme">
      <option value="modern-dark" selected>a</option>
      <option value="cyberpunk">b</option>
    </select>
    <select id="cover-border-style"><option value="none">a</option></select>
    <input id="cover-border-color" value="#ffffff" class="cover-color-input">
    <input id="cover-color-1" value="#4f46e5" class="cover-color-input">
    <input id="cover-color-2" value="#9333ea" class="cover-color-input">
    <canvas id="cover-canvas"></canvas>
    <button type="button" id="apply-cover-btn">Apply Cover</button>
    <button type="button" id="download-cover-btn">Download</button>
  </div>
  <div id="error-dialog-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

/**
 * Give the canvas element a working 2D context stub.
 *
 * jsdom does not implement canvas rendering, so `getContext('2d')` returns
 * `null` and `renderCover()` bails out before drawing anything — which would
 * make "did the preview re-render?" unobservable.
 *
 * @param {HTMLCanvasElement} canvas
 * @returns {{setTransform: Function, clearRect: Function}} Recorded calls.
 */
function stubCanvasContext(canvas) {
    const calls = { setTransform: vi.fn(), clearRect: vi.fn() };
    const gradient = { addColorStop: vi.fn() };
    canvas.getContext = () => new Proxy({}, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (prop in calls) return calls[prop];
            return (...args) => {
                if (prop === 'measureText') {
                    return { width: String(args[0] ?? '').length * 10 };
                }
                return String(prop).startsWith('create') ? gradient : undefined;
            };
        },
        set: (target, prop, value) => { target[prop] = value; return true; },
    });
    return calls;
}

beforeEach(() => {
    document.body.innerHTML = MODAL;
    document.body.className = '';
    vi.resetModules();
    vi.restoreAllMocks();
    delete globalThis.fetch;
});

describe('initCoverGenerator', () => {
    it('redraws the preview when the cover text changes', async () => {
        const canvas = document.getElementById('cover-canvas');
        const calls = stubCanvasContext(canvas);

        const { initCoverGenerator } = await import(
            '../../static/js/features/cover-generator.js'
        );
        initCoverGenerator();
        calls.setTransform.mockClear();

        const text = document.getElementById('cover-text');
        text.value = 'A different name';
        text.dispatchEvent(new Event('input', { bubbles: true }));

        expect(calls.setTransform).toHaveBeenCalled();
    });

    it('redraws the preview when the theme changes', async () => {
        const canvas = document.getElementById('cover-canvas');
        const calls = stubCanvasContext(canvas);

        const { initCoverGenerator } = await import(
            '../../static/js/features/cover-generator.js'
        );
        initCoverGenerator();
        calls.setTransform.mockClear();

        const theme = document.getElementById('cover-theme');
        theme.value = 'cyberpunk';
        theme.dispatchEvent(new Event('change', { bubbles: true }));

        expect(calls.setTransform).toHaveBeenCalled();
    });

    it('does not stack handlers when initialised twice', async () => {
        const canvas = document.getElementById('cover-canvas');
        const calls = stubCanvasContext(canvas);

        const { initCoverGenerator } = await import(
            '../../static/js/features/cover-generator.js'
        );
        initCoverGenerator();
        initCoverGenerator();
        calls.setTransform.mockClear();

        const text = document.getElementById('cover-text');
        text.dispatchEvent(new Event('input', { bubbles: true }));

        // One render per event: a stacked handler would draw twice, which is
        // wasted canvas work on every keystroke.
        expect(calls.setTransform).toHaveBeenCalledTimes(1);
    });

    it('wires the download button', async () => {
        const canvas = document.getElementById('cover-canvas');
        stubCanvasContext(canvas);
        const toDataUrl = vi.fn(() => 'data:image/jpeg;base64,AAA');
        canvas.toDataURL = toDataUrl;

        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [{ name: 'Action' }] };

        const { initCoverGenerator, openCoverGenerator } = await import(
            '../../static/js/features/cover-generator.js'
        );
        initCoverGenerator();
        openCoverGenerator(0);

        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(() => {});

        document.getElementById('download-cover-btn').click();

        expect(toDataUrl).toHaveBeenCalled();
        expect(clickSpy).toHaveBeenCalled();
    });
});
