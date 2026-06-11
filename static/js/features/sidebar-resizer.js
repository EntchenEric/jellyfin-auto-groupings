// sidebar-resizer.js – Sidebar drag resize (mouse + touch)

let isResizing = false;

/** Clamp sidebar width between min and max bounds. */
function clampSidebarWidth(clientX) {
    let newWidth = clientX;
    if (newWidth < 200) newWidth = 200;
    if (newWidth > 800) newWidth = 800;
    return newWidth;
}

/** Persist the current --sidebar-width to localStorage. */
function persistSidebarWidth() {
    const currentWidth = getComputedStyle(document.documentElement)
        .getPropertyValue('--sidebar-width')
        .replace('px', '')
        .trim();
    localStorage.setItem('sidebarWidth', currentWidth);
}

/** Update the CSS custom property and clamp. */
function updateSidebarWidth(clientX) {
    const newWidth = clampSidebarWidth(clientX);
    document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
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

export function initSidebarResizer() {
    const resizer = document.getElementById('sidebar-resizer');
    if (!resizer) return;

    /* Restore saved width */
    const savedWidth = localStorage.getItem('sidebarWidth');
    if (savedWidth) {
        document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);
    }

    /* ── Mouse support ── */
    resizer.addEventListener('mousedown', (e) => {
        startResize();
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        updateSidebarWidth(e.clientX);
    });

    document.addEventListener('mouseup', endResize);

    /* ── Touch support (tablet / touchscreen laptops) ── */
    resizer.addEventListener('touchstart', (e) => {
        startResize();
        /* Prevent default touch behavior (scrolling) during resize gesture;
           { passive: false } is required to allow preventDefault(). */
        e.preventDefault();
    }, { passive: false });

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
