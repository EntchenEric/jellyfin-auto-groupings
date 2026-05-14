// ui.js – UI utility functions (toasts, loading states, modals)

let toastTimer = null;

export function showToast(msg, type = 'success', duration = 5000) {
    const el = document.getElementById('status-msg');
    if (!el) return;
    el.textContent = msg;
    el.className = `status-msg ${type}`;
    // Add close button
    const closeBtn = document.createElement('button');
    closeBtn.className = 'close-btn toast-close';
    closeBtn.innerHTML = '&times;';
    closeBtn.style.cssText = 'position:absolute; top:4px; right:8px; font-size:1rem; color:inherit; width:auto; margin:0; padding:0; background:none; border:none; cursor:pointer;';
    closeBtn.onclick = () => { el.style.display = 'none'; clearTimeout(toastTimer); };
    // Remove existing close buttons
    el.querySelectorAll('.toast-close').forEach(b => b.remove());
    el.appendChild(closeBtn);
    el.style.display = 'block';
    el.style.position = 'relative';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        if (el.textContent.includes(msg) || el.textContent.startsWith(msg)) {
            el.style.display = 'none';
        }
    }, duration);
}

export function setLoading(btn, loading) {
    if (!btn) return;
    btn.classList.toggle('btn-loading', loading);
}

export function showModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.style.display = 'flex';
        // Focus first focusable element
        const focusable = el.querySelector('button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusable) setTimeout(() => focusable.focus(), 100);
    }
}

export function hideModal(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal[style*="display: flex"], .modal[style*="display:flex"]');
        if (modals.length > 0) {
            const topModal = modals[modals.length - 1];
            topModal.style.display = 'none';
        }
    }
});

// Generic click handler for .close-modal-btn class
document.addEventListener('click', (e) => {
    if (e.target.closest('.close-modal-btn')) {
        const modal = e.target.closest('.modal');
        if (modal) modal.style.display = 'none';
    }
});

export function renderEmptyState(container, message) {
    container.innerHTML = `<p style="color: var(--text-secondary); text-align: center; font-style: italic; margin-top: 2rem;">${message}</p>`;
}

export function getEl(id) {
    return document.getElementById(id);
}

export function showLoadingOverlay(title, status) {
    const overlay = getEl('loading-overlay');
    if (!overlay) return;
    const titleEl = getEl('loading-overlay-title');
    const statusEl = getEl('loading-overlay-status');
    if (titleEl) titleEl.textContent = title || 'Connecting to Jellyfin';
    if (statusEl) statusEl.textContent = status || 'Fetching data...';
    overlay.style.display = 'flex';
}

export function updateLoadingStatus(status) {
    const el = getEl('loading-overlay-status');
    if (el) el.textContent = status;
}

export function hideLoadingOverlay() {
    const overlay = getEl('loading-overlay');
    if (overlay) overlay.style.display = 'none';
}
