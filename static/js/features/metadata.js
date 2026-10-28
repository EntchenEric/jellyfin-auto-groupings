// metadata.js – Metadata fetching and source type UI logic

import { state, sourceOptions, metadataTypes, resolveSourceCategory } from '../core/state.js';
import { fetchMetadata, fetchUsers, apiPost } from '../core/api.js';
import { getEl } from '../core/ui.js';

export async function refreshMetadata(onStatus) {
    if (onStatus) onStatus('Fetching genres, actors, studios, and tags...');
    const result = await fetchMetadata();
    if (result.status === 'success') {
        state.cachedMetadata = result.metadata;
        updateSourceValueUI();
    } else {
        throw new Error(result.message || 'Failed to load metadata from Jellyfin server');
    }
}

export function updateSourceTypeOptions(sourceTypeHint = null) {
    const categoryEl = getEl('source_category');
    if (!categoryEl) return;

    // A stored or imported group can name a category this build does not
    // know; the select then holds no valid option and the lookup below is
    // undefined. Normalise it against the group's own source type first, so
    // one bad value cannot blank the dropdown (and abort the caller).
    const category = resolveSourceCategory(categoryEl.value, sourceTypeHint ?? '');
    if (categoryEl.value !== category) {
        categoryEl.value = category;
    }

    const typeSelect = getEl('source_type');
    if (!typeSelect) return;
    const currentValue = typeSelect.value;

    typeSelect.innerHTML = '';
    sourceOptions[category].forEach(opt => {
        const o = document.createElement('option');
        o.value = opt.value;
        let isDisabled = false;
        if (opt.requiredKey) {
            // A hand-edited config.json can hold a number or null here; a bare
            // `.trim()` on those threw and emptied the whole dropdown.
            const rawKey = state.currentConfig[opt.requiredKey];
            const keyText = typeof rawKey === 'string' ? rawKey.trim() : '';
            isDisabled = keyText === '';
        }
        if (isDisabled) {
            let missingName = 'Key';
            if (opt.requiredKey === 'tmdb_api_key') missingName = 'TMDb API Key';
            else if (opt.requiredKey === 'trakt_client_id') missingName = 'Trakt Client ID';
            else if (opt.requiredKey === 'mal_client_id') missingName = 'MAL Client ID';
            o.textContent = `${opt.label} (${missingName} missing)`;
            o.disabled = true;
        } else {
            o.textContent = opt.label;
        }
        typeSelect.appendChild(o);
    });

    const validOptions = Array.from(typeSelect.options).filter(opt => !opt.disabled).map(opt => opt.value);
    if (validOptions.includes(currentValue)) {
        typeSelect.value = currentValue;
    } else if (validOptions.length > 0) {
        typeSelect.value = validOptions[0];
    }
    updateSourceValueUI();
}

export function getFilterValue() {
    const type = getEl('source_type').value;
    const isMetadataType = metadataTypes.includes(type);
    if (isMetadataType && state.isServerValidated) {
        const validRules = window._currentMetadataRules.filter(r => r.value && r.value.trim() !== '');
        if (validRules.length === 0) return '';
        const parts = validRules.map((r, i) => {
            const prefix = type === 'complex' ? `${r.type || 'genre'}:` : '';
            return i === 0 ? `${prefix}${r.value.trim()}` : `${r.operator} ${prefix}${r.value.trim()}`;
        });
        return parts.join(' ');
    }
    return getEl('source_value').value.trim();
}

export function parseMetadataValue(valStr) {
    if (!valStr || valStr.trim() === '') return [{ operator: '', value: '' }];
    const pattern = /\s+(AND NOT|OR NOT|AND|OR)\s+/i;
    const parts = valStr.split(pattern);
    const rules = [];
    const parseRule = (s) => {
        const match = s.trim().match(/^(\w+):(.+)$/);
        if (match) return { type: match[1].toLowerCase(), value: match[2].trim() };
        return { value: s.trim() };
    };
    const first = parseRule(parts[0]);
    rules.push({ operator: '', ...first });
    for (let i = 1; i < parts.length; i += 2) {
        const rest = parseRule(parts[i + 1]);
        rules.push({ operator: parts[i].trim().toUpperCase().replace(/\s+/g, ' '), ...rest });
    }
    return rules;
}

