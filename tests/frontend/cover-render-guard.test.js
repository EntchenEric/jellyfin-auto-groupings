/**
 * Regression tests for `renderCover()` running after its canvas is gone.
 *
 * `renderCover()` is scheduled from two places that outlive the element they
 * were scheduled against: `document.fonts.ready.then(...)` when the cover
 * dialog opens, and a bare `setTimeout` fallback. Both fire later, and the
 * modal is a Jinja partial — a page rendered without it, or one whose dialog
 * was torn down before the font promise settled, left `getEl('cover-canvas')`
 * returning `null`. The next line called `canvas.getContext('2d')` and threw
 * `TypeError: Cannot read properties of null (reading 'getContext')`; the test
 * run reported it as an unhandled exception from a timer.
 *
 * The same crash happened with the element present but its 2D context absent
 * (`getContext()` returns `null` when canvas rendering is unavailable), which
 * threw one line later on `setTransform()`.
 *
 * Rendering is also not a failure the user can act on: it is a preview of an
 * image that has not been saved. Leaving the dialog open with an empty canvas
 * is the right behaviour, so the function returns instead of throwing.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const MODAL = `
  <div id="cover-generator-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <input id="cover-text" value="My Group">
    <select id="cover-theme"><option value="modern-dark">a</option></select>
    <select id="cover-border-style"><option value="none">a</option></select>
    <input id="cover-border-color" value="#ffffff">
    <input id="cover-color-1" value="#4f46e5">
    <input id="cover-color-2" value="#9333ea">
    <canvas id="cover-canvas"></canvas>
    <button class="close-modal-btn">x</button>
  </div>
  <div id="error-dialog-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

/** Replace the DOM before each test so state cannot leak between them. */
function mount(html = MODAL) {
    document.body.innerHTML = html;
    document.body.className = '';
}

beforeEach(() => {
    mount();
    vi.resetModules();
});

describe('renderCover tolerance of a missing canvas', () => {
    it('does not throw when the canvas element is absent', async () => {
        mount(`<div id="status-msg"></div>`);
        const { renderCover } = await import(
            '../../static/js/features/cover-generator.js'
        );

        expect(() => renderCover()).not.toThrow();
    });

    it('does not throw when getContext() returns null', async () => {
        const { renderCover } = await import(
            '../../static/js/features/cover-generator.js'
        );
        const canvas = document.getElementById('cover-canvas');
        canvas.getContext = () => null;

        expect(() => renderCover()).not.toThrow();
    });

    it('still renders when the canvas and its context are available', async () => {
        const { renderCover } = await import(
            '../../static/js/features/cover-generator.js'
        );
        const canvas = document.getElementById('cover-canvas');
        const calls = [];
        // The renderer draws gradients, so `createLinearGradient()` must return
        // an object that accepts `addColorStop()`. Every other context method
        // is recorded and treated as a no-op.
        const gradient = { addColorStop: vi.fn() };
        canvas.getContext = () => new Proxy({}, {
            get: (target, prop) => {
                if (prop in target) return target[prop];
                return (...args) => {
                    calls.push([prop, args]);
                    if (prop === 'measureText') return { width: String(args[0] ?? '').length * 10 };
                    return prop.startsWith('create') ? gradient : undefined;
                };
            },
            set: (target, prop, value) => { target[prop] = value; return true; },
        });

        expect(() => renderCover()).not.toThrow();
        // setTransform is the first real canvas call; its presence proves the
        // guard did not silently skip a renderable canvas.
        expect(calls.some(([prop]) => prop === 'setTransform')).toBe(true);
    });
});

describe('deferred cover render', () => {
    it('drops a scheduled render when the dialog closes first', async () => {
        const { openCoverGenerator, cancelPendingRender } = await import(
            '../../static/js/features/cover-generator.js'
        );
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [{ name: 'G' }], scheduler: {} };

        const canvas = document.getElementById('cover-canvas');
        const getContext = vi.fn(() => null);
        canvas.getContext = getContext;

        openCoverGenerator(0);
        // Closing before the font/timer callback runs must cancel it, so the
        // render never reaches the canvas at all.
        cancelPendingRender();

        await new Promise((resolve) => setTimeout(resolve, 200));

        expect(getContext).not.toHaveBeenCalled();
    });
});
