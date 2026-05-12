// metadata.js – Metadata fetching and source type UI logic

import { state, sourceOptions, metadataTypes } from '../core/state.js';
import { fetchMetadata, fetchUsers, apiPost } from '../core/api.js';
import { getEl } from '../core/ui.js';

export async function refreshMetadata() {
    try {
        const result = await fetchMetadata();
        if (result.status === 'success') {
            state.cachedMetadata = result.metadata;
            updateSourceValueUI();
        } else {
            console.error('Failed to load metadata from Jellyfin server');
        }
    } catch (err) {
        console.error('Failed to fetch metadata:', err);
    }
}

export function updateSourceTypeOptions() {
    const category = getEl('source_category').value;
    const typeSelect = getEl('source_type');
    const currentValue = typeSelect.value;

    typeSelect.innerHTML = '';
    sourceOptions[category].forEach(opt => {
        const o = document.createElement('option');
        o.value = opt.value;
        let isDisabled = false;
        if (opt.requiredKey && (!state.currentConfig[opt.requiredKey] || state.currentConfig[opt.requiredKey].trim() === '')) {
            isDisabled = true;
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
        if (match) return { type: match[1], value: match[2].trim() };
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
        row.setAttribute('style', 'display: flex; gap: 0.5rem; align-items: center; width: 100%;');

        if (index > 0) {
            const opSelect = document.createElement('select');
            opSelect.setAttribute('style', 'flex: 0 0 auto; padding: 0.8rem; background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); border-radius: var(--radius-md); color: var(--text-primary); font-size: 0.9rem; font-weight: 600;');
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
            rowTypeSelect.setAttribute('style', 'flex: 0 0 auto; width: 110px; padding: 0.8rem; background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); border-radius: var(--radius-md); color: var(--text-primary); font-size: 0.9rem;');
            ['genre', 'actor', 'studio', 'tag'].forEach(t => {
                const o = document.createElement('option');
                o.value = t; o.textContent = t.charAt(0).toUpperCase() + t.slice(1);
                if (rule.type === t || (!rule.type && t === 'genre')) o.selected = true;
                if (!rule.type) rule.type = 'genre';
                rowTypeSelect.appendChild(o);
            });
            rowTypeSelect.onchange = (e) => { rule.type = e.target.value; renderMetadataRules(); };
            row.appendChild(rowTypeSelect);
        }

        const rowType = type === 'complex' ? (rule.type || 'genre') : type;
        const options = state.cachedMetadata[rowType] || [];
        const valSelect = document.createElement('select');
        valSelect.setAttribute('style', 'flex: 1; padding: 0.8rem 1rem; background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); border-radius: var(--radius-md); color: var(--text-primary); font-size: 1rem;');

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

        if (index > 0) {
            const rmBtn = document.createElement('button');
            rmBtn.type = 'button';
            rmBtn.innerHTML = '<svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/></svg>';
            rmBtn.className = 'delete-btn';
            rmBtn.title = 'Remove condition';
            rmBtn.setAttribute('style', 'padding: 0; width: 38px; height: 38px; display:flex; align-items:center; justify-content:center; margin: 0; flex-shrink: 0;');
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
            sourceValueHelp.textContent = `Select one or more ${type}s from your Jellyfin server.`;
        } else {
            container.style.display = 'none';
            addBtn.style.display = 'none';
            sourceValueHelp.innerHTML = `Connect Jellyfin for autocompletion. Or type manually: <code>Horror AND Action AND NOT Comedy</code>`;
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
                userSel.setAttribute('style', 'flex: 1; padding: 0.8rem 1rem; background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); border-radius: var(--radius-md); color: var(--text-primary); font-size: 1rem; width: 100%;');
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
}

export async function previewGrouping() {
    const type = getEl('source_type').value;
    const val = getFilterValue();
    const resultDiv = getEl('preview_result');

    if (!metadataTypes.includes(type) && type !== 'general') {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<span style="color:var(--text-secondary);">Preview supports Jellyfin metadata types (Genre, Actor, etc).</span>';
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
            type, value: val, watch_state: getEl('watch_state').value
        });
        resultDiv.innerHTML = '';
        if (res.status === 'success') {
            const summary = document.createElement('div');
            summary.innerHTML = `<strong>Estimated Items:</strong> <span style="color:var(--accent-color);">${res.count}</span>`;
            resultDiv.appendChild(summary);
            if (res.count > 0 && res.preview_items) {
                const ul = document.createElement('ul');
                ul.setAttribute('style', 'margin-top:0.4rem; padding-left:1.5rem; color:var(--text-secondary);');
                res.preview_items.forEach(item => {
                    const li = document.createElement('li');
                    li.textContent = item.Year ? `${item.Name} (${item.Year})` : item.Name;
                    ul.appendChild(li);
                });
                resultDiv.appendChild(ul);
            }
        } else {
            resultDiv.innerHTML = `<span style="color:var(--error-color);">Error: ${res.message}</span>`;
        }
    } catch (err) {
        resultDiv.innerHTML = '<span style="color:var(--error-color);">Network error during preview.</span>';
    }
}

