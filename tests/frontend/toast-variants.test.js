/**
 * Regression tests for toast styling.
 *
 * `showToast(msg, type)` sets `class="status-msg <type>"` and relies on
 * `components.css` to give that class its colours. Only `.success` and
 * `.error` had a rule. `cleanup.js` reports a partially successful delete with
 * `showToast(msg, 'warning')`, so that toast fell through to the bare
 * `.status-msg` rule — no background, no border, inherited text colour — and
 * rendered as unstyled text in the corner while it named the folders that
 * could NOT be deleted.
 *
 * The CSS is not executed by any other test, so nothing failed when a new type
 * was introduced without a rule. These tests read the real stylesheet, apply
 * it to the real `showToast()`, and check every type the frontend actually
 * passes.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

// `import.meta.url` is rewritten to a Vite `/@fs/...` URL under vitest; the
// project root is the working directory vitest was started in.
const ROOT = process.cwd();
const COMPONENTS_CSS = readFileSync(join(ROOT, 'static/css/components.css'), 'utf8');
const VARIABLES_CSS = readFileSync(join(ROOT, 'static/css/variables.css'), 'utf8');
const JS_ROOT = join(ROOT, 'static/js');

/**
 * Resolve `var(--name)` to its hex value from the dark-theme `:root` block.
 *
 * The toast rules state their colours as variables, so reading the declaration
 * text alone yields `var(--warning-color)` rather than a colour.
 *
 * @param {string} value A CSS value, possibly a `var(...)` reference.
 * @returns {string} The hex colour, or *value* unchanged.
 */
function resolveColor(value) {
    const ref = value.match(/^var\(\s*(--[\w-]+)\s*\)$/);
    if (!ref) return value.trim();
    // The first `:root` block is the dark theme; later blocks are overrides.
    const root = VARIABLES_CSS.slice(0, VARIABLES_CSS.indexOf('@media'));
    const declared = root.match(
        new RegExp(`${ref[1]}\\s*:\\s*(#[0-9a-fA-F]{6})`)
    );
    if (!declared) throw new Error(`${ref[1]} is not defined in variables.css`);
    return declared[1];
}

/** Type tokens `showToast()` understands and that CSS must therefore style. */
const KNOWN_TYPES = ['success', 'error', 'warning', 'info'];

/**
 * Return the source text of every `showToast(...)` call under `static/js`.
 *
 * Walks characters rather than using one regex because the type argument is
 * sometimes a ternary (`status === 'partial_success' ? 'warning' : 'success'`),
 * whose parentheses and quotes a simple pattern cannot delimit reliably.
 *
 * @param {string} source
 * @returns {string[]} Call bodies, one per call site.
 */
function showToastCalls(source) {
    const calls = [];
    const NEEDLE = 'showToast(';
    let from = 0;
    for (;;) {
        const start = source.indexOf(NEEDLE, from);
        if (start === -1) break;
        let depth = 0;
        let i = start + NEEDLE.length - 1;
        for (; i < source.length; i += 1) {
            const ch = source[i];
            if (ch === '(') depth += 1;
            else if (ch === ')') {
                depth -= 1;
                if (depth === 0) break;
            }
        }
        calls.push(source.slice(start + NEEDLE.length, i));
        from = i + 1;
    }
    return calls;
}

/** Recursively list `.js` files below *dir*. */
function jsFiles(dir) {
    const out = [];
    for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) out.push(...jsFiles(path));
        else if (name.endsWith('.js')) out.push(path);
    }
    return out;
}

/**
 * Every toast type the frontend passes, e.g. `['error', 'success', 'warning']`.
 *
 * @returns {string[]} Sorted, de-duplicated type tokens.
 */
function typesUsedInFrontend() {
    const used = new Set();
    for (const file of jsFiles(JS_ROOT)) {
        const source = readFileSync(file, 'utf8');
        for (const body of showToastCalls(source)) {
            for (const match of body.matchAll(/'([a-z]+)'/g)) {
                if (KNOWN_TYPES.includes(match[1])) used.add(match[1]);
            }
        }
    }
    return [...used].sort();
}

/** Return the declarations of the `.status-msg.<type>` rule, or null. */
function ruleFor(type) {
    const match = COMPONENTS_CSS.match(
        new RegExp(`\\.status-msg\\.${type}\\s*\\{([^}]*)\\}`)
    );
    return match ? match[1] : null;
}

beforeEach(() => {
    // A clean DOM per test: showToast() appends a close button to #status-msg.
    document.body.innerHTML = '<div id="status-msg" class="status-msg" aria-hidden="true"></div>';
    const prior = document.getElementById('toast-css');
    if (prior) prior.remove();
    const style = document.createElement('style');
    style.id = 'toast-css';
    style.textContent = COMPONENTS_CSS;
    document.head.appendChild(style);
    const vars = readFileSync(join(ROOT, 'static/css/variables.css'), 'utf8');
    const varsStyle = document.createElement('style');
    varsStyle.textContent = vars;
    document.head.appendChild(varsStyle);
});

