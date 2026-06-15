// ui.js – UI utility functions (toasts, loading states, modals)

let toastTimer = null;
let _toastMsgId = 0;

export function showToast(msg, type = 'success', duration = null) {
    // Increase duration for error messages so users have time to read them
    if (duration === null) {
        duration = type === 'error' ? 8000 : 5000;
    }
    const el = document.getElementById('status-msg');
    if (!el) return;
    const msgId = ++_toastMsgId;
    el.dataset.toastId = msgId;
    el.textContent = msg;
    el.className = `status-msg ${type}`;
    // Show toast to screen readers when visible
    el.removeAttribute('aria-hidden');
    // Add close button
    const closeBtn = document.createElement('button');
    closeBtn.className = 'close-btn toast-close';
    closeBtn.innerHTML = '&times;';
    closeBtn.onclick = () => { el.style.display = 'none'; el.setAttribute('aria-hidden', 'true'); clearTimeout(toastTimer); };
    // Remove existing close buttons
    el.querySelectorAll('.toast-close').forEach(b => b.remove());
    el.appendChild(closeBtn);
    el.style.display = 'block';
    el.style.position = 'relative';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        // Only dismiss if no newer toast replaced this one
        if (el.dataset.toastId === String(msgId)) {
            el.style.display = 'none';
            el.setAttribute('aria-hidden', 'true');
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
        // Mark the modal as visible for assistive technology
        el.removeAttribute('aria-hidden');
        // Trap focus inside the modal
        const previousActive = document.activeElement;
        el.dataset.previousActive = previousActive && previousActive !== document.body
            ? previousActive.id || ''
            : '';
        // Focus first focusable element
        const focusable = el.querySelector('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
        if (focusable) {
            setTimeout(() => focusable.focus(), 100);
        }
        // Add body class to prevent background scroll
        document.body.classList.add('modal-open');
    }
}

export function hideModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.style.display = 'none';
        // Hide modal from assistive technology when not visible
        el.setAttribute('aria-hidden', 'true');
        // Return focus to the element that triggered the modal
        const prevId = el.dataset.previousActive;
        if (prevId) {
            const prev = document.getElementById(prevId);
            if (prev) prev.focus();
        }
        // Remove body class when no more modals are visible
        const anyVisible = document.querySelectorAll('.modal');
        let hasVisible = false;
        for (const m of anyVisible) {
            const style = window.getComputedStyle(m);
            if (style.display !== 'none') {
                hasVisible = true;
                break;
            }
        }
        if (!hasVisible) {
            document.body.classList.remove('modal-open');
        }
    }
}

// Close modal on Escape key — hide the topmost visible modal
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const visibleModals = document.querySelectorAll('.modal');
        // Find the last visible modal (topmost in stacking order)
        let topmost = null;
        for (const m of visibleModals) {
            if (m.style.display === 'flex' || m.style.display === 'block') {
                topmost = m;
            }
        }
        if (topmost) {
            hideModal(topmost.id);
            // Restore focus to trigger
            const modalId = topmost.id;
            const trigger = document.querySelector(`[onclick*="${modalId}"], [data-modal="${modalId}"]`);
            if (trigger) trigger.focus();
        }
    }
});

// Close modal when clicking the backdrop (overlay) outside content area
document.addEventListener('click', (e) => {
    const modal = e.target.closest('.modal');
    if (modal && e.target === modal) {
        hideModal(modal.id);
    }
});

// Generic click handler for .close-modal-btn class
document.addEventListener('click', (e) => {
    const closeBtn = e.target.closest('.close-modal-btn');
    if (closeBtn) {
        const modal = closeBtn.closest('.modal');
        if (modal) {
            modal.style.display = 'none';
            // Return focus to the element that triggered the modal
            const trigger = document.querySelector(`[data-modal="${modal.id}"], [onclick*="${modal.id}"]`);
            if (trigger) trigger.focus();
        }
    }
});

export function renderEmptyState(container, message) {
    container.innerHTML = '';
    const p = document.createElement('p');
    p.style.cssText = 'color: var(--text-secondary); text-align: center; font-style: italic; margin-top: 2rem;';
    p.textContent = message;
    container.appendChild(p);
}

export function getEl(id) {
    return document.getElementById(id);
}

export function showErrorDialog(msg) {
    const modal = getEl('error-dialog-modal');
    const msgEl = getEl('error-dialog-message');
    if (!modal || !msgEl) {
        showToast(msg, 'error');
        return;
    }
    msgEl.textContent = msg;
    showModal('error-dialog-modal');
}

