/**
 * Regression tests for API error messages.
 *
 * `POST /api/config` answers a validation failure with a generic top-level
 * message plus an `errors` array, e.g.
 *
 *     {"message": "Invalid config field type(s)",
 *      "errors": ["groups[1].name duplicates groups[0].name ('Dup')"]}
 *
 * The client used to keep only `body.message`, so the user saw "Invalid
 * config field type(s)" with no indication of which field was wrong and no
 * way to act on it. The details are now folded into the displayed message.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// `api.js` registers nothing at module scope, so a fresh import per test is
// safe. `fetch` is stubbed per test to drive each response shape.
import { apiPost, apiGetSilent } from '../../static/js/core/api.js';
import * as ui from '../../static/js/core/ui.js';

/** Build a fetch stub that answers with *body* and *status*. */
function stubFetch(body, status = 400) {
    globalThis.fetch = vi.fn(async () => ({
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
    }));
}

beforeEach(() => {
    document.body.innerHTML = `
        <div id="error-dialog-modal" class="modal" style="display: none">
            <div class="modal-content">
                <p id="error-dialog-message"></p>
            </div>
        </div>
        <div id="status-msg"></div>
    `;
    vi.spyOn(ui, 'showErrorDialog').mockImplementation(() => {});
    vi.spyOn(ui, 'showToast').mockImplementation(() => {});
});

afterEach(() => {
    vi.restoreAllMocks();
    delete globalThis.fetch;
});

describe('API error messages', () => {
    it('includes the individual validation errors', async () => {
        stubFetch(
            {
                message: 'Invalid config field type(s)',
                errors: [
                    "groups[1].name duplicates groups[0].name ('Dup')",
                    "groups[2].name must not be empty",
                ],
            },
            400,
        );

        const err = await apiPost('/api/config', {}).catch(e => e);

        expect(err.status).toBe(400);
        expect(err.message).toContain('Invalid config field type(s)');
        expect(err.message).toContain('duplicates');
        expect(err.message).toContain('must not be empty');
        expect(err.details).toHaveLength(2);
    });

    it('shows only the first few details and counts the rest', async () => {
        stubFetch(
            {
                message: 'Invalid',
                errors: ['a', 'b', 'c', 'd', 'e'],
            },
            400,
        );

        const err = await apiPost('/api/config', {}).catch(e => e);

        expect(err.message).toContain('a');
        expect(err.message).toContain('c');
        expect(err.message).not.toContain('• d');
        expect(err.message).toContain('(+2 more)');
    });

    it('falls back to the plain message when there are no details', async () => {
        stubFetch({ message: 'Config file write failed: disk full' }, 500);

        const err = await apiPost('/api/config', {}).catch(e => e);

        expect(err.message).toBe('Config file write failed: disk full');
        expect(err.details).toEqual([]);
    });

    it('ignores non-string entries in the errors array', async () => {
        stubFetch({ message: 'Invalid', errors: [null, 42, 'real problem'] }, 400);

        const err = await apiPost('/api/config', {}).catch(e => e);

        expect(err.message).toContain('real problem');
        expect(err.details).toEqual(['real problem']);
    });

    it('uses a generic message when the body carries none', async () => {
        stubFetch({}, 400);

        const err = await apiPost('/api/config', {}).catch(e => e);

        expect(err.message).toBe('Request failed');
    });

    it('surfaces details to the caller of a silent request', async () => {
        // The folder picker renders failures inline, so it must still be able
        // to read the server's reason rather than a bare status code.
        stubFetch(
            {
                message: 'Access to this path is not permitted',
                errors: ['path is outside the browse roots'],
            },
            403,
        );

        const err = await apiGetSilent('/api/browse').catch(e => e);

        expect(err.status).toBe(403);
        expect(err.message).toContain('Access to this path is not permitted');
        expect(err.message).toContain('outside the browse roots');
        // Silent requests must not pop a dialog on top of the picker.
        expect(ui.showErrorDialog).not.toHaveBeenCalled();
    });
});
