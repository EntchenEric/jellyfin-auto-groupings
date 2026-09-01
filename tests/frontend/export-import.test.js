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

  it('openExportModal should fall back to Unnamed Group for missing fields', async () => {
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = {
      groups: [{ name: '', source_type: '' }],
    };

    const mod = await import('../../static/js/features/export-import.js');
    mod.openExportModal();

    const container = document.getElementById('export-groups-container');
    expect(container.querySelector('.item-name').textContent).toBe('Unnamed Group');
    expect(container.querySelector('.item-type').textContent).toBe('');
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
    // Revoke happens asynchronously (setTimeout 0) to avoid aborting the download.
    await new Promise((r) => setTimeout(r, 0));
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

  it('handleFileSelected should render groups missing source_type/source_value', async () => {
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
    const file = new File([JSON.stringify({ groups: [{ name: 'Unnamed Group' }] })], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({ target: { result: JSON.stringify({ groups: [{ name: 'Unnamed Group' }] }) } });

    const container = document.getElementById('import-groups-container');
    expect(container.querySelectorAll('.modal-item').length).toBe(1);
    // The type/value fallback renders an empty string rather than "undefined"
    expect(container.querySelector('.item-type').textContent).toBe(': ');
    expect(showErrorDialog).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should fall back to Unnamed Group for a nameless imported group', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File([JSON.stringify({ groups: [{ source_type: 'genre', source_value: 'Action' }] })], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({ target: { result: JSON.stringify({ groups: [{ source_type: 'genre', source_value: 'Action' }] }) } });

    const container = document.getElementById('import-groups-container');
    expect(container.querySelector('.item-name').textContent).toBe('Unnamed Group');
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

  it('handleFileSelected should show a processing error for non-SyntaxError failures', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File(['null'], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    // JSON.parse('null') succeeds, but setupImportStep2(null) throws a TypeError.
    mockReader.onload({ target: { result: 'null' } });

    expect(showErrorDialog).toHaveBeenCalledWith(
      expect.stringContaining('Failed to process import file:')
    );
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

  it('execExport with selective and selected groups should download selected', async () => {
    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = {
      groups: [{ name: 'Action', source_type: 'genre' }, { name: 'Drama', source_type: 'studio' }],
    };

    const createObjectURL = vi.fn(() => 'blob:mock');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });

    document.querySelector('input[name="export-type"][value="selective"]').checked = true;
    document.getElementById('export-groups-container').innerHTML = `
      <input type="checkbox" class="export-check item-checkbox" data-index="0" checked>
      <input type="checkbox" class="export-check item-checkbox" data-index="1">
    `;

    const mod = await import('../../static/js/features/export-import.js');
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    mod.execExport();

    expect(clickSpy).toHaveBeenCalled();
    expect(createObjectURL).toHaveBeenCalled();
    // Revoke happens asynchronously (setTimeout 0) to avoid aborting the download.
    await new Promise((r) => setTimeout(r, 0));
    expect(revokeObjectURL).toHaveBeenCalled();
    expect(document.getElementById('export-modal').style.display).toBe('none');
    clickSpy.mockRestore();
  });

  it('handleFileSelected should show error when reader fails', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File(['{}'], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onerror();

    expect(showErrorDialog).toHaveBeenCalledWith('Failed to read the selected file');
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should show error for incompatible structure', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File(['{}'], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({ target: { result: '{}' } });

    expect(showErrorDialog).toHaveBeenCalledWith('Incompatible file structure');
    expect(document.getElementById('import-modal').style.display).toBe('none');
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should accept a raw array of groups', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File([JSON.stringify([{ name: 'Action' }])], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({ target: { result: JSON.stringify([{ name: 'Action' }]) } });

    const container = document.getElementById('import-groups-container');
    expect(container.querySelectorAll('.modal-item').length).toBe(1);
    expect(container.querySelector('.item-name').textContent).toBe('Action');
    expect(showErrorDialog).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should treat a partial config (url without api_key) as a groups-only import', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File(['{}'], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({
      target: { result: JSON.stringify({ jellyfin_url: 'http://jf', groups: [{ name: 'Action' }] }) },
    });

    // Not a full config (missing api_key), so it should fall through to the groups-only path.
    expect(document.getElementById('import-warning').style.display).toBe('none');
    expect(document.getElementById('import-selection-list').style.display).toBe('block');
    expect(document.getElementById('confirm-import').textContent).toBe('Import Selected');
    expect(showErrorDialog).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('handleFileSelected should handle full config import (Overwrite All)', async () => {
    const showErrorDialog = vi.fn();
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast: vi.fn(),
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));

    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));

    const mod = await import('../../static/js/features/export-import.js');
    const file = new File(['{}'], 'test.json', { type: 'application/json' });
    const event = { target: { files: [file], value: 'x' } };

    mod.handleFileSelected(event);
    mockReader.onload({
      target: { result: JSON.stringify({ jellyfin_url: 'http://jf', api_key: 'key', groups: [] }) },
    });

    expect(document.getElementById('import-warning').style.display).toBe('block');
    expect(document.getElementById('import-selection-list').style.display).toBe('none');
    expect(document.getElementById('confirm-import').textContent).toBe('Overwrite All');
    vi.unstubAllGlobals();
  });

  it('performImport full should overwrite config and save', async () => {
    const saveConfig = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    const renderGroups = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));
    vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups }));

    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = { groups: [{ name: 'Old' }] };

    const mod = await import('../../static/js/features/export-import.js');
    // Drive the real full-config flow via handleFileSelected + setupImportStep2.
    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));
    mod.handleFileSelected({ target: { files: [new File(['{}'], 'x.json')], value: '' } });
    mockReader.onload({
      target: { result: JSON.stringify({ jellyfin_url: 'http://new', api_key: 'k', groups: [{ name: 'X' }] }) },
    });

    document.getElementById('confirm-import').onclick();
    await new Promise((r) => setTimeout(r, 0));

    expect(stateMod.state.currentConfig).toEqual({
      jellyfin_url: 'http://new',
      api_key: 'k',
      groups: [{ name: 'X' }],
    });
    expect(saveConfig).toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('Import successful!', 'success');
    expect(renderGroups).toHaveBeenCalled();
    expect(document.getElementById('import-modal').style.display).toBe('none');
    vi.unstubAllGlobals();
  });

  it('performImport groups should append selected groups', async () => {
    const saveConfig = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    const renderGroups = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog: vi.fn(),
      getEl: (id) => document.getElementById(id),
    }));
    vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups }));

    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = { groups: [{ name: 'Existing' }] };

    const mod = await import('../../static/js/features/export-import.js');
    // Drive the real groups-import flow via handleFileSelected + setupImportStep2.
    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));
    mod.handleFileSelected({ target: { files: [new File(['{}'], 'x.json')], value: '' } });
    mockReader.onload({
      target: { result: JSON.stringify({ groups: [{ name: 'New1' }, { name: 'New2' }] }) },
    });

    // Select only the first group.
    const checkboxes = document.querySelectorAll('.import-check');
    checkboxes[1].checked = false;
    document.getElementById('confirm-import').onclick();
    await new Promise((r) => setTimeout(r, 0));

    expect(stateMod.state.currentConfig.groups).toEqual([{ name: 'Existing' }, { name: 'New1' }]);
    expect(saveConfig).toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('Import successful!', 'success');
    expect(renderGroups).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('performImport groups should show error when no groups selected', async () => {
    const saveConfig = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    const showErrorDialog = vi.fn();
    const renderGroups = vi.fn();
    vi.doMock('../../static/js/core/api.js', () => ({ saveConfig }));
    vi.doMock('../../static/js/core/ui.js', () => ({
      showToast,
      showErrorDialog,
      getEl: (id) => document.getElementById(id),
    }));
    vi.doMock('../../static/js/features/groupings.js', () => ({ renderGroups }));

    const stateMod = await import('../../static/js/core/state.js');
    stateMod.state.currentConfig = { groups: [{ name: 'Existing' }] };

    const mod = await import('../../static/js/features/export-import.js');
    const mockReader = { readAsText: vi.fn() };
    vi.stubGlobal('FileReader', vi.fn(() => mockReader));
    mod.handleFileSelected({ target: { files: [new File(['{}'], 'x.json')], value: '' } });
    mockReader.onload({
      target: { result: JSON.stringify({ groups: [{ name: 'New1' }, { name: 'New2' }] }) },
    });

    // Uncheck every group so nothing is selected.
    document.querySelectorAll('.import-check').forEach((cb) => { cb.checked = false; });
    document.getElementById('confirm-import').onclick();
    await new Promise((r) => setTimeout(r, 0));

    expect(showErrorDialog).toHaveBeenCalledWith('Please select at least one grouping to import.');
    expect(stateMod.state.currentConfig.groups).toEqual([{ name: 'Existing' }]);
    expect(saveConfig).not.toHaveBeenCalled();
    expect(showToast).not.toHaveBeenCalled();
    expect(renderGroups).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('initExportImport should not throw', async () => {
    const mod = await import('../../static/js/features/export-import.js');
    expect(() => mod.initExportImport()).not.toThrow();
  });
});