/**
 * Show a confirm dialog modal that resolves to true/false.
 * @param {string} title - Dialog title
 * @param {string} message - Dialog body text
 * @param {string} [confirmText='Confirm'] - Text for the confirm button
 * @param {string} [cancelText='Cancel'] - Text for the cancel button
 * @returns {Promise<boolean>} Resolves to true if confirmed, false if cancelled
 */
export function showConfirmDialog(title, message, confirmText = 'Confirm', cancelText = 'Cancel') {
    return new Promise((resolve) => {
        const modal = getEl('confirm-dialog-modal');
        const titleEl = getEl('confirm-dialog-title');
        const msgEl = getEl('confirm-dialog-message');
        const okBtn = getEl('confirm-dialog-ok-btn');
        const cancelBtn = getEl('confirm-dialog-cancel-btn');
        if (!modal || !titleEl || !msgEl || !okBtn || !cancelBtn) {
            // Fallback to native confirm if modal elements are missing
            resolve(confirm(message));
            return;
        }

        titleEl.textContent = title;
        msgEl.textContent = message;
        okBtn.textContent = confirmText;
        cancelBtn.textContent = cancelText;

        const cleanup = () => {
            okBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
            // Remove any close-modal-btn listeners that might fire
            const closeBtns = modal.querySelectorAll('.close-modal-btn');
            closeBtns.forEach(btn => btn.removeEventListener('click', onCancel));
        };

        const onConfirm = () => {
            hideModal('confirm-dialog-modal');
            cleanup();
            resolve(true);
        };

        const onCancel = () => {
            hideModal('confirm-dialog-modal');
            cleanup();
            resolve(false);
        };

        okBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        // Also close on backdrop click or X button
        const closeBtns = modal.querySelectorAll('.close-modal-btn');
        closeBtns.forEach(btn => btn.addEventListener('click', onCancel));

        showModal('confirm-dialog-modal');
    });
}

let _progressTotal = 0;
let _progressStep = 0;
let _progressStartTime = 0;

function _updateProgressBar() {
    const fill = getEl('progress-bar-fill');
    const pctEl = getEl('progress-percentage');
    const etaEl = getEl('progress-eta');
    if (!fill || !pctEl) return;

    const pct = _progressTotal > 0
        ? Math.round((_progressStep / _progressTotal) * 100)
        : 0;
    fill.style.width = `${pct}%`;
    pctEl.textContent = `${pct}%`;

    if (etaEl && _progressStartTime > 0 && _progressStep > 0 && _progressStep < _progressTotal) {
        const elapsed = Math.max(0.001, (Date.now() - _progressStartTime) / 1000);
        const perStep = elapsed / _progressStep;
        const remaining = perStep * (_progressTotal - _progressStep);
        if (remaining > 2) {
            etaEl.style.display = 'inline';
            etaEl.textContent = `~${Math.ceil(remaining)}s remaining`;
        } else {
            etaEl.style.display = 'none';
        }
    } else if (etaEl) {
        etaEl.style.display = 'none';
    }
}

export function showLoadingOverlay(title, status, totalSteps = 0) {
    const overlay = getEl('loading-overlay');
    if (!overlay) return;
    const titleEl = getEl('loading-overlay-title');
    const statusEl = getEl('loading-overlay-status');
    if (titleEl) titleEl.textContent = title || 'Connecting to Jellyfin';
    if (statusEl) statusEl.textContent = status || 'Fetching data...';

    _progressTotal = Math.max(0, totalSteps);
    _progressStep = 0;
    _progressStartTime = _progressTotal > 0 ? Date.now() : 0;
    _updateProgressBar();

    overlay.style.display = 'flex';
    overlay.removeAttribute('aria-hidden');
}

export function updateLoadingStatus(status, advanceStep = false) {
    const el = getEl('loading-overlay-status');
    if (el) el.textContent = status;

    if (advanceStep && _progressTotal > 0) {
        _progressStep = Math.min(_progressStep + 1, _progressTotal);
        _updateProgressBar();
    }
}

export function hideLoadingOverlay() {
    const overlay = getEl('loading-overlay');
    if (overlay) {
        overlay.style.display = 'none';
        overlay.setAttribute('aria-hidden', 'true');
    }
    _progressTotal = 0;
    _progressStep = 0;
    _progressStartTime = 0;
}
