/**
 * Regression tests for the "+ Add Condition" button's single binding.
 *
 * `initMetadata()` assigns `.onclick = addMetadataRule` and `app.js`'s
 * `wireGroupFormEvents()` also registered `addEventListener('click', ...)` on
 * the same element. Both bindings survive, so one click ran
 * `addMetadataRule()` twice and appended **two** empty condition rows to the
 * rule editor. The bug was invisible to the per-module tests: each one only
 * ever exercised its own binding, so both passed while the real page
 * double-added.
 *
 * `tests/test_frontend_double_bindings.py` now fails on the source shape.
 * These tests assert the behaviour a user gets: one click, one new row.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const FORM = `
  <select id="source_category">
    <option value="jellyfin">jellyfin</option>
    <option value="external">external</option>
  </select>
  <select id="source_type"><option value="genre" selected>Genre</option></select>
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
    state.state.cachedMetadata = { genre: ['Action', 'Horror'] };
    state.state.isServerValidated = true;
    state.state.lastRenderedType = 'genre';
    window._currentMetadataRules = [{ operator: '', value: '' }];
    metadata.initMetadata();
    metadata.renderMetadataRules();
    return { state, metadata };
}

function rules() {
    return window._currentMetadataRules;
}

function rows() {
    return document.querySelectorAll('#metadata_rules_container .rule-row');
}

describe('+ Add Condition', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('adds exactly one condition per click', async () => {
        await mount();

        document.getElementById('add-rule-btn').click();

        expect(rules()).toHaveLength(2);
        expect(rows()).toHaveLength(2);
    });

    it('keeps one condition per click over repeated clicks', async () => {
        await mount();

        const btn = document.getElementById('add-rule-btn');
        btn.click();
        btn.click();
        btn.click();

        expect(rules()).toHaveLength(4);
        expect(rows()).toHaveLength(4);
    });

    it('does not add a condition when the button is only initialised', async () => {
        await mount();

        expect(rules()).toHaveLength(1);
        expect(rows()).toHaveLength(1);
    });
});
