/**
 * @file Tests for the groupings feature module (CRUD operations for groupings:
 * render, edit, delete, clear, scheduler toggles, seasonal days, exclusions UI).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the metadata module to avoid deep DOM dependencies.
vi.mock('../../static/js/features/metadata.js', () => ({
  updateSourceTypeOptions: vi.fn(),
  updateSourceValueUI: vi.fn(),
  getFilterValue: vi.fn(),
}));

// Mock cover-generator so openCoverGenerator is observable.
vi.mock('../../static/js/features/cover-generator.js', () => ({
  openCoverGenerator: vi.fn(),
}));

// Mock the API module so saveConfig/apiPost are observable.
vi.mock('../../static/js/core/api.js', () => ({
  saveConfig: vi.fn(),
  apiPost: vi.fn(),
}));

// Mock the UI module so showToast/showConfirmDialog are observable.
vi.mock('../../static/js/core/ui.js', () => ({
  showToast: vi.fn(),
  getEl: vi.fn((id) => document.getElementById(id)),
  showErrorDialog: vi.fn(),
  showConfirmDialog: vi.fn(),
}));

// Import the mocked modules so we can assert on them.
import { saveConfig, apiPost } from '../../static/js/core/api.js';
import { showToast, showConfirmDialog } from '../../static/js/core/ui.js';
import { updateSourceTypeOptions, updateSourceValueUI } from '../../static/js/features/metadata.js';
import { openCoverGenerator } from '../../static/js/features/cover-generator.js';

/**
 * Set up the DOM elements that groupings.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="groups-list"></div>
    <span id="groups-count-badge"></span>
    <input id="groups-search" />
    <input id="group_name" />
    <select id="source_category"><option value="jellyfin">Jellyfin</option><option value="external">External</option></select>
    <select id="source_type"><option value="genre">Genre</option></select>
    <input id="sort_order_enabled" type="checkbox" />
    <div id="sort_order_panel"></div>
    <input id="sort_order" />
    <input id="schedule_enabled" type="checkbox" />
    <div id="group_scheduler_panel"></div>
    <input id="group_schedule" />
    <input id="seasonal_enabled" type="checkbox" />
    <div id="seasonal_panel"></div>
    <select id="seasonal_start_month"><option value="01">1</option><option value="02">2</option><option value="03">3</option><option value="11">11</option><option value="12">12</option></select>
    <select id="seasonal_start_day"></select>
    <select id="seasonal_end_month"><option value="01">1</option><option value="02">2</option><option value="03">3</option><option value="11">11</option><option value="12">12</option></select>
    <select id="seasonal_end_day"></select>
    <select id="watch_state"></select>
    <select id="item_type"></select>
    <input id="create_as_collection" type="checkbox" />
    <h2 id="group-form-title"></h2>
    <button id="add-group-btn"></button>
    <button id="cancel-edit-btn"></button>
    <form id="group-form"></form>
    <div id="global_sync_exclusions"></div>
  `;
  // jsdom does not implement scrollIntoView; provide a no-op stub.
  document.getElementById('group-form').scrollIntoView = () => {};
}

/**
 * Build a sample group object for tests.
 */
function makeGroup(overrides = {}) {
  return {
    name: 'Action',
    source_category: 'jellyfin',
    source_type: 'genre',
    source_value: 'Action',
    sort_order: 'SortName',
    seasonal_enabled: false,
    create_as_collection: false,
    schedule_enabled: false,
    ...overrides,
  };
}

