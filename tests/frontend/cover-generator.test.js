/**
 * @file Tests for the cover-generator feature module (canvas-based cover image
 * generation: open, render, download, apply, init).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the API module so uploadCover/saveConfig are observable.
vi.mock('../../static/js/core/api.js', () => ({
  saveConfig: vi.fn(),
  uploadCover: vi.fn(),
}));

// Mock the UI module so showToast/showErrorDialog/hideModal/getEl are observable.
vi.mock('../../static/js/core/ui.js', () => ({
  showToast: vi.fn(),
  showErrorDialog: vi.fn(),
  hideModal: vi.fn(),
  getEl: vi.fn((id) => document.getElementById(id)),
}));

import { saveConfig, uploadCover } from '../../static/js/core/api.js';
import { showToast, showErrorDialog, hideModal } from '../../static/js/core/ui.js';

/**
 * Build a minimal mock 2D canvas context so renderCover() can run in jsdom
 * (which does not implement getContext('2d')).
 */
function mockCanvasContext() {
  const ctx = {
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    quadraticCurveTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    clearRect: vi.fn(),
    arc: vi.fn(),
    bezierCurveTo: vi.fn(),
    setTransform: vi.fn(),
    createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    measureText: vi.fn(() => ({ width: 10 })),
    fillText: vi.fn(),
    setLineDash: vi.fn(),
    // writable properties
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    globalAlpha: 1,
    shadowBlur: 0,
    shadowColor: 'transparent',
    shadowOffsetY: 0,
    lineCap: 'butt',
    lineJoin: 'miter',
    font: '',
    textAlign: 'left',
    textBaseline: 'alphabetic',
    filter: 'none',
    imageSmoothingEnabled: true,
    imageSmoothingQuality: 'low',
  };
  return ctx;
}

/**
 * Set up the DOM elements that cover-generator.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <input id="cover-text" />
    <select id="cover-theme">
      <option value="modern-dark">Dark Gradient (Modern)</option>
      <option value="vibrant-glow">Vibrant Glow</option>
      <option value="minimal-glass">Minimal Glassmorphism</option>
      <option value="cyberpunk">Cyberpunk Night</option>
      <option value="aurora">Aurora Borealis</option>
      <option value="monochrome">Monochrome Peak</option>
      <option value="vintage">Golden Age</option>
    </select>
    <select id="cover-border-style">
      <option value="none">None</option>
      <option value="elegant">Elegant Thin</option>
      <option value="bold-frame">Bold Frame</option>
      <option value="neon-glow">Neon Glow</option>
      <option value="tech-corners">Sci-Fi Corners</option>
      <option value="double-inset">Double Inset</option>
      <option value="corner-brackets">Corner Brackets</option>
      <option value="industrial-dash">Dashed Industrial</option>
      <option value="ornate">Ornate Frame</option>
    </select>
    <input id="cover-border-color" />
    <input id="cover-color-1" />
    <input id="cover-color-2" />
    <div id="cover-generator-modal"></div>
    <canvas id="cover-canvas"></canvas>
  `;
  const canvas = document.getElementById('cover-canvas');
  canvas.getContext = vi.fn(() => mockCanvasContext());
  // jsdom does not implement toDataURL; provide a stub.
  canvas.toDataURL = vi.fn(() => 'data:image/jpeg;base64,AAAA');
}

/**
 * Build a sample group object for tests.
 */
function makeGroup(overrides = {}) {
  return {
    name: 'Action',
    cover_text: 'Action Movies',
    cover_theme: 'modern-dark',
    cover_border_style: 'none',
    cover_border_color: '#ffffff',
    cover_color1: '#4f46e5',
    cover_color2: '#9333ea',
    ...overrides,
  };
}

