/**
 * Regression tests for the accessible names of the metadata rule editor.
 *
 * `renderMetadataRules()` builds every control in a row at runtime: the
 * logical operator, the field selector (complex only), and the value control
 * (a <select> of cached metadata values, or a free-form <input> for years).
 * None of them carried a `<label>` or an `aria-label`, so a screen reader
 * walked a row announcing "combo box, combo box, combo box" with no way to
 * tell the operator from the field from the value — and with several
 * conditions the rows were indistinguishable from each other.
 *
 * `tests/test_template_accessibility.py` now fails on any runtime-created
 * control without a name, but that guard only reads source text; these tests
 * assert the names a user actually gets, including the condition number.
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
    document.getElementById('source_type').innerHTML =
        '<option value="complex" selected>Complex</option>';
    state.state.cachedMetadata = {
        genre: ['Action', 'Horror'],
        actor: ['Someone'],
        studio: ['A Studio'],
        tag: ['a-tag'],
    };
    return { state, metadata };
}

/** The three controls of the nth rule row (0-based). */
function rowControls(index) {
    return document.querySelectorAll('#metadata_rules_container .rule-row')[index]
        .querySelectorAll('select, input');
}

describe('metadata rule row accessible names', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('names the operator and field of a multi-condition row', async () => {
        const { metadata } = await mount();

        window._currentMetadataRules = [
            { operator: '', type: 'genre', value: 'Action' },
            { operator: 'AND', type: 'tag', value: 'a-tag' },
        ];
        metadata.renderMetadataRules();

        const controls = rowControls(1);
        expect(controls[0].className).toBe('rule-operator-select');
        expect(controls[0].getAttribute('aria-label')).toBe('Condition 2 operator');
        expect(controls[1].className).toBe('rule-type-select');
        expect(controls[1].getAttribute('aria-label')).toBe('Condition 2 field');
        expect(controls[2].className).toBe('rule-value-select');
        expect(controls[2].getAttribute('aria-label')).toBe('Condition 2 tag value');
    });

    it('names the value control of the first row too', async () => {
        const { metadata } = await mount();

        window._currentMetadataRules = [{ operator: '', type: 'genre', value: 'Action' }];
        metadata.renderMetadataRules();

        const controls = rowControls(0);
        // The first row has no operator select: field then value.
        expect(controls[0].getAttribute('aria-label')).toBe('Condition 1 field');
        expect(controls[1].getAttribute('aria-label')).toBe('Condition 1 genre value');
    });

    it('names a free-form year input', async () => {
        const { metadata } = await mount();

        window._currentMetadataRules = [
            { operator: '', type: 'year', value: '>=2000' },
        ];
        metadata.renderMetadataRules();

        const input = document.querySelector('#metadata_rules_container .rule-value-input');
        expect(input).not.toBeNull();
        expect(input.getAttribute('aria-label')).toBe('Condition 1 year value');
    });

    it('follows the selected type when a row field changes', async () => {
        const { metadata } = await mount();

        window._currentMetadataRules = [
            { operator: '', type: 'genre', value: 'Action' },
            { operator: 'AND', type: 'genre', value: 'Horror' },
        ];
        metadata.renderMetadataRules();

        const typeSelect = rowControls(1)[1];
        typeSelect.value = 'studio';
        typeSelect.dispatchEvent(new Event('change'));

        const renamed = rowControls(1)[2];
        expect(renamed.getAttribute('aria-label')).toBe('Condition 2 studio value');
    });
});
