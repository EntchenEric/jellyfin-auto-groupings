/**
 * Regression tests for keyboard accessibility of the sidebar resizer.
 *
 * The resizer was drag-only: `initSidebarResizer()` bound mousedown/mousemove
 * and touch handlers, and the element carried no `role`, no `tabindex` and no
 * value. A keyboard-only or screen-reader user therefore had no way to change
 * the sidebar width at all, and no way to discover that resizing existed.
 *
 * The fix follows the ARIA window-splitter pattern: `role="separator"` with a
 * `tabindex`, `aria-valuenow` kept in sync with the applied width, and arrow /
 * Home / End keys that resize. These tests pin that contract, including the
 * bounds, the persistence, and the fact that unrelated keys stay untouched so
 * arrow keys keep scrolling the sidebar.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

import { initSidebarResizer } from '../../static/js/features/sidebar-resizer.js';

const MIN_WIDTH = 200;
const MAX_WIDTH = 800;
const STEP = 16;
const LARGE_STEP = 64;

/** Replace the DOM with a fresh resizer and clear stored state. */
function mount() {
    document.body.innerHTML = '<div id="sidebar-resizer" role="separator" tabindex="0"></div>';
    // Mirror the stylesheet default so `width()` reads a number: jsdom loads no
    // CSS, and a real page always has `--sidebar-width` from variables.css.
    document.documentElement.style.setProperty('--sidebar-width', '340px');
    localStorage.clear();
    return document.getElementById('sidebar-resizer');
}

/** Read the width currently applied to the document root. */
function width() {
    return Number.parseFloat(
        document.documentElement.style.getPropertyValue('--sidebar-width')
    );
}

/** Press a key on *el* and report whether the default action was prevented. */
function press(el, key, init = {}) {
    const event = new window.KeyboardEvent('keydown', {
        key,
        bubbles: true,
        cancelable: true,
        ...init
    });
    el.dispatchEvent(event);
    return event.defaultPrevented;
}

/**
 * Load a fresh copy of the module.
 *
 * The module keeps `listening` at module scope so document-level handlers are
 * registered once; a fresh copy per test therefore gives each case an
 * isolated listener set while the shared state stays consistent within a test.
 */
async function freshInit() {
    vi.resetModules();
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();
    return mod;
}

beforeEach(() => {
    mount();
});

describe('sidebar resizer keyboard support', () => {
    it('announces the width in effect through aria-valuenow', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        expect(resizer.getAttribute('aria-valuenow')).toBe('340');
    });

    it('widens with ArrowRight and narrows with ArrowLeft', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        const start = width();

        expect(press(resizer, 'ArrowRight')).toBe(true);
        expect(width()).toBe(start + STEP);

        expect(press(resizer, 'ArrowLeft')).toBe(true);
        expect(width()).toBe(start);
    });

    it('moves by a larger step when Shift is held', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        const start = width();

        press(resizer, 'ArrowRight', { shiftKey: true });
        expect(width()).toBe(start + LARGE_STEP);

        press(resizer, 'ArrowLeft', { shiftKey: true });
        expect(width()).toBe(start);
    });

    it('jumps to the bounds with Home and End', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        press(resizer, 'Home');
        expect(width()).toBe(MIN_WIDTH);

        press(resizer, 'End');
        expect(width()).toBe(MAX_WIDTH);
    });

    it('clamps instead of running past the bounds', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        press(resizer, 'End');
        press(resizer, 'ArrowRight');
        expect(width()).toBe(MAX_WIDTH);

        press(resizer, 'Home');
        press(resizer, 'ArrowLeft');
        expect(width()).toBe(MIN_WIDTH);
    });

    it('keeps aria-valuenow in step with every change', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        press(resizer, 'End');
        expect(resizer.getAttribute('aria-valuenow')).toBe(String(MAX_WIDTH));

        press(resizer, 'Home');
        expect(resizer.getAttribute('aria-valuenow')).toBe(String(MIN_WIDTH));

        press(resizer, 'ArrowRight');
        expect(resizer.getAttribute('aria-valuenow')).toBe(String(MIN_WIDTH + STEP));
    });

    it('persists the width so a reload restores it', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        press(resizer, 'End');
        expect(localStorage.getItem('sidebarWidth')).toBe(String(MAX_WIDTH));

        // A fresh mount without the inline property must restore from storage.
        document.documentElement.style.removeProperty('--sidebar-width');
        document.getElementById('sidebar-resizer').remove();
        document.body.innerHTML = '<div id="sidebar-resizer" role="separator" tabindex="0"></div>';
        await freshInit();

        expect(width()).toBe(MAX_WIDTH);
        expect(
            document.getElementById('sidebar-resizer').getAttribute('aria-valuenow')
        ).toBe(String(MAX_WIDTH));
    });

    it('leaves unrelated keys alone so the sidebar still scrolls', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        const start = width();

        expect(press(resizer, 'ArrowDown')).toBe(false);
        expect(press(resizer, 'PageDown')).toBe(false);
        expect(press(resizer, 'a')).toBe(false);
        expect(width()).toBe(start);
    });

    it('ignores arrow keys combined with Alt, Ctrl or Meta', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        const start = width();

        expect(press(resizer, 'ArrowRight', { altKey: true })).toBe(false);
        expect(press(resizer, 'ArrowRight', { ctrlKey: true })).toBe(false);
        expect(press(resizer, 'ArrowRight', { metaKey: true })).toBe(false);
        expect(width()).toBe(start);
    });
});

describe('sidebar resizer pointer support', () => {
    it('applies the dragged width and saves it on release', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        resizer.dispatchEvent(new window.MouseEvent('mousedown', { bubbles: true }));
        document.dispatchEvent(
            new window.MouseEvent('mousemove', { bubbles: true, clientX: 500 })
        );
        expect(width()).toBe(500);

        document.dispatchEvent(new window.MouseEvent('mouseup', { bubbles: true }));
        expect(localStorage.getItem('sidebarWidth')).toBe('500');
    });

    it('clamps a drag beyond the bounds', async () => {
        const resizer = document.getElementById('sidebar-resizer');
        await freshInit();

        resizer.dispatchEvent(new window.MouseEvent('mousedown', { bubbles: true }));
        document.dispatchEvent(
            new window.MouseEvent('mousemove', { bubbles: true, clientX: 5000 })
        );
        expect(width()).toBe(MAX_WIDTH);

        document.dispatchEvent(
            new window.MouseEvent('mousemove', { bubbles: true, clientX: 1 })
        );
        expect(width()).toBe(MIN_WIDTH);
    });
});

describe('sidebar resizer stored-value validation', () => {
    it('ignores a corrupt stored width instead of breaking the layout', async () => {
        localStorage.setItem('sidebarWidth', 'not-a-number');
        await freshInit();

        // The stylesheet default still applies and is what gets announced.
        expect(width()).toBe(340);
        expect(
            document.getElementById('sidebar-resizer').getAttribute('aria-valuenow')
        ).toBe('340');
    });

    it('clamps an out-of-range stored width', async () => {
        localStorage.setItem('sidebarWidth', '9000');
        await freshInit();

        expect(width()).toBe(MAX_WIDTH);
    });
});
