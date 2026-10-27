/**
 * Regression tests for feature modals opening through the shared lifecycle.
 *
 * `showModal()` does four things a raw `el.style.display = 'flex'` does not:
 * it clears `aria-hidden` so assistive technology announces the dialog, it
 * remembers and later restores focus, it adds `body.modal-open` (the mobile
 * scroll lock), and it moves focus inside the dialog.
 *
 * The cleanup, preview/confirm sync, export, import and cover-generator
 * dialogs all flipped `display` directly. The dialogs still appeared, so
 * nothing looked wrong visually — but a screen reader saw a `role="dialog"`
 * that stayed `aria-hidden="true"` while visible, and on a phone the page
 * behind the dialog still scrolled.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const MODALS = `
  <button id="opener">open</button>

  <div id="cleanup-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <div id="cleanup-loading"></div>
    <div id="cleanup-content"></div>
    <div id="cleanup-error"></div>
    <div id="cleanup-list"></div>
    <span id="cleanup-count"></span>
    <button id="confirm-cleanup-btn"></button>
    <button class="close-modal-btn">x</button>
  </div>

  <div id="export-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <input type="radio" name="export-type" value="all" checked>
    <input type="radio" name="export-type" value="selective">
    <div id="export-groups-container"></div>
    <div id="export-selection-list"></div>
    <button class="close-modal-btn">x</button>
  </div>

  <div id="import-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <div id="import-step-1"></div>
    <div id="import-step-2"></div>
    <div id="cancel-import-top"></div>
  </div>

  <div id="preview-sync-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <div id="preview-sync-results"></div>
    <button class="close-modal-btn">x</button>
  </div>

  <div id="confirm-sync-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <span id="confirm-sync-group-count"></span>
    <button class="close-modal-btn">x</button>
  </div>

  <div id="cover-generator-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <input id="cover-text">
    <select id="cover-theme"><option value="modern-dark">a</option></select>
    <select id="cover-border-style"><option value="none">a</option></select>
    <input id="cover-border-color">
    <input id="cover-color-1">
    <input id="cover-color-2">
    <canvas id="cover-canvas"></canvas>
    <button class="close-modal-btn">x</button>
  </div>

  <div id="error-dialog-modal" class="modal" role="dialog" aria-hidden="true" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
  <div id="status-msg"></div>
`;

/** Rebuild the DOM so each test starts from closed dialogs. */
function mount() {
    document.body.innerHTML = MODALS;
    document.body.className = '';
}

/**
 * Assert the dialog is genuinely open: visible, announced, and scroll-locked.
 * @param {string} id dialog element id
 */
function expectOpen(id) {
    const el = document.getElementById(id);
    expect(el.style.display).toBe('flex');
    expect(el.getAttribute('aria-hidden')).toBeNull();
    expect(document.body.classList.contains('modal-open')).toBe(true);
}

beforeEach(() => {
    mount();
    vi.resetModules();
});

describe('feature modals use the shared lifecycle', () => {
    it('opens the cleanup dialog through showModal()', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            getCleanupItems: async () => ({ status: 'success', items: [] }),
            performCleanup: vi.fn(),
        }));
        const { openCleanupModal } = await import(
            '../../static/js/features/cleanup.js'
        );

        await openCleanupModal();

        expectOpen('cleanup-modal');
    });

    it('opens the export dialog through showModal()', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [], scheduler: {} };
        const { openExportModal } = await import(
            '../../static/js/features/export-import.js'
        );

        openExportModal();

        expectOpen('export-modal');
    });

    it('opens the import dialog through showModal()', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
        }));
        const { openImportModal } = await import(
            '../../static/js/features/export-import.js'
        );

        openImportModal();

        expectOpen('import-modal');
    });

    it('closes the import dialog through hideModal()', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
        }));
        const { openImportModal } = await import(
            '../../static/js/features/export-import.js'
        );
        const ui = await import('../../static/js/core/ui.js');

        openImportModal();
        ui.hideModal('import-modal');

        const el = document.getElementById('import-modal');
        expect(el.style.display).toBe('none');
        expect(el.getAttribute('aria-hidden')).toBe('true');
        expect(document.body.classList.contains('modal-open')).toBe(false);
    });

    it('opens the preview sync dialog through showModal()', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            apiPost: async () => ({
                status: 'success',
                results: [{ group: 'G', links: 1, items: [] }],
            }),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [{ name: 'G' }], scheduler: {} };
        const { previewSyncAll } = await import(
            '../../static/js/features/sync.js'
        );

        await previewSyncAll();

        expectOpen('preview-sync-modal');
    });

    it('opens the confirm sync dialog through showModal()', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            apiPost: vi.fn(),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [{ name: 'G' }], scheduler: {} };
        const { showConfirmSyncDialog } = await import(
            '../../static/js/features/sync.js'
        );

        showConfirmSyncDialog();

        expectOpen('confirm-sync-modal');
    });

    it('opens the cover generator through showModal()', async () => {
        vi.doMock('../../static/js/core/api.js', () => ({
            saveConfig: vi.fn(),
            uploadCover: vi.fn(),
        }));
        const { state } = await import('../../static/js/core/state.js');
        state.currentConfig = { groups: [{ name: 'G' }], scheduler: {} };
        const { openCoverGenerator } = await import(
            '../../static/js/features/cover-generator.js'
        );

        openCoverGenerator(0);

        expectOpen('cover-generator-modal');
    });
});