describe('toast type coverage', () => {
    it('finds the toast types the frontend passes', () => {
        // A parser that matched nothing would make the coverage test vacuous.
        const types = typesUsedInFrontend();
        expect(types).toContain('success');
        expect(types).toContain('error');
        expect(types).toContain('warning');
    });

    it.each(KNOWN_TYPES)('styles the %s toast', (type) => {
        const declarations = ruleFor(type);
        expect(declarations, `.status-msg.${type} has no CSS rule`).not.toBeNull();
        expect(declarations).toMatch(/background\s*:/);
        expect(declarations).toMatch(/color\s*:/);
        expect(declarations).toMatch(/border\s*:/);
    });

    it('gives every type used in the frontend its own rule', () => {
        const unstyled = typesUsedInFrontend().filter((type) => ruleFor(type) === null);
        expect(unstyled, `toast type(s) without a CSS rule: ${unstyled.join(', ')}`).toEqual([]);
    });

    it.each(KNOWN_TYPES)('renders the %s toast with a visible surface', async (type) => {
        // jsdom resolves the real cascade, so this catches a rule that exists
        // but is overridden or empty — which is how the warning toast broke.
        const { showToast } = await import('../../static/js/core/ui.js');
        showToast('message', type);

        const el = document.getElementById('status-msg');
        const styles = window.getComputedStyle(el);

        expect(el.className).toBe(`status-msg ${type}`);
        expect(styles.display).toBe('block');
        expect(styles.backgroundColor).not.toBe('');
        expect(styles.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
        expect(styles.borderTopWidth).not.toBe('0px');
    });
});

/** Parse `#rrggbb` into relative luminance (WCAG 2.x definition). */
function luminance(hex) {
    const value = hex.replace('#', '');
    const channels = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255);
    const linear = channels.map((c) =>
        c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
    );
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

/** Composite an `rgba(...)` foreground over an opaque `#rrggbb` background. */
function composite(rgba, background) {
    const nums = rgba.match(/[\d.]+/g).map(Number);
    const alpha = nums.length > 3 ? nums[3] : 1;
    const bg = background.replace('#', '');
    const out = [0, 2, 4].map((i, index) => {
        const over = parseInt(bg.slice(i, i + 2), 16);
        return Math.round(nums[index] * alpha + over * (1 - alpha));
    });
    return `#${out.map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}

/** WCAG contrast ratio between two opaque `#rrggbb` colours. */
function contrast(a, b) {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
}

/**
 * Contrast of a `.status-msg.<type>` rule's text against its own background.
 *
 * @param {string} type
 * @param {string} surface The page surface the tinted background sits on.
 * @param {string|null} textColor Override for the text colour, to exercise the
 *   light-mode override rather than resolving it through the media query.
 * @returns {number} WCAG contrast ratio.
 */
function toastContrast(type, surface, textColor = null) {
    const declarations = ruleFor(type);
    const color = textColor || resolveColor(
        declarations.match(/color:\s*([^;]+);/)[1]
    );
    const background = declarations.match(/background:\s*([^;]+);/)[1].trim();
    return contrast(color, composite(background, surface));
}

describe('toast contrast', () => {
    const SURFACES = {
        dark: '#1a1a24',
        light: '#ffffff',
    };

    it.each(KNOWN_TYPES)('%s toast meets WCAG AA on the dark surface', (type) => {
        // Toast body text is 0.85rem/500 — below the 18.66px-bold large-text
        // threshold, so AA requires 4.5:1, not 3:1.
        expect(toastContrast(type, SURFACES.dark)).toBeGreaterThanOrEqual(4.5);
    });

    it('darkens every toast variant for the light surface', () => {
        // The shared theme colours are too pale on white, so components.css
        // overrides the text colour inside a prefers-color-scheme block. Read
        // those overrides out of the stylesheet instead of hardcoding them, so
        // the test fails if the block is dropped or a variant is left out.
        const light = COMPONENTS_CSS.match(
            /@media\s*\(prefers-color-scheme:\s*light\)\s*\{([\s\S]*?\n\}\n)/
        );
        expect(light, 'no prefers-color-scheme: light block for toasts').not.toBeNull();

        const overrides = {};
        for (const [, type, color] of light[1].matchAll(
            /\.status-msg\.(\w+)\s*\{\s*color:\s*(#[0-9a-fA-F]{6});/g
        )) {
            overrides[type] = color;
        }

        for (const type of KNOWN_TYPES) {
            expect(overrides[type], `${type} has no light-mode text colour`).toBeDefined();
            const ratio = toastContrast(type, SURFACES.light, overrides[type]);
            expect(ratio, `${type} toast on white is ${ratio.toFixed(2)}:1`)
                .toBeGreaterThanOrEqual(4.5);
        }
    });
});
