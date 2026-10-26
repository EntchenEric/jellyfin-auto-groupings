/**
 * Regression tests for the "Release Year" source type.
 *
 * The backend has always accepted `year` groups and `_match_year()` has always
 * understood comparison expressions, but the source-type dropdown never
 * offered `year` and the complex-rule editor never offered a way to type a
 * year. Both are now exposed: `year` is a first-class source option and its
 * value is a free-form text field (a literal year, a comma-separated list, or
 * a comparison) rather than a dropdown populated from the metadata endpoint,
 * which has no year list.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const FORM = `
  <select id="source_category">
    <option value="jellyfin">Jellyfin</option>
    <option value="external">External</option>
  </select>
  <select id="source_type"></select>
  <input type="text" id="source_value">
  <div id="source_value_container"></div>
  <div id="source_value_help"></div>
  <div id="metadata_rules_container"></div>
  <button type="button" id="add-rule-btn"></button>
  <div id="status-msg"></div>
`;

async function mount() {
    document.body.innerHTML = FORM;
    vi.resetModules();
    const state = await import('../../static/js/core/state.js');
    const metadata = await import('../../static/js/features/metadata.js');
    return { state, metadata };
}

/** Option values of the source-type select, in order. */
function sourceTypeValues() {
    return Array.from(document.getElementById('source_type').options).map(
        (o) => o.value,
    );
}

describe('year source type', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('is offered as a Jellyfin source option', async () => {
        const { metadata } = await mount();
        metadata.updateSourceTypeOptions();
        expect(sourceTypeValues()).toContain('year');
    });

    it('is treated as a metadata type so the rule editor is used', async () => {
        const { state } = await mount();
        expect(state.metadataTypes).toContain('year');
    });

    it('does not parse a bare year as a complex query', async () => {
        const { metadata } = await mount();

        document.getElementById('source_type').innerHTML =
            '<option value="year" selected>Release Year</option>';
        document.getElementById('source_value').value = '2000';

        // A bare year is a literal Jellyfin `years` filter, not a rule
        // expression, so it must be sent through unchanged.
        expect(metadata.getFilterValue()).toBe('2000');
    });

    it('renders a text input, not an empty select, for a year rule', async () => {
        const { metadata } = await mount();

        document.getElementById('source_type').innerHTML =
            '<option value="complex" selected>Complex</option>';
        document.getElementById('source_value').value = 'year:>=2000';

        window._currentMetadataRules = [{ operator: '', type: 'year', value: '>=2000' }];
        metadata.renderMetadataRules();

        const row = document.querySelector('#metadata_rules_container .rule-value-input');
        expect(row).not.toBeNull();
        expect(row.tagName).toBe('INPUT');
        expect(row.value).toBe('>=2000');
    });

    it('offers year in the complex-rule type dropdown', async () => {
        const { metadata } = await mount();

        document.getElementById('source_type').innerHTML =
            '<option value="complex" selected>Complex</option>';
        window._currentMetadataRules = [{ operator: '', type: 'genre', value: 'Action' }];
        metadata.renderMetadataRules();

        const typeSelect = document.querySelector(
            '#metadata_rules_container .rule-type-select',
        );
        const values = Array.from(typeSelect.options).map((o) => o.value);
        expect(values).toContain('year');
    });

    it('parses a year-prefixed rule into type and value', async () => {
        const { metadata } = await mount();

        const rules = metadata.parseMetadataValue('genre:Horror AND year:>=2000');
        expect(rules).toEqual([
            { operator: '', type: 'genre', value: 'Horror' },
            { operator: 'AND', type: 'year', value: '>=2000' },
        ]);
    });
});
