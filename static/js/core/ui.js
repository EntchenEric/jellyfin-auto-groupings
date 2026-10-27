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
    // Add close button. The aria-label gives screen readers a descriptive
    // name instead of announcing the raw '×' glyph (WCAG 4.1.2).
    const closeBtn = document.createElement('button');
    closeBtn.className = 'close-btn toast-close';
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Dismiss notification');
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

// Selector for elements that can receive keyboard focus inside a modal.
const _FOCUSABLE =
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
    'textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

function _isVisible(el) {
    // Walk up the tree; an element is focusable only if neither it nor any
    // ancestor is hidden via display:none or visibility:hidden. Uses computed
    // style so it works both in real browsers and in jsdom-based tests.
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
        const style = window.getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return false;
        }
    }
    return true;
}

function _getFocusable(el) {
    return Array.from(el.querySelectorAll(_FOCUSABLE)).filter(_isVisible);
}

// Trap Tab/Shift+Tab inside the topmost visible modal so keyboard users
// cannot tab out into the background page (WCAG 2.1.2 / 2.4.3). The topmost
// modal is derived from the DOM (last visible .modal), so the trap stays
// correct even if a modal is hidden through other means.
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const modals = document.querySelectorAll('.modal');
    let topmost = null;
    for (const m of modals) {
        const style = window.getComputedStyle(m);
        if (style.display !== 'none') {
            topmost = m;
        }
    }
    if (!topmost) return;
    const focusable = _getFocusable(topmost);
    if (focusable.length === 0) {
        e.preventDefault();
        topmost.focus && topmost.focus();
        return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (e.shiftKey) {
        if (active === first || !topmost.contains(active)) {
            e.preventDefault();
            last.focus();
        }
    } else if (active === last || !topmost.contains(active)) {
        e.preventDefault();
        first.focus();
    }
});

// Callbacks fired whenever a modal is hidden, keyed by modal id. A dialog that
// owns a pending promise (see showConfirmDialog) registers here so every close
// path — Escape, backdrop click, the × button — settles it. Without this the
// promise stayed pending forever and the caller's `await` never resumed.
const _hideListeners = new Map();

//: Settles the confirmation dialog that is currently open, if any. A second
//: call to showConfirmDialog() replaces the dialog contents, so the previous
//: promise would otherwise stay pending forever.
let _abandonPendingConfirm = null;

/**
 * Register *fn* to run when the modal with *id* is hidden.
 * @param {string} id - Modal element id
 * @param {Function} fn - Callback, invoked once per hide
 * @returns {Function} Unregister function
 */
export function onModalHide(id, fn) {
    if (!_hideListeners.has(id)) {
        _hideListeners.set(id, new Set());
    }
    _hideListeners.get(id).add(fn);
    return () => {
        const listeners = _hideListeners.get(id);
        if (!listeners) return;
        listeners.delete(fn);
        if (listeners.size === 0) _hideListeners.delete(id);
    };
}

function _notifyModalHidden(id) {
    const listeners = _hideListeners.get(id);
    if (!listeners) return;
    // Copy so a listener that unregisters itself does not disturb iteration.
    for (const fn of Array.from(listeners)) {
        fn();
    }
}

// Element that had focus before each modal opened, keyed by modal id. The
// reference is kept in memory rather than written to `data-previous-active`
// because the trigger often has no id at all: every per-group "Cover" and
// "Edit" button is created in a loop, so an id-based round trip stored ""
// and `hideModal()` left focus on the closed dialog (WCAG 2.4.3). Holding the
// node also survives a trigger that is re-rendered with the same id.
const _previousFocus = new Map();

/**
 * Remember which element should get focus back when *id* closes.
 * @param {string} id - Modal element id
 * @param {Element|null} el - Element that opened the modal
 * @returns {void}
 */
function _rememberFocus(id, el) {
    if (el && el !== document.body && typeof el.focus === 'function') {
        _previousFocus.set(id, el);
    } else {
        _previousFocus.delete(id);
    }
}

export function showModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.style.display = 'flex';
        // Mark the modal as visible for assistive technology
        el.removeAttribute('aria-hidden');
        // Remember the element that triggered the modal so focus can be
        // restored when it closes.
        _rememberFocus(id, document.activeElement);
        // Focus first focusable element
        const focusable = el.querySelector(_FOCUSABLE);
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
        const wasOpen = el.style.display !== 'none';
        el.style.display = 'none';
        // Hide modal from assistive technology when not visible
        el.setAttribute('aria-hidden', 'true');
        // Return focus to the element that triggered the modal. The trigger
        // may have been removed by a re-render while the dialog was open, in
        // which case focusing it would silently do nothing; drop the stale
        // reference instead of keeping it forever.
        const prev = _previousFocus.get(id);
        _previousFocus.delete(id);
        if (prev && document.contains(prev)) {
            prev.focus();
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
        // Only report a real transition, so a redundant hideModal() call on an
        // already-closed dialog cannot settle a fresh pending promise.
        if (wasOpen) _notifyModalHidden(id);
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
            // `hideModal()` restores focus to the element that opened the
            // dialog; looking up a `[onclick*="<modal-id>"]` trigger here
            // never matched anything, because openers name the feature (Sync,
            // Export) rather than the dialog.
            hideModal(topmost.id);
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
            // Delegate to hideModal instead of only flipping display: it also
            // sets aria-hidden, restores focus to the trigger, and drops
            // body.modal-open. Setting display alone left the page stuck
            // scroll-locked (body { position: fixed }) and left the closed
            // dialog exposed to assistive technology.
            hideModal(modal.id);
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
    if (_abandonPendingConfirm) {
        const abandon = _abandonPendingConfirm;
        _abandonPendingConfirm = null;
        abandon();
    }

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

        // ``outcome`` holds the answer for the current close. A close that did
        // not come from the confirm button (Escape, backdrop, ×) keeps the
        // default ``false``, which is the documented cancel behaviour.
        let outcome = false;
        let settled = false;
        let unregisterHide = null;

        const settle = (value) => {
            if (settled) return;
            settled = true;
            if (_abandonPendingConfirm === cancelPending) _abandonPendingConfirm = null;
            if (unregisterHide) unregisterHide();
            unregisterHide = null;
            cleanup();
            resolve(value);
        };

        const cancelPending = () => settle(false);
        _abandonPendingConfirm = cancelPending;

        const cleanup = () => {
            okBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
            // Remove any close-modal-btn listeners that might fire
            const closeBtns = modal.querySelectorAll('.close-modal-btn');
            closeBtns.forEach(btn => btn.removeEventListener('click', onCancel));
        };

        const onConfirm = () => {
            outcome = true;
            hideModal('confirm-dialog-modal');
            settle(true);
        };

        const onCancel = () => {
            outcome = false;
            hideModal('confirm-dialog-modal');
            settle(false);
        };

        okBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        // Also close on backdrop click or X button
        const closeBtns = modal.querySelectorAll('.close-modal-btn');
        closeBtns.forEach(btn => btn.addEventListener('click', onCancel));

        // Escape, backdrop click, and the × button call hideModal() directly
        // and never reached the handlers above, leaving the promise pending
        // forever — a caller awaiting the answer then hung silently.
        unregisterHide = onModalHide('confirm-dialog-modal', () => settle(outcome));

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
    _rememberFocus('loading-overlay', document.activeElement);
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
        const prev = _previousFocus.get('loading-overlay');
        _previousFocus.delete('loading-overlay');
        if (prev && document.contains(prev)) {
            prev.focus();
        }
    }
    _progressTotal = 0;
    _progressStep = 0;
    _progressStartTime = 0;
}
