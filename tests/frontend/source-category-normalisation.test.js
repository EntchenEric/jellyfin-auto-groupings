/**
 * Regression tests for unusable `source_category` values.
 *
 * `updateSourceTypeOptions()` read the select's value and indexed
 * `sourceOptions` with it directly. `config.json` is user-editable and an
 * import can come from a build with a different set of categories, so a group
 * can carry `"External"`, `" jellyfin"`, `42`, or a value from a future
 * release. Setting an unknown value on a `<select>` leaves it selectedIndex
 * -1, so `sourceOptions[value]` was `undefined` and the `.forEach` beneath it
 * threw `TypeError: Cannot read properties of undefined (reading 'forEach')`.
 *
 * The throw propagated out of `loadConfig()` — the dashboard reported "Failed
 * to load configuration" and rendered no groups at all — and out of
 * `editGroup()`, so every group's Edit button did nothing.
 *
 * The category is now resolved against the group's own `source_type`, which
 * is a reliable hint: `tmdb_list` only exists in the External list, so a
 * broken category beside it means External, not Jellyfin.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const FORM = `
  <select id="source_category">
    <option value="jellyfin">Jellyfin (Integrated)</option>
    <option value="external">External (3rd Party)</option>
  </select>
  <select id="source_type"></select>
  <input type="text" id="source_value">
  <div id="source_value_container"></div>
  <div id="source_value_help"></div>
  <div id="metadata_rules_container"></div>
  <button type="button" id="add-rule-btn"></button>
  <div id="status-msg"></div>
`;

async function mount(html = FORM) {
    document.body.innerHTML = html;
    vi.resetModules();
    const stateMod = await import('../../static/js/core/state.js');
    const metadata = await import('../../static/js/features/metadata.js');
    return { state: stateMod.state, stateMod, metadata };
}

/** Option values currently offered by the source-type select. */
function sourceTypeValues() {
    return Array.from(document.getElementById('source_type').options).map(
        (o) => o.value,
    );
}

describe('resolveSourceCategory', () => {
    it('keeps a known category', async () => {
        const { stateMod } = await mount();
        expect(stateMod.resolveSourceCategory('external')).toBe('external');
        expect(stateMod.resolveSourceCategory('jellyfin')).toBe('jellyfin');
    });

    it('infers external from a source type only the external list offers', async () => {
        const { stateMod } = await mount();
        expect(stateMod.resolveSourceCategory('External', 'tmdb_list')).toBe(
            'external',
        );
        expect(stateMod.resolveSourceCategory(undefined, 'imdb_list')).toBe(
            'external',
        );
    });

    it('infers jellyfin from a source type only Jellyfin offers', async () => {
        const { stateMod } = await mount();
        expect(stateMod.resolveSourceCategory('nonsense', 'genre')).toBe(
            'jellyfin',
        );
        expect(stateMod.resolveSourceCategory(42, 'complex')).toBe('jellyfin');
    });

    it('ignores surrounding whitespace and case in the hint', async () => {
        const { stateMod } = await mount();
        expect(stateMod.resolveSourceCategory(' Jellyfin ', '')).toBe(
            'jellyfin',
        );
        expect(stateMod.resolveSourceCategory(null, ' TMDb_List ')).toBe(
            'external',
        );
    });

    it('falls back to jellyfin when neither value is usable', async () => {
        const { stateMod } = await mount();
        expect(stateMod.resolveSourceCategory('not-a-category')).toBe(
            'jellyfin',
        );
        expect(stateMod.resolveSourceCategory(null, 'not-a-type')).toBe(
            'jellyfin',
        );
    });
});

describe('updateSourceTypeOptions with an unusable category', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('does not throw when the select holds an unknown value', async () => {
        const { metadata } = await mount();
        const select = document.getElementById('source_category');
        // Force the state a stored unknown value produces: no option matches.
        select.insertAdjacentHTML(
            'beforeend',
            '<option value="External">External</option>',
        );
        select.value = 'External';

        expect(() => metadata.updateSourceTypeOptions()).not.toThrow();
        expect(['jellyfin', 'external']).toContain(select.value);
        expect(sourceTypeValues().length).toBeGreaterThan(0);
    });

    it('rebuilds the list for the inferred category', async () => {
        const { metadata } = await mount();
        const select = document.getElementById('source_category');
        select.insertAdjacentHTML(
            'beforeend',
            '<option value="bogus">bogus</option>',
        );
        select.value = 'bogus';

        metadata.updateSourceTypeOptions('imdb_list');

        expect(select.value).toBe('external');
        expect(sourceTypeValues()).toContain('imdb_list');
        expect(sourceTypeValues()).not.toContain('genre');
    });

    it('does nothing when the category select is absent', async () => {
        const { metadata } = await mount(`
          <select id="source_type"></select>
          <div id="status-msg"></div>
        `);

        expect(() => metadata.updateSourceTypeOptions()).not.toThrow();
    });

    it('survives a non-string API key value in the config', async () => {
        const { metadata, state } = await mount();
        state.currentConfig = { tmdb_api_key: 12345, trakt_client_id: null };
        document.getElementById('source_category').value = 'external';

        expect(() => metadata.updateSourceTypeOptions()).not.toThrow();

        // Both keys are unusable as text, so both options stay disabled rather
        // than throwing on `.trim()`.
        const options = Array.from(document.getElementById('source_type').options);
        const tmdb = options.find((o) => o.value === 'tmdb_list');
        expect(tmdb.disabled).toBe(true);
    });
});
