// sidebar-resizer.js – Sidebar drag resize

let isResizing = false;

export function initSidebarResizer() {
    const resizer = document.getElementById('sidebar-resizer');
    if (!resizer) return;

    const savedWidth = localStorage.getItem('sidebarWidth');
    if (savedWidth) {
        document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);
    }

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('active');
        document.body.style.cursor = 'col-resize';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        let newWidth = e.clientX;
        if (newWidth < 200) newWidth = 200;
        if (newWidth > 800) newWidth = 800;
        document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
    });

    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        resizer.classList.remove('active');
        document.body.style.cursor = 'default';
        const currentWidth = getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').replace('px', '').trim();
        localStorage.setItem('sidebarWidth', currentWidth);
    });
}
