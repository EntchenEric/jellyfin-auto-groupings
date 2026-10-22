/**
 * Regression tests for modal lifecycle and the authenticated folder picker.
 *
 * Both bugs were invisible to the Python suite because they live in the SPA:
 *
 * - `.close-modal-btn` set `display:none` directly instead of calling
 *   `hideModal()`, so `body.modal-open` (position:fixed on mobile) was never
 *   removed and the page stayed scroll-locked. It also left the closed
 *   dialog visible to assistive technology (no `aria-hidden`).
 * - The folder picker called raw `fetch()`, which sends no Basic-Auth
 *   header, so with `APP_PASSWORD` set every directory listed as "HTTP 401".
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const MODALS = `
  <button id="opener">open</button>
  <!--
    Inline display:none mirrors the .modal rule in components.css; the jsdom
    environment loads no stylesheet, so without it every closed modal would
    look visible to hideModal().
  -->
  <div id="wizard" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <button type="button" class="close-modal-btn" aria-label="Close">x</button>
  </div>
  <div id="second" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <button type="button" class="close-modal-btn" aria-label="Close">y</button>
  </div>
  <div id="status-msg"></div>
`;

/** Rebuild the DOM and re-import the modules so each test starts clean. */
async function mount(html = MODALS) {
    document.body.innerHTML = html;
    document.body.className = '';
    vi.resetModules();
    // Import for side effects: ui.js registers its document-level handlers
    // (Escape, backdrop click, .close-modal-btn) at module scope, and the
    // reset keeps each test from stacking a second copy on document.
    await import('../../static/js/core/ui.js');
}

describe('modal close button', () => {
    it('removes the scroll lock when the last modal closes', async () => {
        await mount();
        const ui = await import('../../static/js/core/ui.js');
        ui.showModal('wizard');
        expect(document.body.classList.contains('modal-open')).toBe(true);

        document
            .querySelector('#wizard .close-modal-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        expect(document.getElementById('wizard').style.display).toBe('none');
        expect(document.body.classList.contains('modal-open')).toBe(false);
    });

    it('keeps the lock while another modal is still open', async () => {
        await mount();
        const ui = await import('../../static/js/core/ui.js');
        ui.showModal('wizard');
        ui.showModal('second');

        document
            .querySelector('#second .close-modal-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        expect(document.body.classList.contains('modal-open')).toBe(true);
    });

    it('hides the closed dialog from assistive technology', async () => {
        await mount();
        const ui = await import('../../static/js/core/ui.js');
        ui.showModal('wizard');

        document
            .querySelector('#wizard .close-modal-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true }));

        expect(document.getElementById('wizard').getAttribute('aria-hidden')).toBe('true');
    });
});

describe('folder picker', () => {
    beforeEach(() => {
        sessionStorage.clear();
        vi.unstubAllGlobals();
    });

    it('sends the Basic auth header via the shared API client', async () => {
        await mount(`
          <div id="path-picker-modal" class="modal" aria-hidden="true" style="display: none">
            <p id="picker-title"></p>
            <div id="picker-breadcrumb"></div>
            <div id="picker-footer-path"></div>
            <div id="picker-body"></div>
          </div>
          <div id="status-msg"></div>
        `);
        sessionStorage.setItem('jfg_app_password', 's3cret');

        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => ({ status: 'success', current: '/media', parent: '/', dirs: ['Movies'] }),
        });
        vi.stubGlobal('fetch', fetchMock);

        const { browseDir } = await import('../../static/js/features/path-picker.js');
        await browseDir('/media');

        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [, options] = fetchMock.mock.calls[0];
        expect(options.headers.Authorization).toMatch(/^Basic /);
    });

    it('renders the server message inline instead of stacking a dialog', async () => {
        await mount(`
          <div id="path-picker-modal" class="modal" aria-hidden="true" style="display: none">
            <p id="picker-title"></p>
            <div id="picker-breadcrumb"></div>
            <div id="picker-footer-path"></div>
            <div id="picker-body"></div>
          </div>
          <div id="error-dialog-modal" class="modal" aria-hidden="true" style="display: none">
            <p id="error-dialog-message"></p>
          </div>
          <div id="status-msg"></div>
        `);

        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
            ok: false,
            status: 403,
            json: async () => ({ status: 'error', message: 'Access to this path is not permitted' }),
        }));

        const { browseDir } = await import('../../static/js/features/path-picker.js');
        await browseDir('/etc');

        expect(document.getElementById('picker-body').textContent).toContain('HTTP 403');
        expect(document.getElementById('picker-body').textContent).toContain(
            'Access to this path is not permitted'
        );
        // The picker owns the failure display; the error modal stays hidden.
        expect(document.getElementById('error-dialog-modal').style.display).not.toBe('flex');
    });
});

describe('Basic auth header encoding', () => {
    it('base64-encodes the password as UTF-8, not Latin-1', async () => {
        const { base64Utf8 } = await import('../../static/js/core/api.js');

        // "pässwort" -> UTF-8 bytes 70 c3 a4 ... ; btoa() alone would emit
        // the Latin-1 byte e4 and the server would never match it.
        expect(base64Utf8('user:pässwort')).toBe('dXNlcjpww6Rzc3dvcnQ=');
    });

    it('does not throw for characters outside Latin-1', async () => {
        const { base64Utf8 } = await import('../../static/js/core/api.js');

        // btoa('user:パスワード') raises InvalidCharacterError.
        expect(() => base64Utf8('user:パスワード')).not.toThrow();
        expect(base64Utf8('user:パスワード')).toBe('dXNlcjrjg5Hjgrnjg6/jg7zjg4k=');
    });
});
