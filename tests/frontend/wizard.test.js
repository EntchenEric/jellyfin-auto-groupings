/**
 * @file Tests for the wizard feature module (wizard.js).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Set up the DOM elements that wizard.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="status-msg"></div>
    <div id="error-dialog-modal" class="modal">
      <div id="error-dialog-message"></div>
    </div>
    <div id="setup-wizard-modal" class="modal" style="display:none"></div>
    <input id="wizard_jellyfin_url" />
    <input id="wizard_api_key" />
    <input id="wizard_media_path_in_jellyfin" />
    <input id="wizard_media_path_on_host" />
    <input id="wizard_target_path" />
    <div id="wizard-step-1"></div>
    <div id="wizard-step-2"></div>
    <div id="wizard-step-3"></div>
    <div id="wizard-step-4"></div>
    <div id="wizard-progress-bar"></div>
    <button id="wizard-back"></button>
    <button id="wizard-next"></button>
    <button id="wizard-test-btn"></button>
    <button id="wizard-detect-btn"></button>
    <div id="wizard-conn-status"></div>
    <div id="badge-j-path" style="display:none"></div>
    <div id="badge-h-path" style="display:none"></div>
    <div id="badge-t-path" style="display:none"></div>
  `;
}

describe('wizard feature module', () => {
  beforeEach(() => {
    setupDOM();
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should export the expected functions', async () => {
    const mod = await import('../../static/js/features/wizard.js');
    expect(typeof mod.openWizardManual).toBe('function');
    expect(typeof mod.wizardNext).toBe('function');
    expect(typeof mod.wizardPrev).toBe('function');
    expect(typeof mod.testWizardConnection).toBe('function');
    expect(typeof mod.runWizardAutoDetect).toBe('function');
    expect(typeof mod.initWizard).toBe('function');
  });

  it('openWizardManual should populate fields and show modal', async () => {
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = {
      jellyfin_url: 'http://jf',
      api_key: 'key',
      media_path_in_jellyfin: '/media',
      media_path_on_host: '/host',
      target_path: '/target',
    };

    const mod = await import('../../static/js/features/wizard.js');
    mod.openWizardManual();

    expect(document.getElementById('wizard_jellyfin_url').value).toBe('http://jf');
    expect(document.getElementById('wizard_api_key').value).toBe('key');
    expect(document.getElementById('wizard_media_path_in_jellyfin').value).toBe('/media');
    expect(document.getElementById('wizard_media_path_on_host').value).toBe('/host');
    expect(document.getElementById('wizard_target_path').value).toBe('/target');
    expect(document.getElementById('wizard-step-1').classList.contains('active')).toBe(true);
  });

  it('wizardNext and wizardPrev should step through the wizard', async () => {
    const mod = await import('../../static/js/features/wizard.js');
    mod.openWizardManual();

    mod.wizardNext();
    expect(document.getElementById('wizard-step-2').classList.contains('active')).toBe(true);
    expect(document.getElementById('wizard-back').style.visibility).toBe('visible');

    mod.wizardPrev();
    expect(document.getElementById('wizard-step-1').classList.contains('active')).toBe(true);
    expect(document.getElementById('wizard-back').style.visibility).toBe('hidden');
  });

  it('wizardNext should not advance past the last step', async () => {
    const mod = await import('../../static/js/features/wizard.js');
    mod.openWizardManual();
    mod.wizardNext();
    mod.wizardNext();
    mod.wizardNext();
    mod.wizardNext(); // attempt to go past step 4
    expect(document.getElementById('wizard-step-4').classList.contains('active')).toBe(true);
    expect(document.getElementById('wizard-next').textContent).toBe('Finish & Restart');
  });

  it('testWizardConnection should mark connected on success', async () => {
    vi.doMock('../../static/js/features/test-connection.js', () => ({
      testConnection: vi.fn().mockResolvedValue({ success: true, message: 'Connected!' }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog: vi.fn(),
      setLoading: vi.fn(),
      showModal: vi.fn(),
      hideModal: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    document.getElementById('wizard_jellyfin_url').value = 'http://jf';
    document.getElementById('wizard_api_key').value = 'key';

    const mod = await import('../../static/js/features/wizard.js');
    await mod.testWizardConnection();

    const statusDiv = document.getElementById('wizard-conn-status');
    expect(statusDiv.textContent).toBe('Connected successfully!');
    expect(statusDiv.className).toContain('success');
    expect(statusDiv.style.display).toBe('block');
  });

  it('testWizardConnection should show error on failure', async () => {
    vi.doMock('../../static/js/features/test-connection.js', () => ({
      testConnection: vi.fn().mockResolvedValue({ success: false, message: 'Bad key' }),
    }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog: vi.fn(),
      setLoading: vi.fn(),
      showModal: vi.fn(),
      hideModal: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/wizard.js');
    await mod.testWizardConnection();

    const statusDiv = document.getElementById('wizard-conn-status');
    expect(statusDiv.textContent).toBe('Bad key');
    expect(statusDiv.className).toContain('error');
  });

  it('runWizardAutoDetect should populate detected paths', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({}),
      autoDetectPaths: vi.fn().mockResolvedValue({
        status: 'success',
        detected: {
          media_path_in_jellyfin: '/detected/j',
          media_path_on_host: '/detected/h',
          target_path: '/detected/t',
        },
      }),
    }));
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      setLoading: vi.fn(),
      showModal: vi.fn(),
      hideModal: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/wizard.js');
    await mod.runWizardAutoDetect();

    expect(document.getElementById('wizard_media_path_in_jellyfin').value).toBe('/detected/j');
    expect(document.getElementById('wizard_media_path_on_host').value).toBe('/detected/h');
    expect(document.getElementById('wizard_target_path').value).toBe('/detected/t');
    expect(document.getElementById('badge-j-path').style.display).toBe('inline-flex');
    expect(showToast).toHaveBeenCalledWith('Paths detected!', 'success');
  });

  it('runWizardAutoDetect should show error when detection fails', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({}),
      autoDetectPaths: vi.fn().mockResolvedValue({ status: 'error', message: 'No paths' }),
    }));
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      setLoading: vi.fn(),
      showModal: vi.fn(),
      hideModal: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/wizard.js');
    await mod.runWizardAutoDetect();
    expect(showErrorDialog).toHaveBeenCalledWith('No paths');
  });

  it('runWizardAutoDetect should handle network errors', async () => {
    vi.doMock('../../static/js/core/api.js', () => ({
      apiPost: vi.fn().mockResolvedValue({}),
      autoDetectPaths: vi.fn().mockRejectedValue(new Error('Network down')),
    }));
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      setLoading: vi.fn(),
      showModal: vi.fn(),
      hideModal: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/wizard.js');
    await mod.runWizardAutoDetect();
    expect(showErrorDialog).toHaveBeenCalledWith('Auto-detect failed - network error');
  });
});