export function renderMetadataRules() {
    const container = getEl('metadata_rules_container');
    container.innerHTML = '';
    const type = getEl('source_type').value;

    window._currentMetadataRules.forEach((rule, index) => {
        const row = document.createElement('div');
        row.className = 'rule-row';

        // Each control in a rule row is created at runtime and sits next to
        // other look-alike controls, so a screen reader otherwise announced
        // every one of them as an unnamed "combo box"/"edit text". The number
        // is the condition's position in the row list (1-based), which is what
        // the visible order shows.
        const position = index + 1;

        if (index > 0) {
            const opSelect = document.createElement('select');
            opSelect.className = 'rule-operator-select';
            opSelect.setAttribute(
                'aria-label',
                `Condition ${position} operator`,
            );
            ['AND', 'OR', 'AND NOT', 'OR NOT'].forEach(op => {
                const o = document.createElement('option');
                o.value = op; o.textContent = op;
                if (rule.operator === op) o.selected = true;
                opSelect.appendChild(o);
            });
            opSelect.onchange = (e) => { rule.operator = e.target.value; };
            row.appendChild(opSelect);
        }

        if (type === 'complex') {
            const rowTypeSelect = document.createElement('select');
            rowTypeSelect.className = 'rule-type-select';
            rowTypeSelect.setAttribute(
                'aria-label',
                `Condition ${position} field`,
            );
            ['genre', 'actor', 'studio', 'tag', 'year'].forEach(t => {
                const o = document.createElement('option');
                o.value = t; o.textContent = t.charAt(0).toUpperCase() + t.slice(1);
                if (rule.type === t || (!rule.type && t === 'genre')) o.selected = true;
                if (!rule.type) rule.type = 'genre';
                rowTypeSelect.appendChild(o);
            });
            rowTypeSelect.onchange = (e) => { rule.type = e.target.value; renderMetadataRules(); };
            row.appendChild(rowTypeSelect);
        }

        const rowType = type === 'complex' ? rule.type : type;

        // Years are free-form (a literal year, a comma-separated list, or a
        // comparison like ">=2000"), and the metadata endpoint does not
        // provide a year list to populate a dropdown from. Without this
        // branch the row rendered an empty <select> that held only the
        // disabled placeholder, so a year rule could not be entered at all.
        if (rowType === 'year') {
            const valInput = document.createElement('input');
            valInput.type = 'text';
            valInput.className = 'rule-value-input';
            valInput.setAttribute(
                'aria-label',
                `Condition ${position} ${rowType} value`,
            );
            valInput.placeholder = 'e.g. 2000, 1999,2000, or >=2000';
            valInput.value = rule.value || '';
            valInput.oninput = (e) => { rule.value = e.target.value; };
            row.appendChild(valInput);
        } else {
            const options = state.cachedMetadata[rowType] || [];
            const valSelect = document.createElement('select');
            valSelect.className = 'rule-value-select';
            valSelect.setAttribute(
                'aria-label',
                `Condition ${position} ${rowType} value`,
            );

            const defaultOpt = document.createElement('option');
            defaultOpt.value = ''; defaultOpt.textContent = 'Select ' + rowType + '...'; defaultOpt.disabled = true; defaultOpt.selected = !rule.value;
            valSelect.appendChild(defaultOpt);

            let foundMatch = false;
            options.forEach(opt => {
                const o = document.createElement('option');
                o.value = opt; o.textContent = opt;
                if (rule.value === opt) { o.selected = true; foundMatch = true; }
                valSelect.appendChild(o);
            });
            if (rule.value && !foundMatch) {
                const o = document.createElement('option');
                o.value = rule.value; o.textContent = rule.value + " (Custom)"; o.selected = true;
                valSelect.appendChild(o);
            }
            valSelect.onchange = (e) => { rule.value = e.target.value; };
            row.appendChild(valSelect);
        }

        if (index > 0) {
            const rmBtn = document.createElement('button');
            rmBtn.type = 'button';
            // The button holds only an icon, so it needs its own accessible
            // name; `title` alone is not reliably exposed by every screen
            // reader. The <svg> is decorative and must not be announced as an
            // unnamed graphic before the label (WCAG 1.1.1 / 4.1.2).
            rmBtn.innerHTML = '<svg aria-hidden="true" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>';
            rmBtn.className = 'delete-btn rule-remove-btn';
            rmBtn.title = 'Remove condition';
            rmBtn.setAttribute('aria-label', 'Remove condition');
            rmBtn.onclick = () => { window._currentMetadataRules.splice(index, 1); renderMetadataRules(); };
            row.appendChild(rmBtn);
        }
        container.appendChild(row);
    });
}

