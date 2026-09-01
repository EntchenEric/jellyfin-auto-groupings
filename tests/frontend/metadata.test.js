/**
 * @file Tests for the metadata feature module (metadata.js).
 *
 * Covers the pure/unit-testable logic: parseMetadataValue, getFilterValue,
 * updateSourceTypeOptions, renderMetadataRules, addMetadataRule,
 * updateSourceValueUI, refreshMetadata and previewGrouping.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the API and UI modules so we can exercise metadata.js in isolation.
vi.mock('../../static/js/core/api.js', () => ({
  fetchMetadata: vi.fn(),
  fetchUsers: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('../../static/js/core/ui.js', () => ({
  getEl: (id) => document.getElementById(id),
}));

// Import the mocked modules so we can assert on their calls.
import { fetchMetadata, fetchUsers, apiPost } from '../../static/js/core/api.js';
import * as metadata from '../../static/js/features/metadata.js';
import { state, sourceOptions, metadataTypes } from '../../static/js/core/state.js';

/**
 * Set up the DOM elements that metadata.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <select id="source_category">
      <option value="jellyfin">Jellyfin</option>
      <option value="external">External</option>
    </select>
    <select id="source_type">
      <option value="general">General</option>
      <option value="genre">Genre</option>
      <option value="actor">Actor</option>
      <option value="studio">Studio</option>
      <option value="tag">Tag</option>
      <option value="complex">Complex</option>
      <option value="recommendations">Recommendations</option>
      <option value="imdb_list">IMDb List</option>
      <option value="trakt_list">Trakt List</option>
      <option value="tmdb_list">TMDb List</option>
      <option value="anilist_list">AniList List</option>
      <option value="mal_list">MAL List</option>
      <option value="letterboxd_list">Letterboxd List</option>
    </select>
    <div id="source_value_container">
      <input id="source_value" />
    </div>
    <div id="source_value_help"></div>
    <div id="metadata_rules_container"></div>
    <button id="add-rule-btn"></button>
    <div id="preview_result"></div>
    <select id="watch_state"></select>
    <select id="item_type"></select>
  `;
}

describe('parseMetadataValue', () => {
  it('returns an empty rule for empty/whitespace input', () => {
    expect(metadata.parseMetadataValue('')).toEqual([{ operator: '', value: '' }]);
    expect(metadata.parseMetadataValue('   ')).toEqual([{ operator: '', value: '' }]);
    expect(metadata.parseMetadataValue(null)).toEqual([{ operator: '', value: '' }]);
  });

  it('parses a single plain value', () => {
    expect(metadata.parseMetadataValue('Action')).toEqual([{ operator: '', value: 'Action' }]);
  });

  it('parses a single typed value', () => {
    expect(metadata.parseMetadataValue('genre:Horror')).toEqual([
      { operator: '', type: 'genre', value: 'Horror' },
    ]);
  });

  it('parses AND/OR/NOT combinations with operators', () => {
    const result = metadata.parseMetadataValue('Horror AND Action OR NOT Comedy');
    expect(result).toEqual([
      { operator: '', value: 'Horror' },
      { operator: 'AND', value: 'Action' },
      { operator: 'OR NOT', value: 'Comedy' },
    ]);
  });

  it('parses typed values within a complex expression', () => {
    const result = metadata.parseMetadataValue('genre:Horror AND actor:Tom Hanks');
    expect(result).toEqual([
      { operator: '', type: 'genre', value: 'Horror' },
      { operator: 'AND', type: 'actor', value: 'Tom Hanks' },
    ]);
  });

  it('normalises operator whitespace/case', () => {
    const result = metadata.parseMetadataValue('a  and  b');
    expect(result[1].operator).toBe('AND');
  });
});

describe('getFilterValue', () => {
  beforeEach(() => {
    setupDOM();
    state.isServerValidated = false;
    window._currentMetadataRules = [{ operator: '', value: '' }];
  });

  it('returns the raw source_value for non-metadata types', () => {
    document.getElementById('source_type').value = 'imdb_list';
    document.getElementById('source_value').value = 'ls000024390';
    expect(metadata.getFilterValue()).toBe('ls000024390');
  });

  it('returns empty string when no valid rules exist for metadata type', () => {
    document.getElementById('source_type').value = 'genre';
    state.isServerValidated = true;
    window._currentMetadataRules = [{ operator: '', value: '' }];
    expect(metadata.getFilterValue()).toBe('');
  });

  it('builds a query string from valid rules for metadata type', () => {
    document.getElementById('source_type').value = 'genre';
    state.isServerValidated = true;
    window._currentMetadataRules = [
      { operator: '', value: 'Horror' },
      { operator: 'AND', value: 'Action' },
    ];
    expect(metadata.getFilterValue()).toBe('Horror AND Action');
  });

  it('prefixes rule types for complex queries', () => {
    document.getElementById('source_type').value = 'complex';
    state.isServerValidated = true;
    window._currentMetadataRules = [
      { operator: '', type: 'genre', value: 'Horror' },
      { operator: 'OR', type: 'actor', value: 'Tom Hanks' },
    ];
    expect(metadata.getFilterValue()).toBe('genre:Horror OR actor:Tom Hanks');
  });

  it('falls back to source_value when server is not validated', () => {
    document.getElementById('source_type').value = 'genre';
    state.isServerValidated = false;
    document.getElementById('source_value').value = 'manual value';
    expect(metadata.getFilterValue()).toBe('manual value');
  });
});

describe('updateSourceTypeOptions', () => {
  beforeEach(() => {
    setupDOM();
    state.currentConfig = {};
  });

  it('populates options for the jellyfin category', () => {
    document.getElementById('source_category').value = 'jellyfin';
    metadata.updateSourceTypeOptions();
    const typeSelect = document.getElementById('source_type');
    const values = Array.from(typeSelect.options).map((o) => o.value);
    expect(values).toEqual(sourceOptions.jellyfin.map((o) => o.value));
  });

  it('disables options whose required key is missing', () => {
    document.getElementById('source_category').value = 'external';
    state.currentConfig = { trakt_client_id: '' };
    metadata.updateSourceTypeOptions();
    const typeSelect = document.getElementById('source_type');
    const trakt = Array.from(typeSelect.options).find((o) => o.value === 'trakt_list');
    expect(trakt.disabled).toBe(true);
    expect(trakt.textContent).toContain('Trakt Client ID missing');
  });

  it('keeps current selection when still valid', () => {
    document.getElementById('source_category').value = 'jellyfin';
    const typeSelect = document.getElementById('source_type');
    typeSelect.value = 'genre';
    metadata.updateSourceTypeOptions();
    expect(typeSelect.value).toBe('genre');
  });

  it('selects the first valid option when current selection is invalid', () => {
    document.getElementById('source_category').value = 'jellyfin';
    const typeSelect = document.getElementById('source_type');
    typeSelect.value = 'nonexistent';
    metadata.updateSourceTypeOptions();
    expect(typeSelect.value).toBe('general');
  });
});

describe('renderMetadataRules', () => {
  beforeEach(() => {
    setupDOM();
    state.cachedMetadata = { genre: ['Horror', 'Action'], actor: ['Tom Hanks'] };
    document.getElementById('source_type').value = 'genre';
  });

  it('renders a single rule row for a simple type', () => {
    window._currentMetadataRules = [{ operator: '', value: 'Horror' }];
    metadata.renderMetadataRules();
    const container = document.getElementById('metadata_rules_container');
    expect(container.querySelectorAll('.rule-row').length).toBe(1);
    expect(container.querySelectorAll('.rule-value-select').length).toBe(1);
    // No operator select for the first row
    expect(container.querySelectorAll('.rule-operator-select').length).toBe(0);
  });

  it('renders operator selects and remove buttons for subsequent rows', () => {
    window._currentMetadataRules = [
      { operator: '', value: 'Horror' },
      { operator: 'AND', value: 'Action' },
    ];
    metadata.renderMetadataRules();
    const container = document.getElementById('metadata_rules_container');
    expect(container.querySelectorAll('.rule-row').length).toBe(2);
    expect(container.querySelectorAll('.rule-operator-select').length).toBe(1);
    expect(container.querySelectorAll('.rule-remove-btn').length).toBe(1);
  });

  it('renders type selects for complex rules', () => {
    document.getElementById('source_type').value = 'complex';
    window._currentMetadataRules = [{ operator: '', value: 'Horror' }];
    metadata.renderMetadataRules();
    const container = document.getElementById('metadata_rules_container');
    expect(container.querySelectorAll('.rule-type-select').length).toBe(1);
  });

  it('adds a custom option when the value is not in the cached metadata', () => {
    window._currentMetadataRules = [{ operator: '', value: 'Sci-Fi' }];
    metadata.renderMetadataRules();
    const container = document.getElementById('metadata_rules_container');
    const custom = Array.from(container.querySelectorAll('.rule-value-select option'))
      .find((o) => o.textContent.includes('Custom'));
    expect(custom).toBeTruthy();
  });

  it('remove button splices the rule and re-renders', () => {
    window._currentMetadataRules = [
      { operator: '', value: 'Horror' },
      { operator: 'AND', value: 'Action' },
    ];
    metadata.renderMetadataRules();
    const container = document.getElementById('metadata_rules_container');
    const rmBtn = container.querySelector('.rule-remove-btn');
    rmBtn.click();
    expect(window._currentMetadataRules.length).toBe(1);
    expect(container.querySelectorAll('.rule-row').length).toBe(1);
  });
});

describe('addMetadataRule', () => {
  beforeEach(() => {
    setupDOM();
    window._currentMetadataRules = [{ operator: '', value: 'Horror' }];
  });

  it('appends a new AND rule and re-renders', () => {
    metadata.addMetadataRule();
    expect(window._currentMetadataRules).toEqual([
      { operator: '', value: 'Horror' },
      { operator: 'AND', value: '' },
    ]);
    const container = document.getElementById('metadata_rules_container');
    expect(container.querySelectorAll('.rule-row').length).toBe(2);
  });
});

describe('updateSourceValueUI', () => {
  beforeEach(() => {
    setupDOM();
    state.isServerValidated = false;
    state.cachedMetadata = {};
    state.lastRenderedType = null;
    window._currentMetadataRules = [{ operator: '', value: '' }];
  });

  it('shows the manual input for non-metadata types', () => {
    document.getElementById('source_type').value = 'imdb_list';
    metadata.updateSourceValueUI();
    const input = document.getElementById('source_value');
    expect(input.style.display).toBe('block');
    expect(input.required).toBe(true);
    expect(document.getElementById('metadata_rules_container').style.display).toBe('none');
  });

  it('shows the rules container for metadata types when server is validated', () => {
    document.getElementById('source_type').value = 'genre';
    state.isServerValidated = true;
    metadata.updateSourceValueUI();
    const container = document.getElementById('metadata_rules_container');
    expect(container.style.display).toBe('flex');
    expect(document.getElementById('add-rule-btn').style.display).toBe('inline-block');
    expect(document.getElementById('source_value').style.display).toBe('none');
  });

  it('parses a preValue string into rules for a validated metadata type', () => {
    document.getElementById('source_type').value = 'genre';
    state.isServerValidated = true;
    metadata.updateSourceValueUI('Horror AND Action');
    expect(window._currentMetadataRules).toEqual([
      { operator: '', value: 'Horror' },
      { operator: 'AND', value: 'Action' },
    ]);
    expect(state.lastRenderedType).toBe('genre');
  });

  it('shows manual help text for metadata types when server is not validated', () => {
    document.getElementById('source_type').value = 'genre';
    state.isServerValidated = false;
    metadata.updateSourceValueUI();
    const help = document.getElementById('source_value_help');
    expect(help.innerHTML).toContain('Connect Jellyfin for autocompletion');
    expect(document.getElementById('metadata_rules_container').style.display).toBe('none');
  });

  it('sets placeholder and help for imdb_list', () => {
    document.getElementById('source_type').value = 'imdb_list';
    metadata.updateSourceValueUI();
    const input = document.getElementById('source_value');
    expect(input.placeholder).toContain('ls000024390');
    expect(document.getElementById('source_value_help').textContent).toContain('IMDb list ID');
  });

  it('pre-fills the manual input for non-metadata types when preValue is given', () => {
    document.getElementById('source_type').value = 'imdb_list';
    metadata.updateSourceValueUI('ls000024390');
    expect(document.getElementById('source_value').value).toBe('ls000024390');
  });

  it('uses the fallback placeholder and help for an unknown non-metadata type', () => {
    document.getElementById('source_type').value = 'some_unknown_type';
    metadata.updateSourceValueUI();
    const input = document.getElementById('source_value');
    expect(input.placeholder).toContain('e.g. Action');
    expect(document.getElementById('source_value_help').textContent).toContain('Enter the value manually.');
  });

  it('shows the manual input for recommendations when the server is not validated', () => {
    document.getElementById('source_type').value = 'recommendations';
    state.isServerValidated = false;
    metadata.updateSourceValueUI('u1');
    const input = document.getElementById('source_value');
    expect(input.style.display).toBe('block');
    expect(input.required).toBe(true);
    expect(input.value).toBe('u1');
    const userSel = document.getElementById('source_value_user_select');
    expect(userSel).toBeTruthy();
    expect(userSel.style.display).toBe('none');
  });

  it('pre-selects the matching user and dispatches change when preValue matches a user id', async () => {
    document.getElementById('source_type').value = 'recommendations';
    state.isServerValidated = true;
    fetchUsers.mockResolvedValue({
      status: 'success',
      users: [{ id: 'u1', name: 'Alice' }, { id: 'u2', name: 'Bob' }],
    });
    metadata.updateSourceValueUI('u2');
    await vi.waitFor(() => {
      const userSel = document.getElementById('source_value_user_select');
      expect(userSel).toBeTruthy();
      expect(userSel.value).toBe('u2');
    });
  });

  it('shows an error option when fetching users fails', async () => {
    document.getElementById('source_type').value = 'recommendations';
    state.isServerValidated = true;
    fetchUsers.mockRejectedValue(new Error('Network down'));
    metadata.updateSourceValueUI();
    await vi.waitFor(() => {
      const userSel = document.getElementById('source_value_user_select');
      expect(userSel).toBeTruthy();
      expect(userSel.innerHTML).toContain('Error loading users');
    });
  });

  it('populates the user select for recommendations when validated', async () => {
    document.getElementById('source_type').value = 'recommendations';
    state.isServerValidated = true;
    fetchUsers.mockResolvedValue({
      status: 'success',
      users: [{ id: 'u1', name: 'Alice' }, { id: 'u2', name: 'Bob' }],
    });
    metadata.updateSourceValueUI();
    // Wait for the async fetchUsers resolution
    await vi.waitFor(() => {
      const userSel = document.getElementById('source_value_user_select');
      expect(userSel).toBeTruthy();
      expect(userSel.options.length).toBeGreaterThan(1);
    });
  });
});

describe('initMetadata', () => {
  beforeEach(() => {
    setupDOM();
    state.currentConfig = {};
    state.isServerValidated = false;
    window._currentMetadataRules = [{ operator: '', value: '' }];
  });

  it('wires up the source category, type and add-rule handlers', () => {
    metadata.initMetadata();
    expect(window.updateSourceTypeOptions).toBe(metadata.updateSourceTypeOptions);
    expect(window.updateSourceValueUI).toBe(metadata.updateSourceValueUI);
    // Trigger the category change handler and verify it repopulates options.
    document.getElementById('source_category').value = 'jellyfin';
    document.getElementById('source_category').onchange();
    const typeSelect = document.getElementById('source_type');
    expect(typeSelect.options.length).toBeGreaterThan(0);
    // Trigger the add-rule handler and verify a rule is appended.
    document.getElementById('add-rule-btn').onclick();
    expect(window._currentMetadataRules.length).toBe(2);
  });
});

describe('refreshMetadata', () => {
  beforeEach(() => {
    setupDOM();
    state.cachedMetadata = {};
  });

  it('calls onStatus, caches metadata and updates UI on success', async () => {
    fetchMetadata.mockResolvedValue({ status: 'success', metadata: { genre: ['Horror'] } });
    const onStatus = vi.fn();
    document.getElementById('source_type').value = 'genre';
    await metadata.refreshMetadata(onStatus);
    expect(onStatus).toHaveBeenCalledWith('Fetching genres, actors, studios, and tags...');
    expect(state.cachedMetadata).toEqual({ genre: ['Horror'] });
  });

  it('throws when the server returns an error', async () => {
    fetchMetadata.mockResolvedValue({ status: 'error', message: 'Server down' });
    await expect(metadata.refreshMetadata()).rejects.toThrow('Server down');
  });

  it('throws a default message when no message is provided', async () => {
    fetchMetadata.mockResolvedValue({ status: 'error' });
    await expect(metadata.refreshMetadata()).rejects.toThrow('Failed to load metadata from Jellyfin server');
  });
});

describe('previewGrouping', () => {
  beforeEach(() => {
    setupDOM();
    state.isServerValidated = false;
    window._currentMetadataRules = [{ operator: '', value: '' }];
  });

  it('shows a message for unsupported source types', async () => {
    document.getElementById('source_type').value = 'some_unknown_type';
    document.getElementById('source_value').value = 'x';
    await metadata.previewGrouping();
    const result = document.getElementById('preview_result');
    expect(result.innerHTML).toContain('Preview not supported');
  });

  it('shows an error when no filter value is provided', async () => {
    document.getElementById('source_type').value = 'genre';
    document.getElementById('source_value').value = '';
    await metadata.previewGrouping();
    const result = document.getElementById('preview_result');
    expect(result.innerHTML).toContain('Please enter a filter value');
  });

  it('renders the item count and list on success', async () => {
    document.getElementById('source_type').value = 'genre';
    document.getElementById('source_value').value = 'Horror';
    apiPost.mockResolvedValue({
      status: 'success',
      count: 2,
      preview_items: [{ Name: 'The Shining', Year: 1980 }, { Name: 'Alien' }],
    });
    await metadata.previewGrouping();
    const result = document.getElementById('preview_result');
    expect(result.innerHTML).toContain('Estimated Items');
    expect(result.innerHTML).toContain('The Shining (1980)');
    expect(result.innerHTML).toContain('Alien');
  });

  it('renders an error message when the API returns an error', async () => {
    document.getElementById('source_type').value = 'genre';
    document.getElementById('source_value').value = 'Horror';
    apiPost.mockResolvedValue({ status: 'error', message: 'Preview failed' });
    await metadata.previewGrouping();
    const result = document.getElementById('preview_result');
    expect(result.innerHTML).toContain('Error: Preview failed');
  });

  it('renders a network error message when the API throws', async () => {
    document.getElementById('source_type').value = 'genre';
    document.getElementById('source_value').value = 'Horror';
    apiPost.mockRejectedValue(new Error('Network down'));
    await metadata.previewGrouping();
    const result = document.getElementById('preview_result');
    expect(result.innerHTML).toContain('Network error during preview');
  });
});
