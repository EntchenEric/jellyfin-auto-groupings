/**
 * Regression tests for the seasonal date pickers.
 *
 * The day select used to offer 1-31 for every month, so choosing "31" while
 * February was selected produced `02-31`. That value passes a month/day
 * *range* check but names no real date, and the backend used to accept it and
 * then treat the whole window as "always in season" — the group was never
 * cleaned up when its season ended.
 *
 * The day list now follows the month, and the forms load through
 * `setSeasonalDate()` so a stored value can be restored exactly.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const FORM = `
  <div id="seasonal_panel"></div>
  <input type="checkbox" id="seasonal_enabled">
  <select id="seasonal_start_month">
    <option value="01">Jan</option><option value="02">Feb</option>
    <option value="03">Mar</option><option value="04">Apr</option>
    <option value="05">May</option><option value="06">Jun</option>
    <option value="07">Jul</option><option value="08">Aug</option>
    <option value="09">Sep</option><option value="10">Oct</option>
    <option value="11">Nov</option><option value="12">Dec</option>
  </select>
  <select id="seasonal_start_day"></select>
  <select id="seasonal_end_month">
    <option value="01">Jan</option><option value="02">Feb</option>
    <option value="03">Mar</option><option value="04">Apr</option>
    <option value="05">May</option><option value="06">Jun</option>
    <option value="07">Jul</option><option value="08">Aug</option>
    <option value="09">Sep</option><option value="10">Oct</option>
    <option value="11">Nov</option><option value="12">Dec</option>
  </select>
  <select id="seasonal_end_day"></select>
  <div id="status-msg"></div>
`;

async function mount() {
    document.body.innerHTML = FORM;
    vi.resetModules();
    return import('../../static/js/features/groupings.js');
}

/** Option values of a select, in order. */
function dayOptions(id) {
    return Array.from(document.getElementById(id).options).map((o) => o.value);
}