export function updateSourceValueUI(preValue = null) {
    const type = getEl('source_type').value;
    const isMetadataType = metadataTypes.includes(type);
    const container = getEl('metadata_rules_container');
    const addBtn = getEl('add-rule-btn');
    const sourceValueInput = getEl('source_value');
    const sourceValueHelp = getEl('source_value_help');

    const userSelect = getEl('source_value_user_select');
    if (userSelect) userSelect.style.display = 'none';

    // The grouping form is the only place these controls exist, but this
    // function is also called after a config save and from the wizard, which
    // can run against a partial document. A missing element used to throw
    // here and abort the whole refresh, leaving every control that *is*
    // present in its previous state.
    if (!sourceValueInput || !sourceValueHelp || !container || !addBtn) {
        return;
    }

    sourceValueInput.style.display = 'block';
    sourceValueInput.required = true;
    sourceValueInput.disabled = false;

    if (isMetadataType) {
        sourceValueHelp.style.display = 'block';
        if (state.isServerValidated) {
            sourceValueInput.style.display = 'none';
            sourceValueInput.required = false;
            container.style.display = 'flex';
            addBtn.style.display = 'inline-block';
            if (type !== state.lastRenderedType || preValue) {
                if (preValue) {
                    window._currentMetadataRules = parseMetadataValue(preValue);
                } else {
                    window._currentMetadataRules = [{ operator: '', value: '' }];
                }
                state.lastRenderedType = type;
            }
            renderMetadataRules();
            if (type === 'year') {
                sourceValueHelp.innerHTML = 'Enter years as a literal (<code>2000</code>), a list (<code>1999,2000</code>), or a comparison (<code>&gt;=2000</code>).';
            } else {
                sourceValueHelp.textContent = `Select one or more ${type}s from your Jellyfin server.`;
            }
        } else {
            container.style.display = 'none';
            addBtn.style.display = 'none';
            if (type === 'year') {
                sourceValueHelp.innerHTML = 'Enter years as a literal (<code>2000</code>), a list (<code>1999,2000</code>), or a comparison (<code>&gt;=2000</code>).';
                sourceValueInput.placeholder = 'e.g. 2000  or  >=2000';
            } else {
                sourceValueHelp.innerHTML = `Connect Jellyfin for autocompletion. Or type manually: <code>Horror AND Action AND NOT Comedy</code>`;
                // Clear the year hint, which would otherwise linger after
                // switching away from `year` to another metadata type.
                sourceValueInput.placeholder = '';
            }
            if (preValue) sourceValueInput.value = preValue;
        }
    } else {
        container.style.display = 'none';
        addBtn.style.display = 'none';
        if (preValue) sourceValueInput.value = preValue;
        const helpTexts = {
            'imdb_list': ['e.g. ls000024390', 'IMDb list ID or full URL.'],
            'trakt_list': ['https://trakt.tv/users/username/lists/list-slug', 'Full Trakt list URL. Requires Trakt Client ID.'],
            'tmdb_list': ['e.g. 12345', 'TMDb list ID or full URL.'],
            'anilist_list': ['e.g. username', 'AniList username, optionally with status.'],
            'mal_list': ['e.g. username', 'MAL username, optionally with status.'],
            'general': ['e.g. Action  or  tt1234567', 'Item name or date range.'],
            'recommendations': ['', ''],
        };
        const h = helpTexts[type];
        if (h) {
            sourceValueInput.placeholder = h[0];
            sourceValueHelp.textContent = h[1] || '';
        } else {
            sourceValueInput.placeholder = 'e.g. Action  or  ls000024390';
            sourceValueHelp.textContent = 'Enter the value manually.';
        }

        if (type === 'recommendations') {
            let userSel = getEl('source_value_user_select');
            if (!userSel) {
                userSel = document.createElement('select');
                userSel.id = 'source_value_user_select';
                userSel.className = 'user-select';
                // Built at runtime next to the hidden filter input, so without
                // an explicit name it was announced as a bare "combo box".
                userSel.setAttribute('aria-label', 'Jellyfin user');
                userSel.onchange = (e) => { sourceValueInput.value = e.target.value; };
                getEl('source_value_container').insertBefore(userSel, sourceValueInput);
            }
            if (state.isServerValidated) {
                sourceValueHelp.innerHTML = 'Select a Jellyfin user. Requires <strong>TMDb API Key</strong>.';
                sourceValueInput.style.display = 'none';
                sourceValueInput.required = false;
                userSel.style.display = 'block';
                userSel.innerHTML = '<option value="" disabled selected>Loading users...</option>';
                userSel.disabled = true;
                fetchUsers().then(data => {
                    userSel.disabled = false;
                    if (data.status === 'success') {
                        userSel.innerHTML = '<option value="" disabled selected>Select User...</option>';
                        data.users.forEach(u => {
                            const opt = document.createElement('option');
                            opt.value = u.id; opt.textContent = u.name;
                            if (preValue && preValue === u.id) opt.selected = true;
                            userSel.appendChild(opt);
                        });
                        if (preValue) userSel.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }).catch(() => { userSel.innerHTML = '<option value="">Error loading users</option>'; });
            } else {
                sourceValueInput.style.display = 'block';
                sourceValueInput.required = true;
                if (preValue) sourceValueInput.value = preValue;
                userSel.style.display = 'none';
            }
        }
    }
}

export function addMetadataRule() {
    window._currentMetadataRules.push({ operator: 'AND', value: '' });
    renderMetadataRules();
}

export function initMetadata() {
    getEl('source_category').onchange = updateSourceTypeOptions;
    getEl('source_type').onchange = () => updateSourceValueUI();
    getEl('add-rule-btn').onclick = addMetadataRule;
    // Expose to window for app.js cross-module event wiring
    window.updateSourceTypeOptions = updateSourceTypeOptions;
    window.updateSourceValueUI = updateSourceValueUI;
}

export async function previewGrouping() {
    const type = getEl('source_type').value;
    const val = getFilterValue();
    const resultDiv = getEl('preview_result');

    // External list sources and recommendations also support preview
    const previewableTypes = [...metadataTypes, 'general',
        'imdb_list', 'trakt_list', 'tmdb_list',
        'anilist_list', 'mal_list', 'letterboxd_list',
        'recommendations'];

    if (!previewableTypes.includes(type)) {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<span style="color:var(--text-secondary);">Preview not supported for this source type.</span>';
        return;
    }
    if (!val) {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<span style="color:var(--error-color);">Please enter a filter value.</span>';
        return;
    }

    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<span class="loading-spinner" style="display:inline-block; margin-right:0.5rem; border-color:rgba(255,255,255,0.2); border-left-color:var(--accent-color);"></span> Loading preview...';

    try {
        const res = await apiPost('/api/grouping/preview', {
            type, value: val, watch_state: getEl('watch_state').value,
            item_type: getEl('item_type').value
        });
        resultDiv.innerHTML = '';
        if (res.status === 'success') {
            const summary = document.createElement('div');
            summary.innerHTML = `<strong>Estimated Items:</strong> <span style="color:var(--accent-color);">${res.count}</span>`;
            resultDiv.appendChild(summary);
            if (res.count > 0 && res.preview_items) {
                const ul = document.createElement('ul');
                ul.className = 'metadata-results-list';
                res.preview_items.forEach(item => {
                    const li = document.createElement('li');
                    li.textContent = item.Year ? `${item.Name} (${item.Year})` : item.Name;
                    ul.appendChild(li);
                });
                resultDiv.appendChild(ul);
            }
        } else {
            resultDiv.textContent = '';
            const errSpan = document.createElement('span');
            errSpan.style.color = 'var(--error-color)';
            errSpan.textContent = `Error: ${res.message || 'Preview failed'}`;
            resultDiv.appendChild(errSpan);
        }
    } catch (err) {
        resultDiv.innerHTML = '<span style="color:var(--error-color);">Network error during preview.</span>';
    }
}