describe('groupings module', () => {
  beforeEach(() => {
    setupDOM();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('should export the expected public functions', async () => {
    const mod = await import('../../static/js/features/groupings.js');
    expect(typeof mod.renderGroups).toBe('function');
    expect(typeof mod.initGroupSearch).toBe('function');
    expect(typeof mod.editGroup).toBe('function');
    expect(typeof mod.cancelEdit).toBe('function');
    expect(typeof mod.resetFormUI).toBe('function');
    expect(typeof mod.deleteGroup).toBe('function');
    expect(typeof mod.clearAllGroups).toBe('function');
    expect(typeof mod.toggleSortOrder).toBe('function');
    expect(typeof mod.toggleSeasonal).toBe('function');
    expect(typeof mod.toggleGroupScheduler).toBe('function');
    expect(typeof mod.populateSeasonalDays).toBe('function');
    expect(typeof mod.updateGlobalSyncExclusionsUI).toBe('function');
  });

  describe('renderGroups', () => {
    it('should render an empty state when there are no groups', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      const list = document.getElementById('groups-list');
      expect(list.querySelector('.groups-empty-state')).not.toBeNull();
      expect(document.getElementById('groups-count-badge').textContent).toBe('0');
    });

    it('should render a card per group with name, category, type and value', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      const list = document.getElementById('groups-list');
      const cards = list.querySelectorAll('.group-card');
      expect(cards.length).toBe(1);
      expect(cards[0].querySelector('h4').textContent).toContain('Action');
      expect(cards[0].querySelector('.group-category-label').textContent).toBe('Jellyfin');
      expect(cards[0].querySelector('.group-meta').textContent).toContain('Genre');
      expect(cards[0].querySelector('.group-meta').textContent).toContain('Action');
      expect(document.getElementById('groups-count-badge').textContent).toBe('1');
    });

    it('should render a sort badge when sort_order is set', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ sort_order: 'SortName' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      const badge = document.querySelector('.badge-sort');
      expect(badge).not.toBeNull();
      expect(badge.textContent).toBe('Name (A→Z)');
    });

    it('should render a seasonal badge when seasonal_enabled is set', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ seasonal_enabled: true, seasonal_start: '01-01', seasonal_end: '12-31' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      const badge = document.querySelector('.badge-seasonal');
      expect(badge).not.toBeNull();
      expect(badge.textContent).toBe('01-01 to 12-31');
    });

    it('should render a collection badge when create_as_collection is set', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ create_as_collection: true })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      expect(document.querySelector('.badge-collection')).not.toBeNull();
    });

    it('should filter groups by the search filter', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' }), makeGroup({ name: 'Comedy' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.initGroupSearch();
      // Set the internal search filter via the search input handler.
      const searchInput = document.getElementById('groups-search');
      searchInput.value = 'com';
      searchInput.dispatchEvent(new Event('input'));
      const cards = document.querySelectorAll('.group-card');
      expect(cards.length).toBe(1);
      expect(cards[0].querySelector('h4').textContent).toContain('Comedy');
      expect(document.getElementById('groups-count-badge').textContent).toBe('1/2');
    });

    it('should show a "no match" message when the filter matches nothing', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.initGroupSearch();
      const searchInput = document.getElementById('groups-search');
      searchInput.value = 'zzz';
      searchInput.dispatchEvent(new Event('input'));
      const list = document.getElementById('groups-list');
      expect(list.textContent).toContain('No groups match');
    });

    it('should wire the cover button to openCoverGenerator', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      const coverBtn = document.querySelector('.group-action-btn--cover');
      coverBtn.click();
      expect(openCoverGenerator).toHaveBeenCalledWith(0);
    });

    it('should label an external source category as External', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ source_category: 'external', source_type: 'imdb_list' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      expect(document.querySelector('.group-category-label').textContent).toBe('External');
    });

    it('should fall back to the raw source_type when the category is unknown', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ source_category: 'unknown_cat', source_type: 'mystery_type' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      expect(document.querySelector('.group-meta').textContent).toContain('mystery_type');
    });

    it('should fall back to the raw sort_order when it is not a known label', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ sort_order: 'CustomOrder' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      const badge = document.querySelector('.badge-sort');
      expect(badge).not.toBeNull();
      expect(badge.textContent).toBe('CustomOrder');
    });

    it('should not render sort/seasonal/collection badges when unset', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ sort_order: '', seasonal_enabled: false, create_as_collection: false })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      expect(document.querySelector('.badge-sort')).toBeNull();
      expect(document.querySelector('.badge-seasonal')).toBeNull();
      expect(document.querySelector('.badge-collection')).toBeNull();
    });

    it('should wire the delete button to deleteGroup', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      showConfirmDialog.mockResolvedValue(false);
      const mod = await import('../../static/js/features/groupings.js');
      mod.renderGroups();
      const delBtn = document.querySelector('.delete-btn');
      delBtn.click();
      expect(showConfirmDialog).toHaveBeenCalled();
      expect(state.currentConfig.groups.length).toBe(1);
    });
  });

  describe('updateGroupCount', () => {
    it('should no-op when the count badge element is missing', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      document.getElementById('groups-count-badge').remove();
      const mod = await import('../../static/js/features/groupings.js');
      expect(() => mod.renderGroups()).not.toThrow();
    });
  });

  describe('initGroupSearch', () => {
    it('should no-op when the search input is missing', async () => {
      document.getElementById('groups-search').remove();
      const mod = await import('../../static/js/features/groupings.js');
      expect(() => mod.initGroupSearch()).not.toThrow();
    });
  });

  describe('editGroup', () => {
    it('should populate the form fields from the group', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ sort_order: 'SortName', schedule_enabled: true, schedule: '0 3 * * *' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.populateSeasonalDays();
      mod.editGroup(0);
      expect(state.editingIndex).toBe(0);
      expect(document.getElementById('group_name').value).toBe('Action');
      expect(document.getElementById('source_category').value).toBe('jellyfin');
      expect(document.getElementById('source_type').value).toBe('genre');
      expect(document.getElementById('sort_order_enabled').checked).toBe(true);
      expect(document.getElementById('sort_order_panel').style.display).toBe('block');
      expect(document.getElementById('schedule_enabled').checked).toBe(true);
      expect(document.getElementById('group_scheduler_panel').style.display).toBe('block');
      expect(document.getElementById('group_schedule').value).toBe('0 3 * * *');
      expect(document.getElementById('group-form-title').textContent).toBe('Edit Grouping');
      expect(document.getElementById('add-group-btn').textContent).toBe('Update Grouping');
      expect(document.getElementById('cancel-edit-btn').style.display).toBe('block');
      expect(updateSourceTypeOptions).toHaveBeenCalled();
      expect(updateSourceValueUI).toHaveBeenCalledWith('Action');
    });

    it('should populate seasonal start/end when present', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ seasonal_enabled: true, seasonal_start: '03-15', seasonal_end: '11-20' })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.populateSeasonalDays();
      mod.editGroup(0);
      expect(document.getElementById('seasonal_start_month').value).toBe('03');
      expect(document.getElementById('seasonal_start_day').value).toBe('15');
      expect(document.getElementById('seasonal_end_month').value).toBe('11');
      expect(document.getElementById('seasonal_end_day').value).toBe('20');
    });

    it('should hide optional panels when the group has no sort/schedule/seasonal', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ sort_order: '', schedule_enabled: false, seasonal_enabled: false })];
      const mod = await import('../../static/js/features/groupings.js');
      mod.editGroup(0);
      expect(document.getElementById('sort_order_enabled').checked).toBe(false);
      expect(document.getElementById('sort_order_panel').style.display).toBe('none');
      expect(document.getElementById('schedule_enabled').checked).toBe(false);
      expect(document.getElementById('group_scheduler_panel').style.display).toBe('none');
      expect(document.getElementById('seasonal_enabled').checked).toBe(false);
      expect(document.getElementById('seasonal_panel').style.display).toBe('none');
    });
  });

  describe('cancelEdit / resetFormUI', () => {
    it('should reset the form and editing index', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.editingIndex = 2;
      const mod = await import('../../static/js/features/groupings.js');
      mod.cancelEdit();
      expect(state.editingIndex).toBe(-1);
      expect(document.getElementById('group-form-title').textContent).toBe('Create New Grouping');
      expect(document.getElementById('add-group-btn').textContent).toBe('Add Grouping');
      expect(document.getElementById('cancel-edit-btn').style.display).toBe('none');
      expect(document.getElementById('sort_order_panel').style.display).toBe('none');
      expect(document.getElementById('group_scheduler_panel').style.display).toBe('none');
      expect(document.getElementById('seasonal_panel').style.display).toBe('none');
    });
  });

  describe('deleteGroup', () => {
    it('should reject an invalid index', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      const mod = await import('../../static/js/features/groupings.js');
      await mod.deleteGroup(5);
      expect(showToast).toHaveBeenCalledWith('Invalid group index', 'error');
      expect(saveConfig).not.toHaveBeenCalled();
    });

    it('should delete a group after confirmation and save', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockResolvedValue({});
      apiPost.mockResolvedValue({});
      const mod = await import('../../static/js/features/groupings.js');
      await mod.deleteGroup(0);
      expect(state.currentConfig.groups.length).toBe(0);
      expect(saveConfig).toHaveBeenCalled();
      expect(apiPost).toHaveBeenCalledWith('/api/cleanup', { folders: ['Action'] });
    });

    it('should not delete when confirmation is declined', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      showConfirmDialog.mockResolvedValue(false);
      const mod = await import('../../static/js/features/groupings.js');
      await mod.deleteGroup(0);
      expect(state.currentConfig.groups.length).toBe(1);
      expect(saveConfig).not.toHaveBeenCalled();
    });

    it('should re-insert the group when save fails', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockRejectedValue(new Error('boom'));
      const mod = await import('../../static/js/features/groupings.js');
      await mod.deleteGroup(0);
      expect(state.currentConfig.groups.length).toBe(1);
      expect(state.currentConfig.groups[0].name).toBe('Action');
      expect(showToast).toHaveBeenCalledWith('Failed to save after deleting group', 'error');
    });

    it('should skip the disk cleanup when the group has no name', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: '' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockResolvedValue({});
      const mod = await import('../../static/js/features/groupings.js');
      await mod.deleteGroup(0);
      expect(saveConfig).toHaveBeenCalled();
      expect(apiPost).not.toHaveBeenCalled();
    });

    it('should toast when the disk cleanup fails', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockResolvedValue({});
      apiPost.mockRejectedValue(new Error('disk error'));
      const mod = await import('../../static/js/features/groupings.js');
      await mod.deleteGroup(0);
      expect(showToast).toHaveBeenCalledWith('Failed to clean up folder from disk: disk error', 'error');
    });

    it('should append the removed group when the array shrank during save failure', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' }), makeGroup({ name: 'Comedy' })];
      showConfirmDialog.mockResolvedValue(true);
      // Simulate the array being modified between splice and the save failure.
      saveConfig.mockImplementation(() => {
        state.currentConfig.groups.length = 0;
        return Promise.reject(new Error('boom'));
      });
      const mod = await import('../../static/js/features/groupings.js');
      // Delete the second group (index 1); after the array is emptied, index 1 > length 0.
      await mod.deleteGroup(1);
      // The removed group should be appended at the end rather than spliced in.
      expect(state.currentConfig.groups).toEqual([makeGroup({ name: 'Comedy' })]);
      expect(showToast).toHaveBeenCalledWith('Failed to save after deleting group', 'error');
    });
  });

  describe('clearAllGroups', () => {
    it('should clear all groups after confirmation and save', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' }), makeGroup({ name: 'Comedy' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockResolvedValue({});
      apiPost.mockResolvedValue({});
      const mod = await import('../../static/js/features/groupings.js');
      await mod.clearAllGroups();
      expect(state.currentConfig.groups.length).toBe(0);
      expect(saveConfig).toHaveBeenCalled();
      expect(apiPost).toHaveBeenCalledWith('/api/cleanup', { folders: ['Action', 'Comedy'] });
    });

    it('should restore groups when save fails', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockRejectedValue(new Error('boom'));
      const mod = await import('../../static/js/features/groupings.js');
      await mod.clearAllGroups();
      expect(state.currentConfig.groups.length).toBe(1);
      expect(showToast).toHaveBeenCalledWith('Failed to save after clearing groups', 'error');
    });

    it('should skip the disk cleanup when there are no named groups', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: '' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockResolvedValue({});
      const mod = await import('../../static/js/features/groupings.js');
      await mod.clearAllGroups();
      expect(saveConfig).toHaveBeenCalled();
      expect(apiPost).not.toHaveBeenCalled();
    });

    it('should toast when the disk cleanup fails', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      showConfirmDialog.mockResolvedValue(true);
      saveConfig.mockResolvedValue({});
      apiPost.mockRejectedValue(new Error('disk error'));
      const mod = await import('../../static/js/features/groupings.js');
      await mod.clearAllGroups();
      expect(showToast).toHaveBeenCalledWith('Failed to clean up folders from disk: disk error', 'error');
    });
  });

  describe('toggle helpers', () => {
    it('toggleSortOrder should show/hide the sort panel', async () => {
      const mod = await import('../../static/js/features/groupings.js');
      mod.toggleSortOrder({ checked: true });
      expect(document.getElementById('sort_order_panel').style.display).toBe('block');
      mod.toggleSortOrder({ checked: false });
      expect(document.getElementById('sort_order_panel').style.display).toBe('none');
    });

    it('toggleSeasonal should show/hide the seasonal panel', async () => {
      const mod = await import('../../static/js/features/groupings.js');
      mod.toggleSeasonal({ checked: true });
      expect(document.getElementById('seasonal_panel').style.display).toBe('block');
      mod.toggleSeasonal({ checked: false });
      expect(document.getElementById('seasonal_panel').style.display).toBe('none');
    });

    it('toggleGroupScheduler should show/hide the scheduler panel', async () => {
      const mod = await import('../../static/js/features/groupings.js');
      mod.toggleGroupScheduler({ checked: true });
      expect(document.getElementById('group_scheduler_panel').style.display).toBe('block');
      mod.toggleGroupScheduler({ checked: false });
      expect(document.getElementById('group_scheduler_panel').style.display).toBe('none');
    });
  });

  describe('populateSeasonalDays', () => {
    it('should populate 31 days in both selects', async () => {
      const mod = await import('../../static/js/features/groupings.js');
      mod.populateSeasonalDays();
      const startDay = document.getElementById('seasonal_start_day');
      const endDay = document.getElementById('seasonal_end_day');
      expect(startDay.options.length).toBe(31);
      expect(endDay.options.length).toBe(31);
      expect(startDay.options[0].value).toBe('01');
      expect(startDay.options[30].value).toBe('31');
    });
  });

  describe('updateGlobalSyncExclusionsUI', () => {
    it('should render a checkbox per named group and prune stale exclusions', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' }), makeGroup({ name: 'Comedy' })];
      state.currentConfig.scheduler = {
        global_enabled: false,
        global_schedule: '',
        global_exclude_ids: ['Action', 'StaleGroup'],
      };
      const mod = await import('../../static/js/features/groupings.js');
      mod.updateGlobalSyncExclusionsUI();
      const container = document.getElementById('global_sync_exclusions');
      const checkboxes = container.querySelectorAll('input[type="checkbox"]');
      expect(checkboxes.length).toBe(2);
      // StaleGroup should have been pruned.
      expect(state.currentConfig.scheduler.global_exclude_ids).toEqual(['Action']);
      // Action should be checked.
      expect(checkboxes[0].checked).toBe(true);
    });

    it('should show a placeholder when there are no groups', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [];
      const mod = await import('../../static/js/features/groupings.js');
      mod.updateGlobalSyncExclusionsUI();
      const container = document.getElementById('global_sync_exclusions');
      expect(container.textContent).toContain('No groups defined yet.');
    });

    it('should toggle exclusion membership on checkbox change', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      state.currentConfig.scheduler = { global_enabled: false, global_schedule: '', global_exclude_ids: [] };
      const mod = await import('../../static/js/features/groupings.js');
      mod.updateGlobalSyncExclusionsUI();
      const cb = document.querySelector('#global_sync_exclusions input[type="checkbox"]');
      cb.checked = true;
      cb.dispatchEvent(new Event('change'));
      expect(state.currentConfig.scheduler.global_exclude_ids).toEqual(['Action']);
      cb.checked = false;
      cb.dispatchEvent(new Event('change'));
      expect(state.currentConfig.scheduler.global_exclude_ids).toEqual([]);
    });

    it('should initialise a missing scheduler config', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      delete state.currentConfig.scheduler;
      const mod = await import('../../static/js/features/groupings.js');
      mod.updateGlobalSyncExclusionsUI();
      expect(state.currentConfig.scheduler).toEqual({
        global_enabled: false,
        global_schedule: '',
        global_exclude_ids: [],
      });
    });

    it('should initialise a missing global_exclude_ids array', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: 'Action' })];
      state.currentConfig.scheduler = { global_enabled: false, global_schedule: '' };
      const mod = await import('../../static/js/features/groupings.js');
      mod.updateGlobalSyncExclusionsUI();
      expect(state.currentConfig.scheduler.global_exclude_ids).toEqual([]);
    });

    it('should skip groups without a name when rendering exclusions', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ name: '' }), makeGroup({ name: 'Action' })];
      state.currentConfig.scheduler = { global_enabled: false, global_schedule: '', global_exclude_ids: [] };
      const mod = await import('../../static/js/features/groupings.js');
      mod.updateGlobalSyncExclusionsUI();
      const checkboxes = document.querySelectorAll('#global_sync_exclusions input[type="checkbox"]');
      expect(checkboxes.length).toBe(1);
      expect(checkboxes[0].nextSibling.textContent).toBe('Action');
    });
  });
});