describe('seasonal day selects', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('offers only the days that exist in the selected month', async () => {
        const { populateSeasonalDays } = await mount();
        populateSeasonalDays();

        document.getElementById('seasonal_start_month').value = '02';
        document
            .getElementById('seasonal_start_month')
            .dispatchEvent(new Event('change'));

        // February in a leap year: 29 days, never 30 or 31.
        expect(dayOptions('seasonal_start_day')).toHaveLength(29);
        expect(dayOptions('seasonal_start_day')).toContain('29');
        expect(dayOptions('seasonal_start_day')).not.toContain('31');
    });

    it('defaults a fresh form to day 01, not the month end', async () => {
        const { populateSeasonalDays } = await mount();
        populateSeasonalDays();

        // Nothing was selected before, so the form must not silently start at
        // January 31 — a user who only picks the month would otherwise save a
        // month-end boundary they never chose.
        expect(document.getElementById('seasonal_start_day').value).toBe('01');
        expect(document.getElementById('seasonal_end_day').value).toBe('01');
    });

    it('gives April 30 days and January 31', async () => {
        const { populateSeasonalDays } = await mount();
        populateSeasonalDays();

        document.getElementById('seasonal_end_month').value = '04';
        document
            .getElementById('seasonal_end_month')
            .dispatchEvent(new Event('change'));
        expect(dayOptions('seasonal_end_day')).toHaveLength(30);

        document.getElementById('seasonal_end_month').value = '01';
        document
            .getElementById('seasonal_end_month')
            .dispatchEvent(new Event('change'));
        expect(dayOptions('seasonal_end_day')).toHaveLength(31);
    });

    it('clamps a day that no longer exists to the end of the new month', async () => {
        const { populateSeasonalDays } = await mount();
        populateSeasonalDays();

        const month = document.getElementById('seasonal_start_month');
        const day = document.getElementById('seasonal_start_day');
        month.value = '01';
        day.value = '31';

        month.value = '02';
        month.dispatchEvent(new Event('change'));

        expect(day.value).toBe('29');
    });

    it('keeps a still-valid day when the month changes', async () => {
        const { populateSeasonalDays } = await mount();
        populateSeasonalDays();

        const month = document.getElementById('seasonal_start_month');
        const day = document.getElementById('seasonal_start_day');
        month.value = '01';
        month.dispatchEvent(new Event('change'));
        day.value = '15';

        month.value = '03';
        month.dispatchEvent(new Event('change'));

        expect(day.value).toBe('15');
    });

    it('restores a stored MM-DD value exactly', async () => {
        const { populateSeasonalDays, setSeasonalDate } = await mount();
        populateSeasonalDays();

        setSeasonalDate('seasonal_start', '12-01');
        setSeasonalDate('seasonal_end', '02-28');

        expect(document.getElementById('seasonal_start_month').value).toBe('12');
        expect(document.getElementById('seasonal_start_day').value).toBe('01');
        expect(document.getElementById('seasonal_end_month').value).toBe('02');
        // February must have been re-filled before the day was assigned,
        // otherwise selecting 28 would be fine but 29 would silently fail.
        expect(document.getElementById('seasonal_end_day').value).toBe('28');
    });

    it('restores a leap day stored for February', async () => {
        const { populateSeasonalDays, setSeasonalDate } = await mount();
        populateSeasonalDays();

        setSeasonalDate('seasonal_start', '02-29');

        expect(document.getElementById('seasonal_start_month').value).toBe('02');
        expect(document.getElementById('seasonal_start_day').value).toBe('29');
    });

    it('ignores a missing or malformed stored value', async () => {
        const { populateSeasonalDays, setSeasonalDate } = await mount();
        populateSeasonalDays();

        expect(() => setSeasonalDate('seasonal_start', undefined)).not.toThrow();
        expect(() => setSeasonalDate('seasonal_start', '')).not.toThrow();
        expect(() => setSeasonalDate('seasonal_start', 'nonsense')).not.toThrow();
        expect(() => setSeasonalDate('seasonal_start', '12')).not.toThrow();
    });

    it('re-syncs both lists from their selected months', async () => {
        const { populateSeasonalDays, syncSeasonalDayLists } = await mount();
        populateSeasonalDays();

        // Simulate a month change that bypassed the change handler (the form
        // is reset by assigning values, not by user interaction).
        document.getElementById('seasonal_start_month').value = '02';
        document.getElementById('seasonal_end_month').value = '04';
        syncSeasonalDayLists();

        expect(dayOptions('seasonal_start_day')).toHaveLength(29);
        expect(dayOptions('seasonal_end_day')).toHaveLength(30);
    });

    it('clamps a legacy stored day that no longer exists', async () => {
        const { populateSeasonalDays, setSeasonalDate } = await mount();
        populateSeasonalDays();

        // A config saved before the validation fix can hold 02-31. Assigning
        // it unchanged would leave the select empty and the form would POST
        // "02-", so it is clamped to the last real day of February.
        setSeasonalDate('seasonal_start', '02-31');

        expect(document.getElementById('seasonal_start_month').value).toBe('02');
        expect(document.getElementById('seasonal_start_day').value).toBe('29');
    });

    it('never yields a date the backend rejects', async () => {
        const { populateSeasonalDays } = await mount();
        populateSeasonalDays();

        // For every month, the last offered day must be a real calendar day.
        const monthSelect = document.getElementById('seasonal_start_month');
        const daySelect = document.getElementById('seasonal_start_day');
        for (const month of Array.from(monthSelect.options).map((o) => o.value)) {
            monthSelect.value = month;
            monthSelect.dispatchEvent(new Event('change'));
            const days = dayOptions('seasonal_start_day');
            const last = days[days.length - 1];
            // New Date(2024, month, 0).getDate() is the real day count.
            const expected = new Date(2024, parseInt(month, 10), 0).getDate();
            expect(parseInt(last, 10)).toBe(expected);
            expect(daySelect.value).toBeTruthy();
        }
    });
});
