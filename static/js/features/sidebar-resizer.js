// sidebar-resizer.js – Sidebar drag resize (mouse + touch + keyboard)

/** Minimum and maximum sidebar width in pixels. */
const MIN_WIDTH = 200;
const MAX_WIDTH = 800;

/** Width used when no value has been stored yet (matches `--sidebar-width`). */
const DEFAULT_WIDTH = 340;

/** Keyboard resize step; Shift multiplies it. */
const KEY_STEP = 16;
const KEY_STEP_LARGE = 64;

let isResizing = false;
let listening = false;

/** Elements that already carry their own pointer and key handlers. */
const elementHandled = new WeakSet();

/** Clamp sidebar width between min and max bounds. */
function clampSidebarWidth(clientX) {
    let newWidth = Math.round(clientX);
    if (newWidth < MIN_WIDTH) newWidth = MIN_WIDTH;
    if (newWidth > MAX_WIDTH) newWidth = MAX_WIDTH;
    return newWidth;
}

/**
 * Read the sidebar width currently in effect.
 *
 * The inline custom property is authoritative because every code path that
 * changes the width writes it there; the computed value is the fallback for a
 * stylesheet-provided default, and `DEFAULT_WIDTH` covers the case where no
 * CSS has loaded yet (a test DOM, or a page whose stylesheet failed).
 *
 * @returns {number} A width already clamped to the supported range.
 */
function currentSidebarWidth() {
    const inline = document.documentElement.style
        .getPropertyValue('--sidebar-width')
        .trim();
    const computed = inline
        ? inline
        : getComputedStyle(document.documentElement)
              .getPropertyValue('--sidebar-width')
              .trim();

    const parsed = Number.parseFloat(computed);
    return clampSidebarWidth(Number.isFinite(parsed) ? parsed : DEFAULT_WIDTH);
}

/**
 * Expose the width to assistive technology.
 *
 * `role="separator"` with a tabindex is the ARIA window-splitter pattern, and
 * a splitter must report its position: without `aria-valuenow` a screen
 * reader announces only "separator", so the user cannot tell what the arrow
 * keys changed.
 *
 * @param {number} width New sidebar width in pixels.
 */
function updateAriaValue(width) {
    const resizer = document.getElementById('sidebar-resizer');
    if (!resizer) return;
    resizer.setAttribute('aria-valuenow', String(width));
}

/**
 * Apply a width to the layout and keep the accessible value in step.
 * @param {number} width Desired width in pixels (clamped before use).
 * @returns {number} The width actually applied.
 */
function setSidebarWidth(width) {
    const clamped = clampSidebarWidth(width);
    document.documentElement.style.setProperty('--sidebar-width', `${clamped}px`);
    updateAriaValue(clamped);
    return clamped;
}

/** Persist the current --sidebar-width to localStorage. */
function persistSidebarWidth() {
    localStorage.setItem('sidebarWidth', String(currentSidebarWidth()));
}

/** Update the CSS custom property and clamp. */
function updateSidebarWidth(clientX) {
    setSidebarWidth(clientX);
}

function startResize() {
    isResizing = true;
    document.querySelector('#sidebar-resizer')?.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none'; /* prevent text selection while dragging */
}

function endResize() {
    if (!isResizing) return;
    isResizing = false;
    document.querySelector('#sidebar-resizer')?.classList.remove('active');
    document.body.style.cursor = 'default';
    document.body.style.userSelect = '';
    persistSidebarWidth();
}

/**
 * Resize from the keyboard.
 *
 * Without this handler the sidebar could only be resized by dragging, so a
 * keyboard-only or screen-reader user was stuck with the default width and the
 * `tabindex` on the separator would have promised an interaction that did
 * nothing. Arrow keys move by a small step, Shift+Arrow by a large one, and
 * Home/End jump to the bounds.
 *
 * @param {KeyboardEvent} e The keydown event on the separator.
 */
function handleResizeKeydown(e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;

    const width = currentSidebarWidth();
    let next;

    switch (e.key) {
        case 'ArrowLeft':
        case 'Left': {
            const step = e.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
            next = width - step;
            break;
        }
        case 'ArrowRight':
        case 'Right': {
            const step = e.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
            next = width + step;
            break;
        }
        case 'Home':
            next = MIN_WIDTH;
            break;
        case 'End':
            next = MAX_WIDTH;
            break;
        default:
            return;
    }

    // Only claim the key when it actually applies here; arrow keys must keep
    // scrolling the sidebar for anything else focused inside it.
    e.preventDefault();
    const applied = setSidebarWidth(next);
    if (applied !== width) persistSidebarWidth();
}

export function initSidebarResizer() {
    const resizer = document.getElementById('sidebar-resizer');
    if (!resizer) return;

    /* Restore saved width, clamped to valid bounds and validated so a stale
       or corrupt localStorage value (e.g. from an older version, a value
       outside the 200-800px range, or a non-numeric string) can never break
       the layout. Falls back to the CSS default when invalid. */
    const savedWidth = localStorage.getItem('sidebarWidth');
    if (savedWidth) {
        const parsed = Number.parseFloat(savedWidth);
        if (Number.isFinite(parsed)) {
            setSidebarWidth(parsed);
        }
    }
    // Announce the width in effect even when nothing was restored.
    updateAriaValue(currentSidebarWidth());

    // Bind per element: re-initialising with a fresh element must still give
    // that element its pointer and keyboard support, while re-initialising the
    // same element must not stack a second handler that doubles every step.
    if (!elementHandled.has(resizer)) {
        elementHandled.add(resizer);

        resizer.addEventListener('keydown', handleResizeKeydown);

        /* ── Mouse support ── */
        resizer.addEventListener('mousedown', (e) => {
            startResize();
            e.preventDefault();
        });

        /* ── Touch support (tablet / touchscreen laptops) ── */
        resizer.addEventListener('touchstart', (e) => {
            startResize();
            /* Prevent default touch behavior (scrolling) during resize gesture;
               { passive: false } is required to allow preventDefault(). */
            e.preventDefault();
        }, { passive: false });
    }

    // Document-level listeners are registered once: a second init (a test, or
    // a future re-mount) would otherwise stack duplicate mousemove handlers
    // that each write the width.
    if (listening) return;
    listening = true;

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        updateSidebarWidth(e.clientX);
    });

    document.addEventListener('mouseup', endResize);

    document.addEventListener('touchmove', (e) => {
        if (!isResizing) return;
        /* Block scrolling during touch resize for consistent drag UX,
           matching how mouse drags block text selection via userSelect. */
        e.preventDefault();
        const touch = e.touches[0];
        if (touch) {
            updateSidebarWidth(touch.clientX);
        }
    }, { passive: false });

    document.addEventListener('touchend', endResize);
    document.addEventListener('touchcancel', endResize);
}
