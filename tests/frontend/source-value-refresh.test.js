/**
 * Regression tests for `updateSourceValueUI()` on a partial document.
 *
 * The function is called after a config save and from the wizard, not only
 * while the grouping form is mounted. It read `source_value`,
 * `source_value_help`, `metadata_rules_container`, and `add-rule-btn` and
 * dereferenced them immediately, so a refresh against a document without them
 * threw `TypeError: Cannot read properties of null (reading 'style')` and
 * aborted the whole post-save UI refresh — the group list and source-types
 * select were left stale even though the config had been saved.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const FULL_FORM = `
  <select id="source_category">
    <option value="jellyfin">jellyfin</option>
    <option value="external">external</option>
  </select>
  <select id="source_type"></select>
  <input type="text" id="source_value">
  <div id="source_value_container"></div>
  <div id="source_value_help"></div>
  <div id="metadata_rules_container"></div>
  <button type="button" id="add-rule-btn"></button>
  <div id="status-msg"></div>
`;

async function mount(html) {
    document.body.innerHTML = html;
    vi.resetModules();
    const state = await import('../../static/js/core/state.js');
    const metadata = await import('../../static/js/features/metadata.js');
    return { state, metadata };
}

describe('updateSourceValueUI on a partial document', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('does not throw when the grouping form is absent', async () => {
        const { metadata } = await mount(`
            <select id="source_type"></select>
            <div id="status-msg"></div>
        `);

        expect(() => metadata.updateSourceValueUI()).not.toThrow();
    });

    it('does not throw when only the help element is missing', async () => {
        const { metadata } = await mount(`
            <select id="source_type"></select>
            <input type="text" id="source_value">
            <div id="source_value_container"></div>
            <div id="metadata_rules_container"></div>
            <button type="button" id="add-rule-btn"></button>
        `);

        expect(() => metadata.updateSourceValueUI()).not.toThrow();
    });

    it('still updates the controls when the form is present', async () => {
        const { metadata } = await mount(FULL_FORM);
        const typeSelect = document.getElementById('source_type');
        const option = document.createElement('option');
        option.value = 'imdb_list';
        typeSelect.appendChild(option);
        typeSelect.value = 'imdb_list';

        metadata.updateSourceValueUI();

        expect(document.getElementById('source_value').style.display).toBe('block');
        expect(document.getElementById('source_value_help').textContent).toContain(
            'IMDb',
        );
    });

    it('leaves the source-value input enabled after a metadata refresh', async () => {
        const { metadata } = await mount(FULL_FORM);
        const typeSelect = document.getElementById('source_type');
        const option = document.createElement('option');
        option.value = 'imdb_list';
        typeSelect.appendChild(option);
        typeSelect.value = 'imdb_list';

        metadata.updateSourceValueUI();

        expect(document.getElementById('source_value').disabled).toBe(false);
        expect(document.getElementById('source_value').required).toBe(true);
    });
});
