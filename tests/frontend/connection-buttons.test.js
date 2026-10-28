/**
 * Regression tests for the sidebar "Auto-Detect" and "Test" buttons.
 *
 * Both buttons were left without a handler when the inline `onclick`
 * attributes were dropped during the frontend modularisation. The modules
 * still exported `testConnectionFromSidebar()` and `autoDetectPaths()`, but
 * nothing imported or called them, so clicking either button did nothing at
 * all. Those are the only two controls that verify the entered URL/API key
 * and fill the path fields from a live server, so the whole connection-setup
 * flow was unreachable from the UI.
 *
 * The tests also cover the two failure paths that made a *wired* button look
 * broken: `testConnectionFromSidebar()` left the button spinning (no
 * `finally`) when the metadata refresh raised, and `autoDetectPaths()` threw
 * on a success body that carried no `detected` object.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const SIDEBAR = `
  <input id="jellyfin_url" value="http://jellyfin:8096">
  <input id="api_key" value="secret">
  <input id="target_path" value="/groupings">
  <input id="media_path_in_jellyfin">
  <input id="media_path_on_host">
  <input id="target_path_in_jellyfin">
  <input type="checkbox" id="global_scheduler_enabled">
  <input type="text" id="global_sync_schedule" value="0 3 * * *">
  <input type="checkbox" id="cleanup_scheduler_enabled">
  <input type="text" id="cleanup_sync_schedule" value="0 * * * *">
  <button type="button" id="test-btn"><span class="btn-text">Test</span></button>
  <button type="button" id="auto-detect-btn"><span class="btn-text">Auto-Detect</span></button>
  <div id="maintenance-card"></div>
  <div id="groupings-section"></div>
  <div id="scheduler-card"></div>
  <span id="status-dot"></span><span id="status-text"></span>
  <select id="source_category"><option value="jellyfin">jellyfin</option></select>
  <select id="source_type"></select>
  <input id="source_value">
  <div id="source_value_container"></div>
  <div id="source_value_help"></div>
  <div id="metadata_rules_container"></div>
  <button type="button" id="add-rule-btn"></button>
  <div id="groups-list"></div>
  <span id="groups-count-badge"></span>
  <div id="global_sync_exclusions"></div>
  <div id="status-msg"></div>
  <form id="config-form"></form>
  <form id="api-config-form"></form>
  <form id="group-form"></form>
  <div id="setup-wizard-modal" class="modal" style="display: none">
    <input id="wizard_jellyfin_url"><input id="wizard_api_key">
    <input id="wizard_media_path_in_jellyfin"><input id="wizard_media_path_on_host">
    <input id="wizard_target_path">
    <button type="button" id="wizard-test-btn"></button>
    <button type="button" id="wizard-detect-btn"></button>
    <button type="button" id="wizard-next"></button>
    <button type="button" id="wizard-back"></button>
    <div id="wizard-progress-bar"></div><div id="wizard-conn-status"></div>
    <div id="wizard-step-1"></div><div id="wizard-step-2"></div>
    <div id="wizard-step-3"></div><div id="wizard-step-4"></div>
  </div>
  <div id="error-dialog-modal" class="modal" style="display: none">
    <p id="error-dialog-message"></p>
  </div>
`;

const testBtn = () => document.getElementById('test-btn');
const detectBtn = () => document.getElementById('auto-detect-btn');

beforeEach(() => {
    document.body.innerHTML = SIDEBAR;
    vi.resetModules();
    vi.unstubAllGlobals();
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('sidebar connection buttons', () => {
    it('binds a handler to both buttons during bootstrap', async () => {
        // `bootstrap()` runs on DOMContentLoaded and would immediately fetch
        // config; capture the listener and invoke it explicitly instead.
        let bootstrap = null;
        const realAdd = document.addEventListener.bind(document);
        vi.spyOn(document, 'addEventListener').mockImplementation((type, fn, opts) => {
            if (type === 'DOMContentLoaded') bootstrap = fn;
            else realAdd(type, fn, opts);
        });
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true, status: 200,
            json: async () => ({ status: 'success', groups: [], scheduler: {} }),
        })));

        await import('../../static/js/app.js');
        expect(typeof bootstrap).toBe('function');
        await bootstrap();

        // Without these assignments the buttons are inert: a click does
        // nothing and the user has no way to validate the settings.
        expect(typeof testBtn().onclick).toBe('function');
        expect(typeof detectBtn().onclick).toBe('function');
    });

    it('clears the Test button loading state when the metadata refresh fails', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url) => {
            if (String(url).includes('/api/test-server')) {
                return {
                    ok: true, status: 200,
                    json: async () => ({ status: 'success', message: 'Connected' }),
                };
            }
            if (String(url).includes('/api/jellyfin/metadata')) {
                return {
                    ok: true, status: 200,
                    json: async () => ({ status: 'error', message: 'Server refused' }),
                };
            }
            return { ok: true, status: 200, json: async () => ({ status: 'success' }) };
        }));

        const { testConnectionFromSidebar } = await import(
            '../../static/js/features/test-connection.js'
        );

        await testConnectionFromSidebar();

        // The connection succeeded, so the failure must not escape as an
        // unhandled rejection, and the button must not stay spinning.
        expect(testBtn().classList.contains('btn-loading')).toBe(false);
        expect(document.getElementById('error-dialog-message').textContent)
            .toContain('loading metadata failed');
    });

    it('does not throw when auto-detect succeeds without a detected object', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true, status: 200,
            json: async () => ({ status: 'success' }),
        })));

        const { autoDetectPaths } = await import(
            '../../static/js/features/path-picker.js'
        );

        await expect(autoDetectPaths()).resolves.toBeUndefined();
        expect(detectBtn().classList.contains('btn-loading')).toBe(false);
        expect(document.getElementById('error-dialog-message').textContent)
            .toContain('could not find matching host paths');
    });

    it('does not throw when the auto-detect body is not an object', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true, status: 200,
            json: async () => null,
        })));

        const { autoDetectPaths } = await import(
            '../../static/js/features/path-picker.js'
        );

        await expect(autoDetectPaths()).resolves.toBeUndefined();
        expect(detectBtn().classList.contains('btn-loading')).toBe(false);
    });

    it('fills the path fields from a detected payload', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true, status: 200,
            json: async () => ({
                status: 'success',
                detected: {
                    media_path_in_jellyfin: '/media',
                    media_path_on_host: '/mnt/media',
                    target_path: '/mnt/groupings',
                    target_path_in_jellyfin: '/groupings',
                },
            }),
        })));

        const { autoDetectPaths } = await import(
            '../../static/js/features/path-picker.js'
        );

        await autoDetectPaths();

        expect(document.getElementById('media_path_on_host').value).toBe('/mnt/media');
        expect(document.getElementById('target_path').value).toBe('/mnt/groupings');
        expect(document.getElementById('target_path_in_jellyfin').value).toBe('/groupings');
        expect(detectBtn().classList.contains('btn-loading')).toBe(false);
    });
});
