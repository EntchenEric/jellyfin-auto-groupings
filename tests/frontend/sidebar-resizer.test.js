/**
 * @file Tests for the sidebar-resizer feature module.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Set up the DOM elements that sidebar-resizer.js references.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="sidebar-resizer"></div>
    <div id="sidebar"></div>
  `;
  // Set initial CSS custom property
  document.documentElement.style.setProperty('--sidebar-width', '300px');
  // Clear any saved width from previous tests
  localStorage.removeItem('sidebarWidth');
}

describe('sidebar-resizer module', () => {
  beforeEach(() => {
    setupDOM();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('should export initSidebarResizer as a function', async () => {
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    expect(typeof mod.initSidebarResizer).toBe('function');
  });

  it('should restore saved sidebar width from localStorage', async () => {
    localStorage.setItem('sidebarWidth', '400');
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();
    const width = getComputedStyle(document.documentElement)
      .getPropertyValue('--sidebar-width')
      .trim();
    expect(width).toBe('400px');
  });

  it('should keep default width when no saved width exists', async () => {
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();
    const width = getComputedStyle(document.documentElement)
      .getPropertyValue('--sidebar-width')
      .trim();
    expect(width).toBe('300px');
  });

  it('should not throw when resizer element is missing', async () => {
    document.body.innerHTML = '';
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    expect(() => mod.initSidebarResizer()).not.toThrow();
  });

  it('should clamp sidebar width to minimum 200px', async () => {
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();

    // Simulate mousedown on resizer
    const resizer = document.getElementById('sidebar-resizer');
    resizer.dispatchEvent(new MouseEvent('mousedown', { clientX: 150 }));

    // Simulate mousemove at 150px (below minimum)
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 150 }));

    const width = getComputedStyle(document.documentElement)
      .getPropertyValue('--sidebar-width')
      .trim();
    expect(width).toBe('200px');

    // Clean up: simulate mouseup
    document.dispatchEvent(new MouseEvent('mouseup'));
  });

  it('should clamp sidebar width to maximum 800px', async () => {
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();

    const resizer = document.getElementById('sidebar-resizer');
    resizer.dispatchEvent(new MouseEvent('mousedown', { clientX: 900 }));

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 900 }));

    const width = getComputedStyle(document.documentElement)
      .getPropertyValue('--sidebar-width')
      .trim();
    expect(width).toBe('800px');

    document.dispatchEvent(new MouseEvent('mouseup'));
  });

  it('should persist width to localStorage on mouseup', async () => {
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();

    const resizer = document.getElementById('sidebar-resizer');
    resizer.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 500 }));
    document.dispatchEvent(new MouseEvent('mouseup'));

    expect(localStorage.getItem('sidebarWidth')).toBe('500');
  });

  it('should handle touch events for resize', async () => {
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();

    const resizer = document.getElementById('sidebar-resizer');
    // jsdom does not support Touch constructor, so we use a custom event
    const touchStart = new TouchEvent('touchstart', {
      touches: [{ clientX: 300, target: resizer }],
      cancelable: true,
    });
    resizer.dispatchEvent(touchStart);

    const touchMove = new TouchEvent('touchmove', {
      touches: [{ clientX: 600, target: document.body }],
      cancelable: true,
    });
    document.dispatchEvent(touchMove);

    const width = getComputedStyle(document.documentElement)
      .getPropertyValue('--sidebar-width')
      .trim();
    expect(width).toBe('600px');

    document.dispatchEvent(new TouchEvent('touchend'));
  });

  it('should add active class to resizer on mousedown', async () => {
    const mod = await import('../../static/js/features/sidebar-resizer.js');
    mod.initSidebarResizer();

    const resizer = document.getElementById('sidebar-resizer');
    resizer.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));

    expect(resizer.classList.contains('active')).toBe(true);

    document.dispatchEvent(new MouseEvent('mouseup'));
    expect(resizer.classList.contains('active')).toBe(false);
  });
});
