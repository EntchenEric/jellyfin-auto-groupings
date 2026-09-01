/**
 * @file Tests for the config feature module (load/save config, form bindings,
 * scheduler toggles, cron validation, silent server test).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the metadata module to avoid deep DOM dependencies.
vi.mock('../../static/js/features/metadata.js', () => ({
  updateSourceTypeOptions: vi.fn(),
  updateSourceValueUI: vi.fn(),
  refreshMetadata: vi.fn(),
}));

// Mock groupings so renderGroups is a no-op we can assert on.
vi.mock('../../static/js/features/groupings.js', () => ({
  renderGroups: vi.fn(),
}));

// Mock test-connection so updateValidationUI is observable.
vi.mock('../../static/js/features/test-connection.js', () => ({
  updateValidationUI: vi.fn(),
}));

/**
 * Set up the DOM elements that config.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <input id="jellyfin_url" />
    <input id="api_key" />
    <input id="target_path" />
    <input id="media_path_in_jellyfin" />
    <input id="media_path_on_host" />
    <input id="trakt_client_id" />
    <input id="tmdb_api_key" />
    <input id="mal_client_id" />
    <input id="target_path_in_jellyfin" />
    <input id="auto_create_libraries" type="checkbox" />
    <input id="auto_set_library_covers" type="checkbox" />
    <input id="global_scheduler_enabled" type="checkbox" />
    <input id="global_sync_schedule" />
    <input id="cleanup_scheduler_enabled" type="checkbox" />
    <input id="cleanup_sync_schedule" />
    <div id="global_scheduler_panel"></div>
    <div id="cleanup_scheduler_panel"></div>
    <form id="config-form"></form>
    <button id="save-btn"></button>
    <form id="api-config-form"></form>
    <button id="save-apis-btn"></button>
    <div id="sidebar"></div>
    <div id="connection-warning"></div>
    <div id="env-override-warning"></div>
  `;
}

describe('config module', () => {
  beforeEach(() => {
    setupDOM();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('should export the expected public functions', async () => {
    const mod = await import('../../static/js/features/config.js');
    expect(typeof mod.loadConfig).toBe('function');
    expect(typeof mod.saveAllConfig).toBe('function');
    expect(typeof mod.performSilentTest).toBe('function');
    expect(typeof mod.toggleGlobalScheduler).toBe('function');
    expect(typeof mod.toggleCleanupScheduler).toBe('function');
    expect(typeof mod.syncDomToState).toBe('function');
    expect(typeof mod.initConfig).toBe('function');
  });

  describe('toggleGlobalScheduler', () => {
    it('should show the panel when checked', async () => {
      const mod = await import('../../static/js/features/config.js');
      const cb = { checked: true };
      mod.toggleGlobalScheduler(cb);
      expect(document.getElementById('global_scheduler_panel').style.display).toBe('block');
    });

    it('should hide the panel when unchecked', async () => {
      const mod = await import('../../static/js/features/config.js');
      const cb = { checked: false };
      mod.toggleGlobalScheduler(cb);
      expect(document.getElementById('global_scheduler_panel').style.display).toBe('none');
    });

    it('should no-op when the panel element is missing', async () => {
      document.getElementById('global_scheduler_panel').remove();
      const mod = await import('../../static/js/features/config.js');
      expect(() => mod.toggleGlobalScheduler({ checked: true })).not.toThrow();
    });
  });

  describe('toggleCleanupScheduler', () => {
    it('should show the panel when checked', async () => {
      const mod = await import('../../static/js/features/config.js');
      mod.toggleCleanupScheduler({ checked: true });
      expect(document.getElementById('cleanup_scheduler_panel').style.display).toBe('block');
    });

    it('should hide the panel when unchecked', async () => {
      const mod = await import('../../static/js/features/config.js');
      mod.toggleCleanupScheduler({ checked: false });
      expect(document.getElementById('cleanup_scheduler_panel').style.display).toBe('none');
    });
  });

  describe('syncDomToState', () => {
    it('should copy DOM field values into state.currentConfig', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = {};

      document.getElementById('jellyfin_url').value = 'http://jf:8096';
      document.getElementById('api_key').value = 'secret';
      document.getElementById('target_path').value = '/media';
      document.getElementById('media_path_in_jellyfin').value = '/movies';
      document.getElementById('media_path_on_host').value = '/mnt/movies';
      document.getElementById('target_path_in_jellyfin').value = '/groups';
      document.getElementById('trakt_client_id').value = 'trakt-id';
      document.getElementById('tmdb_api_key').value = 'tmdb-key';
      document.getElementById('mal_client_id').value = 'mal-id';
      document.getElementById('auto_create_libraries').checked = true;
      document.getElementById('auto_set_library_covers').checked = false;

      const mod = await import('../../static/js/features/config.js');
      mod.syncDomToState();

      expect(state.currentConfig.jellyfin_url).toBe('http://jf:8096');
      expect(state.currentConfig.api_key).toBe('secret');
      expect(state.currentConfig.target_path).toBe('/media');
      expect(state.currentConfig.media_path_in_jellyfin).toBe('/movies');
      expect(state.currentConfig.media_path_on_host).toBe('/mnt/movies');
      expect(state.currentConfig.target_path_in_jellyfin).toBe('/groups');
      expect(state.currentConfig.trakt_client_id).toBe('trakt-id');
      expect(state.currentConfig.tmdb_api_key).toBe('tmdb-key');
      expect(state.currentConfig.mal_client_id).toBe('mal-id');
      expect(state.currentConfig.auto_create_libraries).toBe(true);
      expect(state.currentConfig.auto_set_library_covers).toBe(false);
    });
  });

  describe('saveAllConfig', () => {
    it('should save config and show success toast on success', async () => {
      const showToast = vi.fn();
      const showErrorDialog = vi.fn();
      const saveConfig = vi.fn().mockResolvedValue(undefined);
      const renderGroups = vi.fn();
      const updateSourceTypeOptions = vi.fn();

      vi.doMock('../../static/js/core/ui.js', () => ({
        showToast,
        showErrorDialog,
        getEl: (id) => document.getElementById(id),
      }));
      vi.doMock('../../static/js/core/api.js', () => ({
        saveConfig,
        apiPost: vi.fn(),
      }));
      vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions,
        updateSourceValueUI: vi.fn(),
        refreshMetadata: vi.fn(),
      }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { groups: [], scheduler: {} };

      const mod = await import('../../static/js/features/config.js');
      await mod.saveAllConfig();

      expect(saveConfig).toHaveBeenCalledWith(state.currentConfig);
      expect(showToast).toHaveBeenCalledWith('Settings saved', 'success');
      expect(showErrorDialog).not.toHaveBeenCalled();
      expect(renderGroups).toHaveBeenCalled();
      expect(updateSourceTypeOptions).toHaveBeenCalled();
    });

    it('should reject an empty global schedule when global scheduler is enabled', async () => {
      const showErrorDialog = vi.fn();
      const saveConfig = vi.fn();

      vi.doMock('../../static/js/core/ui.js', () => ({
        showToast: vi.fn(),
        showErrorDialog,
        getEl: (id) => document.getElementById(id),
      }));
      vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { groups: [], scheduler: {} };

      document.getElementById('global_scheduler_enabled').checked = true;
      document.getElementById('global_sync_schedule').value = '';

      const mod = await import('../../static/js/features/config.js');
      await mod.saveAllConfig();

      expect(showErrorDialog).toHaveBeenCalledWith(expect.stringContaining('Global schedule'));
      expect(saveConfig).not.toHaveBeenCalled();
    });

    it('should reject a malformed global schedule (wrong field count)', async () => {
      const showErrorDialog = vi.fn();
      const saveConfig = vi.fn();

      vi.doMock('../../static/js/core/ui.js', () => ({
        showToast: vi.fn(),
        showErrorDialog,
        getEl: (id) => document.getElementById(id),
      }));
      vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { groups: [], scheduler: {} };

      document.getElementById('global_scheduler_enabled').checked = true;
      document.getElementById('global_sync_schedule').value = '0 0 * *';

      const mod = await import('../../static/js/features/config.js');
      await mod.saveAllConfig();

      expect(showErrorDialog).toHaveBeenCalledWith(expect.stringContaining('5 fields'));
      expect(saveConfig).not.toHaveBeenCalled();
    });

    it('should reject an invalid per-group schedule', async () => {
      const showErrorDialog = vi.fn();
      const saveConfig = vi.fn();

      vi.doMock('../../static/js/core/ui.js', () => ({
        showToast: vi.fn(),
        showErrorDialog,
        getEl: (id) => document.getElementById(id),
      }));
      vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = {
        groups: [{ name: 'Anime', schedule_enabled: true, schedule: 'bad' }],
        scheduler: {},
      };

      const mod = await import('../../static/js/features/config.js');
      await mod.saveAllConfig();

      expect(showErrorDialog).toHaveBeenCalledWith(expect.stringContaining("Group 'Anime'"));
      expect(saveConfig).not.toHaveBeenCalled();
    });

    it('should default cleanup schedule to hourly when empty', async () => {
      const saveConfig = vi.fn().mockResolvedValue(undefined);

      vi.doMock('../../static/js/core/ui.js', () => ({
        showToast: vi.fn(),
        showErrorDialog: vi.fn(),
        getEl: (id) => document.getElementById(id),
      }));
      vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { groups: [], scheduler: {} };

      document.getElementById('cleanup_scheduler_enabled').checked = true;
      document.getElementById('cleanup_sync_schedule').value = '';

      const mod = await import('../../static/js/features/config.js');
      await mod.saveAllConfig();

      expect(state.currentConfig.scheduler.cleanup_schedule).toBe('0 * * * *');
      expect(saveConfig).toHaveBeenCalled();
    });
  });

  describe('performSilentTest', () => {
    it('should mark valid and refresh metadata on success', async () => {
      const updateValidationUI = vi.fn();
      const refreshMetadata = vi.fn();
      const apiPost = vi.fn().mockResolvedValue({ status: 'success' });

      vi.doMock('../../static/js/core/api.js', () => ({ apiPost }));
      vi.doMock('../../static/js/features/test-connection.js', () => ({ updateValidationUI }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions: vi.fn(),
        updateSourceValueUI: vi.fn(),
        refreshMetadata,
      }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { jellyfin_url: 'http://jf:8096', api_key: 'key' };

      const mod = await import('../../static/js/features/config.js');
      await mod.performSilentTest();

      expect(apiPost).toHaveBeenCalledWith('/api/test-server', {
        jellyfin_url: 'http://jf:8096',
        api_key: 'key',
      });
      expect(updateValidationUI).toHaveBeenCalledWith(true);
      expect(refreshMetadata).toHaveBeenCalled();
    });

    it('should mark invalid on API error status', async () => {
      const updateValidationUI = vi.fn();
      const refreshMetadata = vi.fn();
      const apiPost = vi.fn().mockResolvedValue({ status: 'error' });

      vi.doMock('../../static/js/core/api.js', () => ({ apiPost }));
      vi.doMock('../../static/js/features/test-connection.js', () => ({ updateValidationUI }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions: vi.fn(),
        updateSourceValueUI: vi.fn(),
        refreshMetadata,
      }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { jellyfin_url: 'http://jf:8096', api_key: 'key' };

      const mod = await import('../../static/js/features/config.js');
      await mod.performSilentTest();

      expect(updateValidationUI).toHaveBeenCalledWith(false);
      expect(refreshMetadata).not.toHaveBeenCalled();
    });

    it('should mark invalid on network failure', async () => {
      const updateValidationUI = vi.fn();
      const apiPost = vi.fn().mockRejectedValue(new Error('Network down'));

      vi.doMock('../../static/js/core/api.js', () => ({ apiPost }));
      vi.doMock('../../static/js/features/test-connection.js', () => ({ updateValidationUI }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { jellyfin_url: 'http://jf:8096', api_key: 'key' };

      const mod = await import('../../static/js/features/config.js');
      await mod.performSilentTest();

      expect(updateValidationUI).toHaveBeenCalledWith(false);
    });
  });

  describe('loadConfig', () => {
    it('should populate form fields and migrate legacy group data', async () => {
      const apiLoadConfig = vi.fn().mockResolvedValue({
        jellyfin_url: 'http://jf:8096',
        api_key: 'key',
        target_path: '/media',
        groups: [
          { name: 'G1', source_type: 'imdb_list' },
          { name: 'G2', source_type: 'people' },
          { name: 'G3', source_type: 'jellyfin_tag' },
        ],
      });
      const updateSourceTypeOptions = vi.fn();
      const renderGroups = vi.fn();
      const updateValidationUI = vi.fn();

      vi.doMock('../../static/js/core/api.js', () => ({
        loadConfig: apiLoadConfig,
        apiPost: vi.fn(),
      }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions,
        updateSourceValueUI: vi.fn(),
        refreshMetadata: vi.fn(),
      }));
      vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups }));
      vi.doMock('../../static/js/features/test-connection.js', () => ({ updateValidationUI }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = {};

      const mod = await import('../../static/js/features/config.js');
      await mod.loadConfig();

      expect(document.getElementById('jellyfin_url').value).toBe('http://jf:8096');
      expect(document.getElementById('api_key').value).toBe('key');
      expect(document.getElementById('target_path').value).toBe('/media');

      // Legacy migration: imdb_list -> external, people -> actor, jellyfin_tag -> tag
      expect(state.currentConfig.groups[0].source_category).toBe('external');
      expect(state.currentConfig.groups[1].source_category).toBe('jellyfin');
      expect(state.currentConfig.groups[1].source_type).toBe('actor');
      expect(state.currentConfig.groups[2].source_type).toBe('tag');
      // create_as_collection defaults to false
      expect(state.currentConfig.groups[0].create_as_collection).toBe(false);

      expect(updateSourceTypeOptions).toHaveBeenCalled();
      expect(renderGroups).toHaveBeenCalled();
    });

    it('should show an error dialog when loading fails', async () => {
      const showErrorDialog = vi.fn();
      vi.doMock('../../static/js/core/api.js', () => ({
        loadConfig: vi.fn().mockRejectedValue(new Error('boom')),
      }));
      vi.doMock('../../static/js/core/ui.js', () => ({
        showErrorDialog,
        getEl: (id) => document.getElementById(id),
      }));

      const mod = await import('../../static/js/features/config.js');
      await mod.loadConfig();

      expect(showErrorDialog).toHaveBeenCalledWith('Failed to load configuration');
    });

    it('should render an env override warning banner when overrides are active', async () => {
      const apiLoadConfig = vi.fn().mockResolvedValue({
        jellyfin_url: 'http://jf:8096',
        api_key: 'key',
        _active_env_overrides: {
          api_key: 'JELLYFIN_API_KEY',
          tmdb_api_key: 'TMDB_API_KEY',
          some_unknown_key: 'SOME_ENV',
        },
      });
      vi.doMock('../../static/js/core/api.js', () => ({
        loadConfig: apiLoadConfig,
        apiPost: vi.fn(),
      }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions: vi.fn(),
        updateSourceValueUI: vi.fn(),
        refreshMetadata: vi.fn(),
      }));
      vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups: vi.fn() }));
      vi.doMock('../../static/js/features/test-connection.js', () => ({ updateValidationUI: vi.fn() }));

      const mod = await import('../../static/js/features/config.js');
      await mod.loadConfig();

      const banner = document.getElementById('env-override-warning');
      expect(banner).not.toBeNull();
      expect(banner.className).toContain('status-msg info');
      const html = banner.innerHTML;
      // Known label mapping is applied.
      expect(html).toContain('Jellyfin API Key');
      expect(html).toContain('JELLYFIN_API_KEY');
      expect(html).toContain('TMDb API Key');
      expect(html).toContain('TMDB_API_KEY');
      // Unknown keys fall back to the raw key name.
      expect(html).toContain('some_unknown_key');
      expect(html).toContain('SOME_ENV');
    });

    it('should not render an env override banner when no overrides are active', async () => {
      const apiLoadConfig = vi.fn().mockResolvedValue({
        jellyfin_url: 'http://jf:8096',
        _active_env_overrides: {},
      });
      vi.doMock('../../static/js/core/api.js', () => ({
        loadConfig: apiLoadConfig,
        apiPost: vi.fn(),
      }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions: vi.fn(),
        updateSourceValueUI: vi.fn(),
        refreshMetadata: vi.fn(),
      }));
      vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups: vi.fn() }));
      vi.doMock('../../static/js/features/test-connection.js', () => ({ updateValidationUI: vi.fn() }));

      const mod = await import('../../static/js/features/config.js');
      await mod.loadConfig();

      expect(document.getElementById('env-override-warning')).toBeNull();
    });
  });

  describe('initConfig', () => {
    it('should wire up submit handlers on both forms', async () => {
      const setLoading = vi.fn();
      const showLoadingOverlay = vi.fn();
      const hideLoadingOverlay = vi.fn();
      const updateLoadingStatus = vi.fn();
      const refreshMetadata = vi.fn().mockResolvedValue(undefined);
      const saveConfig = vi.fn().mockResolvedValue(undefined);

      vi.doMock('../../static/js/core/ui.js', () => ({
        setLoading,
        showLoadingOverlay,
        hideLoadingOverlay,
        updateLoadingStatus,
        showToast: vi.fn(),
        showErrorDialog: vi.fn(),
        getEl: (id) => document.getElementById(id),
      }));
      vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions: vi.fn(),
        updateSourceValueUI: vi.fn(),
        refreshMetadata,
      }));
      vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups: vi.fn() }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { groups: [], scheduler: {} };

      const mod = await import('../../static/js/features/config.js');
      mod.initConfig();

      // Submit the main config form
      const configForm = document.getElementById('config-form');
      configForm.dispatchEvent(new Event('submit', { cancelable: true }));

      // Allow the async handler to run
      await new Promise((r) => setTimeout(r, 0));

      expect(saveConfig).toHaveBeenCalled();
      expect(setLoading).toHaveBeenCalled();
    });

    it('should wire up the API config form submit handler', async () => {
      const setLoading = vi.fn();
      const saveConfig = vi.fn().mockResolvedValue(undefined);

      vi.doMock('../../static/js/core/ui.js', () => ({
        setLoading,
        showLoadingOverlay: vi.fn(),
        hideLoadingOverlay: vi.fn(),
        updateLoadingStatus: vi.fn(),
        showToast: vi.fn(),
        showErrorDialog: vi.fn(),
        getEl: (id) => document.getElementById(id),
      }));
      vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));
      vi.doMock('../../static/js/features/metadata.js', () => ({
        updateSourceTypeOptions: vi.fn(),
        updateSourceValueUI: vi.fn(),
        refreshMetadata: vi.fn(),
      }));
      vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups: vi.fn() }));

      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig = { groups: [], scheduler: {} };

      const mod = await import('../../static/js/features/config.js');
      mod.initConfig();

      const apiForm = document.getElementById('api-config-form');
      apiForm.dispatchEvent(new Event('submit', { cancelable: true }));

      await new Promise((r) => setTimeout(r, 0));

      expect(saveConfig).toHaveBeenCalled();
      expect(setLoading).toHaveBeenCalledWith(expect.anything(), true);
      expect(setLoading).toHaveBeenCalledWith(expect.anything(), false);
    });
  });
});
