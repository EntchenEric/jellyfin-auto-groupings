/**
 * @file Tests for the export-import feature module (export-import.js).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Set up the DOM elements that export-import.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="status-msg"></div>
    <div id="error-dialog-modal" class="modal">
      <div id="error-dialog-message"></div>
    </div>
    <div id="export-modal" class="modal" style="display:none"></div>
    <div id="export-groups-container"></div>
    <div id="export-selection-list" style="display:none"></div>
    <input type="radio" name="export-type" value="all" checked>
    <input type="radio" name="export-type" value="selective">
    <div id="import-modal" class="modal" style="display:none"></div>
    <div id="import-step-1" style="display:none"></div>
    <div id="import-step-2" style="display:none"></div>
    <div id="cancel-import-top" style="display:none"></div>
    <div id="import-warning" style="display:none"></div>
    <div id="import-selection-list" style="display:none"></div>
    <div id="import-groups-container"></div>
    <button id="confirm-import"></button>
  `;
}

describe('export-import feature module', () => {
  beforeEach(() => {
    setupDOM();
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('should export the expected functions', async () => {
    const mod = await import('../../static/js/features/export-import.js');
    expect(typeof mod.openExportModal).toBe('function');
    expect(typeof mod.toggleExportSelection).toBe('function');
    expect(typeof mod.execExport).toBe('function');
    expect(typeof mod.openImportModal).toBe('function');
    expect(typeof mod.handleFileSelected).toBe('function');
    expect(typeof mod.initExportImport).toBe('function');
  });

  it('openExportModal should render groups and show modal', async () => {
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = {
      groups: [
        { name: 'Action', source_type: 'genre' },
        { name: 'Drama', source_type: 'studio' },
      ],
    };

    const mod = await import('../../static/js/features/export-import.js');
    mod.openExportModal();

    const container = document.getElementById('export-groups-container');
    expect(container.querySelectorAll('.modal-item').length).toBe(2);
    expect(container.querySelector('.item-name').textContent).toBe('Action');
    expect(document.getElementById('export-modal').style.display).toBe('flex');
  });

  it('openExportModal should show empty message when no groups', async () => {
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = { groups: [] };

    const mod = await import('../../static/js/features/export-import.js');
    mod.openExportModal();

    const container = document.getElementById('export-groups-container');
    expect(container.textContent).toContain('No groups available to export.');
  });

  it('toggleExportSelection should show/hide selection list', async () => {
    const mod = await import('../../static/js/features/export-import.js');
    document.querySelector('input[name="export-type"][value="all"]').checked = true;
    mod.toggleExportSelection();
    expect(document.getElementById('export-selection-list').style.display).toBe('none');

    document.querySelector('input[name="export-type"][value="selective"]').checked = true;
    mod.toggleExportSelection();
    expect(document.getElementById('export-selection-list').style.display).toBe('block');
  });

  it('execExport with "all" should download full config', async () => {
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = { groups: [{ name: 'Action' }], jellyfin_url: 'http://x' };

    // jsdom does not implement URL.createObjectURL
    const createObjectURL = vi.fn(() => 'blob:mock');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });

    const mod = await import('../../static/js/features/export-import.js');
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    mod.execExport();

    expect(clickSpy).toHaveBeenCalled();
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
    expect(document.getElementById('export-modal').style.display).toBe('none');
    clickSpy.mockRestore();
  });

  it('execExport with selective and no selection should show error', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    document.querySelector('input[name="export-type"][value="selective"]').checked = true;
    document.getElementById('export-groups-container').innerHTML = `
      <input type="checkbox" class="export-check item-checkbox">
    `;

    const mod = await import('../../static/js/features/export-import.js');
    mod.execExport();
    expect(showErrorDialog).toHaveBeenCalledWith('Please select at least one grouping.');
  });

  it('openImportModal should reset state and show step 1', async () => {
    const mod = await import('../../static/js/features/export-import.js');
    mod.openImportModal();

    expect(document.getElementById('import-step-1').style.display).toBe('block');
    expect(document.getElementById('import-step-2').style.display).toBe('none');
    expect(document.getElementById('import-modal').style.display).toBe('flex');
  });

  it('handleFileSelected should parse valid JSON groups', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    // Mock FileReader so onload fires synchronously with the file text
    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File([JSON.stringify({ groups: [{ name: 'Action', source_type: 'genre', source_value: 'Action' }] })], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    // Trigger the onload callback synchronously
    mockReader.onload({ target: { result: JSON.stringify({ groups: [{ name: 'Action', source_type: 'genre', source_value: 'Action' }] }) } });

    const stateMod = await import('../../static/js/core/state.js');
    expect(stateMod.state.pendingImportData.groups.length).toBe(1);
    expect(document.getElementById('import-step-2').style.display).toBe('flex');
    expect(document.getElementById('import-groups-container').querySelectorAll('.modal-item').length).toBe(1);
    expect(showErrorDialog).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should show error for invalid JSON', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File(['not json'], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({ target: { result: 'not json' } });

    expect(showErrorDialog).toHaveBeenCalledWith('Invalid JSON file — please check the file format');
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should show error for empty file', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File(['   '], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({ target: { result: '   ' } });

    expect(showErrorDialog).toHaveBeenCalledWith('The selected file is empty');
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should do nothing when no file', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mod = await import('../../static/js/features/export-import.js');
    mod.handleFileSelected({ target: { files: [] } });
    expect(showErrorDialog).not.toHaveBeenCalled();
  });
});