describe('cover-generator module', () => {
  beforeEach(() => {
    setupDOM();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('should export the expected public functions', async () => {
    const mod = await import('../../static/js/features/cover-generator.js');
    expect(typeof mod.openCoverGenerator).toBe('function');
    expect(typeof mod.renderCover).toBe('function');
    expect(typeof mod.downloadCover).toBe('function');
    expect(typeof mod.applyCover).toBe('function');
    expect(typeof mod.initCoverGenerator).toBe('function');
  });

  describe('openCoverGenerator', () => {
    it('should populate the form fields from the group and show the modal', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.openCoverGenerator(0);

      expect(document.getElementById('cover-text').value).toBe('Action Movies');
      expect(document.getElementById('cover-theme').value).toBe('modern-dark');
      expect(document.getElementById('cover-border-style').value).toBe('none');
      expect(document.getElementById('cover-border-color').value).toBe('#ffffff');
      expect(document.getElementById('cover-color-1').value).toBe('#4f46e5');
      expect(document.getElementById('cover-color-2').value).toBe('#9333ea');
      expect(document.getElementById('cover-generator-modal').style.display).toBe('flex');
    });

    it('should fall back to the group name when cover_text is missing', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({ cover_text: undefined })];
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.openCoverGenerator(0);
      expect(document.getElementById('cover-text').value).toBe('Action');
    });

    it('should fall back to defaults when cover fields are missing', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup({
        cover_text: undefined, cover_theme: undefined, cover_border_style: undefined,
        cover_border_color: undefined, cover_color1: undefined, cover_color2: undefined,
      })];
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.openCoverGenerator(0);
      expect(document.getElementById('cover-theme').value).toBe('modern-dark');
      expect(document.getElementById('cover-border-style').value).toBe('none');
      expect(document.getElementById('cover-border-color').value).toBe('#ffffff');
      expect(document.getElementById('cover-color-1').value).toBe('#4f46e5');
      expect(document.getElementById('cover-color-2').value).toBe('#9333ea');
    });

    it('should render the cover once fonts are ready', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      const mod = await import('../../static/js/features/cover-generator.js');
      // Simulate document.fonts.ready resolving.
      document.fonts = { ready: Promise.resolve() };
      mod.openCoverGenerator(0);
      await Promise.resolve();
      // renderCover() should have run and drawn on the canvas.
      const canvas = document.getElementById('cover-canvas');
      expect(canvas.getContext).toHaveBeenCalledWith('2d');
    });
  });

  describe('renderCover', () => {
    it('should draw on the canvas without throwing', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.openCoverGenerator(0);
      // Force synchronous render (fonts not ready path uses setTimeout).
      expect(() => mod.renderCover()).not.toThrow();
      const canvas = document.getElementById('cover-canvas');
      expect(canvas.getContext).toHaveBeenCalledWith('2d');
    });
  });

  describe('downloadCover', () => {
    it('should do nothing when no cover is active', async () => {
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.downloadCover();
      expect(showToast).not.toHaveBeenCalled();
    });

    it('should trigger a download and show a toast when a cover is active', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.openCoverGenerator(0);

      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      mod.downloadCover();
      expect(clickSpy).toHaveBeenCalled();
      expect(showToast).toHaveBeenCalledWith('Downloaded cover!', 'success');
      clickSpy.mockRestore();
    });
  });

  describe('applyCover', () => {
    it('should do nothing when no cover is active', async () => {
      const mod = await import('../../static/js/features/cover-generator.js');
      await mod.applyCover();
      expect(uploadCover).not.toHaveBeenCalled();
    });

    it('should upload, save config, update the group and close the modal on success', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      uploadCover.mockResolvedValue({});
      saveConfig.mockResolvedValue({});
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.openCoverGenerator(0);

      await mod.applyCover();
      expect(uploadCover).toHaveBeenCalledWith('Action', 'data:image/jpeg;base64,AAAA');
      expect(saveConfig).toHaveBeenCalledWith(state.currentConfig);
      expect(showToast).toHaveBeenCalledWith('Cover generated and saved!', 'success');
      expect(hideModal).toHaveBeenCalledWith('cover-generator-modal');
      // Group should be updated with the current form values.
      expect(state.currentConfig.groups[0].cover_text).toBe('Action Movies');
    });

    it('should show an error dialog when the upload fails', async () => {
      const { state } = await import('../../static/js/core/state.js');
      state.currentConfig.groups = [makeGroup()];
      uploadCover.mockRejectedValue(new Error('boom'));
      const mod = await import('../../static/js/features/cover-generator.js');
      mod.openCoverGenerator(0);

      await mod.applyCover();
      expect(showErrorDialog).toHaveBeenCalledWith('Network error while saving cover.');
      expect(hideModal).not.toHaveBeenCalled();
    });
  });

  describe('initCoverGenerator', () => {
    it('should be callable without throwing', async () => {
      const mod = await import('../../static/js/features/cover-generator.js');
      expect(() => mod.initCoverGenerator()).not.toThrow();
    });
  });
});
