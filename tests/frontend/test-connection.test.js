/**
 * @file Tests for the test-connection feature module.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the metadata module to avoid deep DOM dependencies
vi.mock('../../static/js/features/metadata.js', () => ({
  updateSourceTypeOptions: vi.fn(),
  refreshMetadata: vi.fn(),
}));

/**
 * Set up the DOM elements that test-connection.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="status-dot"></div>
    <div id="status-text"></div>
    <div id="maintenance-card"></div>
    <div id="groupings-section"></div>
    <div id="scheduler-card"></div>
    <input id="target_path" />
    <input id="media_path_in_jellyfin" />
    <input id="media_path_on_host" />
    <input id="target_path_in_jellyfin" />
    <div id="target_path_group">
      <button>Browse</button>
    </div>
    <div id="media_path_in_jellyfin_group">
      <button>Browse</button>
    </div>
    <div id="media_path_on_host_group">
      <button>Browse</button>
    </div>
    <div id="target_path_in_jellyfin_group">
      <button>Browse</button>
    </div>
    <input id="jellyfin_url" />
    <input id="api_key" />
    <button id="test-btn"></button>
    <div id="status-msg"></div>
    <div id="error-dialog-modal" class="modal">
      <div id="error-dialog-message"></div>
      <button class="close-modal-btn">X</button>
    </div>
    <div id="loading-overlay">
      <div id="loading-overlay-title"></div>
      <div id="loading-overlay-status"></div>
      <div id="progress-bar-fill"></div>
      <div id="progress-percentage"></div>
      <div id="progress-eta" style="display:none"></div>
    </div>
    <select id="source_category"><option value="jellyfin">Jellyfin</option></select>
    <select id="source_type"></select>
  `;
}

describe('test-connection module', () => {
  beforeEach(() => {
    setupDOM();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('should export updateValidationUI and testConnection', async () => {
    const mod = await import('../../static/js/features/test-connection.js');
    expect(typeof mod.updateValidationUI).toBe('function');
    expect(typeof mod.testConnection).toBe('function');
    expect(typeof mod.testConnectionFromSidebar).toBe('function');
  });

  it('updateValidationUI(true) should set connected state', async () => {
    const mod = await import('../../static/js/features/test-connection.js');
    mod.updateValidationUI(true);

    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const maintenanceCard = document.getElementById('maintenance-card');

    expect(statusDot.className).toBe('connection-dot online');
    expect(statusText.textContent).toBe('Connected');
    expect(maintenanceCard.classList.contains('locked-section')).toBe(false);
  });

  it('updateValidationUI(false) should set disconnected state', async () => {
    const mod = await import('../../static/js/features/test-connection.js');
    mod.updateValidationUI(false);

    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const maintenanceCard = document.getElementById('maintenance-card');

    expect(statusDot.className).toBe('connection-dot offline');
    expect(statusText.textContent).toBe('Disconnected');
    expect(maintenanceCard.classList.contains('locked-section')).toBe(true);
  });

  it('updateValidationUI should disable path fields when disconnected', async () => {
    const mod = await import('../../static/js/features/test-connection.js');
    mod.updateValidationUI(false);

    const targetPath = document.getElementById('target_path');
    expect(targetPath.disabled).toBe(true);
  });

  it('updateValidationUI should enable path fields when connected', async () => {
    const mod = await import('../../static/js/features/test-connection.js');
    mod.updateValidationUI(true);

    const targetPath = document.getElementById('target_path');
    expect(targetPath.disabled).toBe(false);
  });

  it('testConnection should return success when API returns success', async () => {
    // Mock the testServer import
    vi.doMock('../../static/js/core/api.js', () => ({
      testServer: vi.fn().mockResolvedValue({ status: 'success', message: 'Connected!' }),
    }));

    const mod = await import('../../static/js/features/test-connection.js');
    const result = await mod.testConnection('http://test', 'key');
    expect(result.success).toBe(true);
    expect(result.message).toBe('Connected!');
  });

  it('testConnection should return failure when API returns error', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      testServer: vi.fn().mockResolvedValue({ status: 'error', message: 'Bad key' }),
    }));

    const mod = await import('../../static/js/features/test-connection.js');
    const result = await mod.testConnection('http://test', 'bad-key');
    expect(result.success).toBe(false);
    expect(result.message).toBe('Bad key');
  });

  it('testConnection should handle API exceptions gracefully', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      testServer: vi.fn().mockRejectedValue(new Error('Network error')),
    }));

    const mod = await import('../../static/js/features/test-connection.js');
    const result = await mod.testConnection('http://test', 'key');
    expect(result.success).toBe(false);
    expect(result.message).toBe('API unreachable');
  });

  it('testConnection should use fallback message when API error has no message', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      testServer: vi.fn().mockResolvedValue({ status: 'error' }),
    }));

    const mod = await import('../../static/js/features/test-connection.js');
    const result = await mod.testConnection('http://test', 'bad-key');
    expect(result.success).toBe(false);
    expect(result.message).toBe('Connection failed');
  });
});
