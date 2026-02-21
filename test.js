
        const configForm = document.getElementById('config-form');
        const apiConfigForm = document.getElementById('api-config-form');
        const groupForm = document.getElementById('group-form');
        const groupFormTitle = document.getElementById('group-form-title');
        const addGroupBtn = document.getElementById('add-group-btn');
        const cancelEditBtn = document.getElementById('cancel-edit-btn');
        const saveBtn = document.getElementById('save-btn');
        const saveApisBtn = document.getElementById('save-apis-btn');
        const testBtn = document.getElementById('test-btn');
        const statusMsg = document.getElementById('status-msg');
        const groupsList = document.getElementById('groups-list');

        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        const maintenanceCard = document.getElementById('maintenance-card');
        const groupingsSection = document.getElementById('groupings-section');

        const sourceValueInput = document.getElementById('source_value');
        const sourceValueSelect = document.getElementById('source_value_select');
        const sourceValueHelp = document.getElementById('source_value_help');

        const sourceOptions = {
            jellyfin: [
                { value: 'general', label: 'General (Title, Date, Rating...)' },
                { value: 'genre', label: 'Genre' },
                { value: 'actor', label: 'Actor' },
                { value: 'studio', label: 'Studio' },
                { value: 'tag', label: 'Jellyfin Tag' }
            ],
            external: [
                { value: 'imdb_list', label: 'IMDb List' },
                { value: 'trakt_list', label: 'Trakt List', requiredKey: 'trakt_client_id' },
                { value: 'tmdb_list', label: 'TMDb List', requiredKey: 'tmdb_api_key' },
                { value: 'anilist_list', label: 'AniList List' },
                { value: 'mal_list', label: 'MyAnimeList List', requiredKey: 'mal_client_id' },
                { value: 'letterboxd_list', label: 'Letterboxd List' }
            ]
        };

        const metadataTypes = ['genre', 'actor', 'studio', 'tag'];

        let currentConfig = { groups: [] };
        let pendingImportData = null;
        let editingIndex = -1;
        let isServerValidated = false;
        let cachedMetadata = {};
        let lastRenderedType = null;
        window._currentMetadataRules = [{ operator: '', value: '' }];

        function getFilterValue() {
            const type = document.getElementById('source_type').value;
            const isMetadataType = metadataTypes.includes(type);
            if (isMetadataType && isServerValidated) {
                const validRules = window._currentMetadataRules.filter(r => r.value && r.value.trim() !== '');
                if (validRules.length === 0) return '';
                const parts = validRules.map((r, i) => (i === 0 ? r.value.trim() : `${r.operator} ${r.value.trim()}`));
                return parts.join(' ');
            }
            return document.getElementById('source_value').value.trim();
        }

        function parseMetadataValue(valStr) {
            if (!valStr || valStr.trim() === '') return [{ operator: '', value: '' }];
            const pattern = /\s+(AND NOT|OR NOT|AND|OR)\s+/i;
            const parts = valStr.split(pattern);
            const rules = [];
            rules.push({ operator: '', value: parts[0].trim() });
            for (let i = 1; i < parts.length; i += 2) {
                rules.push({ operator: parts[i].trim().toUpperCase().replace(/\s+/g, ' '), value: parts[i + 1].trim() });
            }
            return rules;
        }

        function renderMetadataRules() {
            const container = document.getElementById('metadata_rules_container');
            container.innerHTML = '';
            const type = document.getElementById('source_type').value;
            const options = cachedMetadata[type] || [];

            window._currentMetadataRules.forEach((rule, index) => {
                const row = document.createElement('div');
                row.style = 'display: flex; gap: 0.5rem; align-items: center; width: 100%;';

                if (index > 0) {
                    const opSelect = document.createElement('select');
                    opSelect.style = 'flex: 0 0 auto; padding: 0.8rem; background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); border-radius: var(--radius-md); color: var(--text-primary); font-size: 0.9rem; font-weight: 600;';
                    const ops = ['AND', 'OR', 'AND NOT', 'OR NOT'];
                    ops.forEach(op => {
                        const o = document.createElement('option');
                        o.value = op;
                        o.textContent = op;
                        if (rule.operator === op) o.selected = true;
                        opSelect.appendChild(o);
                    });
                    opSelect.onchange = (e) => { rule.operator = e.target.value; };
                    row.appendChild(opSelect);
                }

                const valSelect = document.createElement('select');
                valSelect.style = 'flex: 1; padding: 0.8rem 1rem; background: rgba(0,0,0,0.2); border: 1px solid var(--glass-border); border-radius: var(--radius-md); color: var(--text-primary); font-size: 1rem;';

                const defaultOpt = document.createElement('option');
                defaultOpt.value = '';
                defaultOpt.textContent = 'Select ' + type + '...';
                defaultOpt.disabled = true;
                defaultOpt.selected = !rule.value;
                valSelect.appendChild(defaultOpt);

                let foundMatch = false;
                options.forEach(opt => {
                    const o = document.createElement('option');
                    o.value = opt;
                    o.textContent = opt;
                    if (rule.value === opt) { o.selected = true; foundMatch = true; }
                    valSelect.appendChild(o);
                });

                if (rule.value && !foundMatch) {
                    const o = document.createElement('option');
                    o.value = rule.value;
                    o.textContent = rule.value + " (Unavailable/Custom)";
                    o.selected = true;
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
                    rmBtn.style = 'padding: 0; width: 38px; height: 38px; display:flex; align-items:center; justify-content:center; margin: 0; flex-shrink: 0;';
                    rmBtn.onclick = () => {
                        window._currentMetadataRules.splice(index, 1);
                        renderMetadataRules();
                    };
                    row.appendChild(rmBtn);
                }

                container.appendChild(row);
            });
        }

        function addMetadataRule() {
            window._currentMetadataRules.push({ operator: 'AND', value: '' });
            renderMetadataRules();
        }

        async function previewGrouping() {
            const type = document.getElementById('source_type').value;
            const val = getFilterValue();
            const resultDiv = document.getElementById('preview_result');

            if (!metadataTypes.includes(type) && type !== 'general') {
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<span style="color:var(--text-secondary);">Preview mostly supports Jellyfin library metadata types (Genre, Actor, etc). Try connecting server or checking other logs.</span>';
                return;
            }

            if (!val) {
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<span style="color:var(--error-color);">Please enter a filter value to preview.</span>';
                return;
            }

            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<span class="loading-spinner" style="display:inline-block; margin-right: 0.5rem; border-color: rgba(255,255,255,0.2); border-left-color: var(--accent-color);"></span> <span style="color: var(--text-secondary);">Loading preview...</span>';

            try {
                const response = await fetch('/api/grouping/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: type, value: val })
                });
                const res = await response.json();
                if (res.status === 'success') {
                    let html = `<strong style="color:var(--text-primary);">Estimated Items:</strong> <span style="color:var(--accent-color); font-weight: 600;">${res.count}</span><br><br>`;
                    if (res.count > 0) {
                        html += `<strong>First matches:</strong><ul style="margin-top:0.4rem; padding-left:1.5rem; color:var(--text-secondary);">`;
                        res.preview_items.forEach(item => {
                            html += `<li>${item.Name} ${item.Year ? '(' + item.Year + ')' : ''}</li>`;
                        });
                        html += `</ul>`;
                    }
                    resultDiv.innerHTML = html;
                } else {
                    resultDiv.innerHTML = `<span style="color:var(--error-color);">Error: ${res.message}</span>`;
                }
            } catch (e) {
                resultDiv.innerHTML = `<span style="color:var(--error-color);">Network error during preview.</span>`;
            }
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                currentConfig = await response.json();
                currentConfig.groups = currentConfig.groups || [];

                // Backwards compatibility / Data Migration
                currentConfig.groups.forEach(g => {
                    if (!g.source_category) {
                        if (['imdb_list', 'trakt_list'].includes(g.source_type)) {
                            g.source_category = 'external';
                        } else {
                            g.source_category = 'jellyfin';
                            if (g.source_type === 'jellyfin_tag') g.source_type = 'tag';
                            if (g.source_type === 'people') g.source_type = 'actor';
                        }
                    } else if (g.source_type === 'people') {
                        // Handle cases where category was set but type was still old
                        g.source_type = 'actor';
                    }
                });

                document.getElementById('jellyfin_url').value = currentConfig.jellyfin_url || '';
                document.getElementById('api_key').value = currentConfig.api_key || '';
                document.getElementById('target_path').value = currentConfig.target_path || '';
                document.getElementById('media_path_in_jellyfin').value = currentConfig.media_path_in_jellyfin || currentConfig.jellyfin_root || '';
                document.getElementById('media_path_on_host').value = currentConfig.media_path_on_host || currentConfig.host_root || '';
                document.getElementById('trakt_client_id').value = currentConfig.trakt_client_id || '';
                document.getElementById('tmdb_api_key').value = currentConfig.tmdb_api_key || '';
                document.getElementById('mal_client_id').value = currentConfig.mal_client_id || '';

                updateSourceTypeOptions();
                renderGroups();

                // Initial silent test if we have config
                if (currentConfig.jellyfin_url && currentConfig.api_key) {
                    await performSilentTest();
                }
            } catch (err) {
                showStatus('Failed to load configuration', 'error');
            }
        }

        async function performSilentTest() {
            const data = {
                jellyfin_url: currentConfig.jellyfin_url,
                api_key: currentConfig.api_key
            };
            try {
                const response = await fetch('/api/test-server', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                const isValid = result.status === 'success';
                updateValidationUI(isValid);
                if (isValid) refreshMetadata();
            } catch (err) {
                updateValidationUI(false);
            }
        }

        async function testConnection() {
            testBtn.classList.add('btn-loading');
            const data = {
                jellyfin_url: document.getElementById('jellyfin_url').value,
                api_key: document.getElementById('api_key').value
            };

            try {
                const response = await fetch('/api/test-server', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();

                if (result.status === 'success') {
                    showStatus(result.message, 'success');
                    updateValidationUI(true);
                    // Also save if successful to lock in the working settings
                    currentConfig.jellyfin_url = data.jellyfin_url;
                    currentConfig.api_key = data.api_key;
                    currentConfig.target_path = document.getElementById('target_path').value;
                    await saveAllConfig();
                    await refreshMetadata();
                    // Auto-detect paths only if fields are currently empty
                    await autoDetectIfEmpty();
                } else {
                    showStatus(result.message || 'Connection failed', 'error');
                    updateValidationUI(false);
                }
            } catch (err) {
                showStatus('Connection test failed - API unreachable', 'error');
                updateValidationUI(false);
            } finally {
                testBtn.classList.remove('btn-loading');
            }
        }

        async function refreshMetadata() {
            try {
                // We've deleted the old `<select>`, no loading state required. Data populates into the dropdown silently
                const response = await fetch('/api/jellyfin/metadata');
                const result = await response.json();
                if (result.status === 'success') {
                    cachedMetadata = result.metadata;
                    updateSourceValueUI();
                } else {
                    console.error('Failed to load metadata from Jellyfin server');
                }
            } catch (err) {
                console.error('Failed to fetch metadata:', err);
            }
        }

        function updateSourceTypeOptions() {
            const category = document.getElementById('source_category').value;
            const typeSelect = document.getElementById('source_type');
            const currentValue = typeSelect.value;

            typeSelect.innerHTML = '';
            sourceOptions[category].forEach(opt => {
                const o = document.createElement('option');
                o.value = opt.value;

                // Check if this option requires an API key that is currently missing
                let isDisabled = false;
                if (opt.requiredKey && (!currentConfig[opt.requiredKey] || currentConfig[opt.requiredKey].trim() === '')) {
                    isDisabled = true;
                }

                if (isDisabled) {
                    o.textContent = `${opt.label} (Keys missing - see Server Settings)`;
                    o.disabled = true;
                } else {
                    o.textContent = opt.label;
                }

                typeSelect.appendChild(o);
            });

            // Keep selection if possible and not disabled
            const validOptions = Array.from(typeSelect.options).filter(opt => !opt.disabled).map(opt => opt.value);
            if (validOptions.includes(currentValue)) {
                typeSelect.value = currentValue;
            } else if (validOptions.length > 0) {
                typeSelect.value = validOptions[0];
            }

            // Always update source value UI when type header changes
            updateSourceValueUI();
        }

        function updateSourceValueUI(preValue = null) {
            const type = document.getElementById('source_type').value;
            const isMetadataType = metadataTypes.includes(type);

            const container = document.getElementById('metadata_rules_container');
            const addBtn = document.getElementById('add-rule-btn');

            // Hide old select logic, always use text input
            sourceValueInput.style.display = 'block';
            sourceValueInput.required = true;
            sourceValueInput.disabled = false;

            const datalist = document.getElementById('source_value_datalist');

            if (isMetadataType) {
                sourceValueHelp.style.display = 'block';

                if (isServerValidated) {
                    datalist.innerHTML = '';
                    sourceValueInput.style.display = 'none';
                    sourceValueInput.required = false;
                    container.style.display = 'flex';
                    addBtn.style.display = 'inline-block';

                    if (type !== lastRenderedType || preValue) {
                        if (preValue) {
                            window._currentMetadataRules = parseMetadataValue(preValue);
                        } else {
                            window._currentMetadataRules = [{ operator: '', value: '' }];
                        }
                        lastRenderedType = type;
                    }
                    renderMetadataRules();

                    sourceValueHelp.innerHTML = `Select one or more ${type}s from your Jellyfin server. Use + to combine logic operators.`;
                } else {
                    datalist.innerHTML = '';
                    container.style.display = 'none';
                    addBtn.style.display = 'none';
                    sourceValueHelp.innerHTML = `You must connect your Jellyfin server to see autocompletion. You can manually type a complex filter (e.g. <code>Horror AND Action AND NOT Comedy</code>).`;
                    if (preValue) sourceValueInput.value = preValue;
                }
            } else {
                datalist.innerHTML = '';
                container.style.display = 'none';
                addBtn.style.display = 'none';
                if (preValue) sourceValueInput.value = preValue;
                if (type === 'imdb_list') {
                    sourceValueInput.placeholder = 'e.g. ls000024390 or full IMDb list URL';
                    sourceValueHelp.innerHTML = 'Enter the IMDb list ID (e.g. <code>ls000024390</code>) or paste the full URL — the ID will be extracted automatically.';
                } else if (type === 'trakt_list') {
                    sourceValueInput.placeholder = 'https://trakt.tv/users/username/lists/list-slug';
                    sourceValueHelp.innerHTML = 'Paste the full Trakt list URL. Requires a <strong>Trakt Client ID</strong> in Server Settings. Matches by IMDb ID against your Jellyfin library.';
                } else if (type === 'tmdb_list') {
                    sourceValueInput.placeholder = 'e.g. 12345 or full TMDb list URL';
                    sourceValueHelp.innerHTML = 'Enter the TMDb list ID or paste the full URL. Matches by TMDb ID against your Jellyfin library.';
                } else if (type === 'anilist_list') {
                    sourceValueInput.placeholder = 'e.g. username  or  username/PLANNING';
                    sourceValueHelp.innerHTML = 'Enter your AniList username (e.g. <code>username</code>) or username and status (e.g. <code>username/PLANNING</code>). Matches by AniList ID against your Jellyfin library.';
                } else if (type === 'mal_list') {
                    sourceValueInput.placeholder = 'e.g. username or username/plan_to_watch';
                    sourceValueHelp.innerHTML = 'Enter your MAL username (e.g. <code>username</code>) or username and status (e.g. <code>username/plan_to_watch</code>). Matches by MAL ID against your Jellyfin library.';
                } else if (type === 'general') {
                    sourceValueInput.placeholder = 'e.g. Action  or  tt1234567';
                    sourceValueHelp.textContent = 'Enter item name or date range.';
                } else {
                    sourceValueInput.placeholder = 'e.g. Action  or  ls000024390';
                    sourceValueHelp.textContent = 'Enter the ID or Value manually.';
                }
            }
        }

        function updateValidationUI(isValid) {
            isServerValidated = isValid;

            const pathFieldIds = ['target_path', 'media_path_in_jellyfin', 'media_path_on_host'];
            const pathGroupIds = ['target_path_group', 'media_path_in_jellyfin_group', 'media_path_on_host_group'];

            if (isValid) {
                statusDot.className = 'connection-dot online';
                statusText.textContent = 'Connected';
                maintenanceCard.classList.remove('locked-section');
                groupingsSection.classList.remove('locked-section');
                // Unlock path fields
                pathFieldIds.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.disabled = false;
                });
                pathGroupIds.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) {
                        el.classList.remove('path-field-locked');
                        el.querySelectorAll('button').forEach(b => b.disabled = false);
                    }
                });
            } else {
                statusDot.className = 'connection-dot offline';
                statusText.textContent = 'Disconnected';
                maintenanceCard.classList.add('locked-section');
                groupingsSection.classList.add('locked-section');
                // Lock path fields
                pathFieldIds.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.disabled = true;
                });
                pathGroupIds.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) {
                        el.classList.add('path-field-locked');
                        el.querySelectorAll('button').forEach(b => b.disabled = true);
                    }
                });
            }
            updateSourceTypeOptions();
        }

        function renderGroups() {
            groupsList.innerHTML = '';
            if (!currentConfig.groups || currentConfig.groups.length === 0) {
                groupsList.innerHTML = '<p style="color: var(--text-secondary); text-align: center; font-style: italic; margin-top: 2rem;">No groupings defined yet.</p>';
                return;
            }

            currentConfig.groups.forEach((group, index) => {
                const card = document.createElement('div');
                card.className = 'group-card';

                const catLabel = group.source_category === 'external' ? 'External' : 'Jellyfin';
                const typeLabel = sourceOptions[group.source_category]?.find(opt => opt.value === group.source_type)?.label || group.source_type;

                const sortLabels = {
                    'imdb_list_order': '📋 IMDb List Order',
                    'trakt_list_order': '📋 Trakt List Order',
                    'tmdb_list_order': '🎞️ TMDb List Order',
                    'anilist_list_order': '🎨 AniList List Order',
                    'mal_list_order': '📋 MAL List Order',
                    'CommunityRating': '⭐ Community Rating',
                    'ProductionYear': '📅 Production Year',
                    'SortName': '🔤 Name (A→Z)',
                    'DateCreated': '🕐 Date Added',
                    'Random': '🎲 Random',
                };
                const sortBadge = group.sort_order
                    ? `<span style="display:inline-block; margin-left:0.5rem; font-size:0.72rem; background:rgba(99,102,241,0.15); color:var(--accent-color); border:1px solid rgba(99,102,241,0.3); border-radius:4px; padding:0.1rem 0.4rem;">${sortLabels[group.sort_order] || group.sort_order}</span>`
                    : '';

                card.innerHTML = `
                    <div class="group-info">
                        <h4>${group.name || 'Unnamed Group'}${sortBadge}</h4>
                        <div class="group-meta">
                            <span style="color: var(--accent-color); font-weight: 600;">${catLabel}</span> • ${typeLabel}: ${group.source_value}
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.5rem;">
                        <button class="secondary-btn" onclick="editGroup(${index})" title="Edit Group" style="padding: 0.5rem 0.8rem; font-size: 0.8rem; margin: 0; width: auto; border-color: var(--accent-color); color: var(--accent-color);">
                            Edit
                        </button>
                        <button class="delete-btn" onclick="deleteGroup(${index})" title="Remove Group">
                            <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16" style="margin-right: 4px;">
                                <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                                <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                            </svg>
                            Remove
                        </button>
                    </div>
                `;
                groupsList.appendChild(card);
            });
        }

        async function saveAllConfig() {
            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(currentConfig)
                });
                if (response.ok) {
                    showStatus('Settings saved', 'success');
                    renderGroups();
                    updateSourceTypeOptions();
                } else {
                    showStatus('Server error while saving', 'error');
                }
            } catch (err) {
                showStatus('Network error - changes not saved locally', 'error');
            }
        }

        function showStatus(msg, type) {
            statusMsg.textContent = msg;
            statusMsg.className = `status-msg ${type}`;
            statusMsg.style.display = 'block';
            setTimeout(() => { if (statusMsg.textContent === msg) statusMsg.style.display = 'none'; }, 3000);
        }

        configForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            saveBtn.classList.add('btn-loading');

            currentConfig.jellyfin_url = document.getElementById('jellyfin_url').value;
            currentConfig.api_key = document.getElementById('api_key').value;
            currentConfig.target_path = document.getElementById('target_path').value;
            currentConfig.media_path_in_jellyfin = document.getElementById('media_path_in_jellyfin').value;
            currentConfig.media_path_on_host = document.getElementById('media_path_on_host').value;

            await saveAllConfig();
            saveBtn.classList.remove('btn-loading');

            // Re-trigger metadata discovery after settings change
            await refreshMetadata();
        });

        apiConfigForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            saveApisBtn.classList.add('btn-loading');

            currentConfig.trakt_client_id = document.getElementById('trakt_client_id').value;
            currentConfig.tmdb_api_key = document.getElementById('tmdb_api_key').value;
            currentConfig.mal_client_id = document.getElementById('mal_client_id').value;

            await saveAllConfig();
            saveApisBtn.classList.remove('btn-loading');
        });

        groupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const source_type = document.getElementById('source_type').value;
            const val = getFilterValue();

            if (!val) {
                showStatus('Please enter or select a filter value', 'error');
                return;
            }

            const groupData = {
                name: document.getElementById('group_name').value,
                source_category: document.getElementById('source_category').value,
                source_type: source_type,
                source_value: val,
                sort_order: document.getElementById('sort_order_enabled').checked ? (document.getElementById('sort_order').value || '') : ''
            };

            if (source_type === 'complex') {
                groupData.rules = window._complexRules;
                groupData.source_value = "Custom Multi-Rule Filter";
            }

            if (!currentConfig.groups) currentConfig.groups = [];

            if (editingIndex >= 0) {
                currentConfig.groups[editingIndex] = groupData;
                editingIndex = -1;
            } else {
                currentConfig.groups.push(groupData);
            }

            await saveAllConfig();
            groupForm.reset();
            resetFormUI();
        });

        function editGroup(index) {
            editingIndex = index;
            const group = currentConfig.groups[index];

            document.getElementById('group_name').value = group.name;
            document.getElementById('source_category').value = group.source_category || 'jellyfin';
            updateSourceTypeOptions();
            document.getElementById('source_type').value = group.source_type;
            const hasSortOrder = !!(group.sort_order);
            document.getElementById('sort_order_enabled').checked = hasSortOrder;
            document.getElementById('sort_order_panel').style.display = hasSortOrder ? 'block' : 'none';
            document.getElementById('sort_order').value = group.sort_order || '';

            updateSourceValueUI(group.source_value);

            groupFormTitle.textContent = 'Edit Grouping';
            addGroupBtn.textContent = 'Update Grouping';
            cancelEditBtn.style.display = 'block';

            // Scroll form into view
            groupForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        function cancelEdit() {
            editingIndex = -1;
            groupForm.reset();
            resetFormUI();
        }

        function resetFormUI() {
            groupFormTitle.textContent = 'Create New Grouping';
            addGroupBtn.textContent = 'Add Grouping';
            cancelEditBtn.style.display = 'none';
            document.getElementById('sort_order_enabled').checked = false;
            document.getElementById('sort_order_panel').style.display = 'none';
            updateSourceTypeOptions();
        }

        function toggleSortOrder(checkbox) {
            document.getElementById('sort_order_panel').style.display = checkbox.checked ? 'block' : 'none';
        }

        async function deleteGroup(index) {
            if (confirm('Permanently remove this grouping?')) {
                if (editingIndex === index) cancelEdit();
                currentConfig.groups.splice(index, 1);
                await saveAllConfig();
            }
        }

        async function clearAllGroups() {
            if (confirm('Are you sure you want to remove ALL groupings? This cannot be undone.')) {
                currentConfig.groups = [];
                await saveAllConfig();
            }
        }

        // --- Streamlined Import / Export Logic ---

        function openExportModal() {
            const container = document.getElementById('export-groups-container');
            container.innerHTML = '';

            if (currentConfig.groups.length === 0) {
                container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.9rem;">No groups available to export.</p>';
            } else {
                currentConfig.groups.forEach((g, i) => {
                    const item = document.createElement('div');
                    item.className = 'modal-item';
                    item.innerHTML = `
                        <input type="checkbox" checked class="export-check" data-index="${i}" style="width:18px; height:18px; accent-color: var(--accent-color);">
                        <div>
                            <div style="font-weight:600; font-size:0.95rem;">${g.name}</div>
                            <div style="font-size:0.8rem; color:var(--text-secondary);">${g.source_type}</div>
                        </div>
                    `;
                    container.appendChild(item);
                });
            }

            document.querySelector('input[name="export-type"][value="all"]').checked = true;
            toggleExportSelection();
            document.getElementById('export-modal').style.display = 'flex';
        }

        function toggleExportSelection() {
            const type = document.querySelector('input[name="export-type"]:checked').value;
            document.getElementById('export-selection-list').style.display = (type === 'selective') ? 'block' : 'none';
        }

        function execExport() {
            const type = document.querySelector('input[name="export-type"]:checked').value;
            let dataToExport = {};
            let filename = 'jellyfin-groupings-export.json';

            if (type === 'all') {
                dataToExport = currentConfig;
                filename = 'jellyfin-config-full.json';
            } else {
                const selectedIndices = Array.from(document.querySelectorAll('.export-check:checked'))
                    .map(cb => parseInt(cb.dataset.index));

                if (selectedIndices.length === 0) {
                    alert('Please select at least one grouping.');
                    return;
                }
                dataToExport = { groups: selectedIndices.map(i => currentConfig.groups[i]) };
                filename = 'jellyfin-selected-groupings.json';
            }

            downloadJSON(dataToExport, filename);
            closeModal('export-modal');
        }

        function openImportModal() {
            document.getElementById('import-step-1').style.display = 'block';
            document.getElementById('import-step-2').style.display = 'none';
            document.getElementById('cancel-import-top').style.display = 'block';
            document.getElementById('import-modal').style.display = 'flex';
        }

        function handleFileSelected(event) {
            const file = event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const data = JSON.parse(e.target.result);
                    pendingImportData = data;
                    setupImportStep2(data);
                } catch (err) {
                    showStatus('Invalid JSON file', 'error');
                }
            };
            reader.readAsText(file);
            event.target.value = ''; // Reset
        }

        function setupImportStep2(data) {
            document.getElementById('import-step-1').style.display = 'none';
            document.getElementById('import-step-2').style.display = 'block';
            document.getElementById('cancel-import-top').style.display = 'none';

            const warning = document.getElementById('import-warning');
            const selectionList = document.getElementById('import-selection-list');
            const container = document.getElementById('import-groups-container');
            const confirmBtn = document.getElementById('confirm-import');

            container.innerHTML = '';

            // Detection: Is it a full config or just groups?
            const isFullConfig = data.jellyfin_url !== undefined && data.api_key !== undefined;
            const groups = data.groups || (Array.isArray(data) ? data : null);

            if (isFullConfig) {
                warning.style.display = 'block';
                selectionList.style.display = 'none';
                confirmBtn.textContent = 'Overwrite Over All';
                confirmBtn.onclick = () => performImport('full');
            } else if (groups) {
                warning.style.display = 'none';
                selectionList.style.display = 'block';
                confirmBtn.textContent = 'Import Selected';

                groups.forEach((g, i) => {
                    const item = document.createElement('div');
                    item.className = 'modal-item';
                    item.innerHTML = `
                        <input type="checkbox" checked class="import-check" data-index="${i}" style="width:18px; height:18px; accent-color: var(--accent-color);">
                        <div>
                            <div style="font-weight:600; font-size:0.95rem;">${g.name}</div>
                            <div style="font-size:0.8rem; color:var(--text-secondary);">${g.source_type}: ${g.source_value}</div>
                        </div>
                    `;
                    container.appendChild(item);
                });
                confirmBtn.onclick = () => performImport('groups', groups);
            } else {
                showStatus('Incompatible file structure', 'error');
                closeModal('import-modal');
            }
        }

        async function performImport(type, sourceGroups = null) {
            if (type === 'full') {
                currentConfig = pendingImportData;
            } else {
                const selectedIndices = Array.from(document.querySelectorAll('.import-check:checked'))
                    .map(cb => parseInt(cb.dataset.index));

                const toImport = selectedIndices.map(i => sourceGroups[i]);
                currentConfig.groups = [...currentConfig.groups, ...toImport];
            }

            await saveAllConfig();
            closeModal('import-modal');
            showStatus('Import successful!', 'success');
            loadConfig();
        }

        function downloadJSON(data, filename) {
            const blob = new Blob([JSON.stringify(data, null, 4)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);
        }

        function closeModal(id) {
            document.getElementById(id).style.display = 'none';
            pendingImportData = null;
        }

        async function autoDetectPaths() {
            const detectBtn = document.getElementById('auto-detect-btn');
            detectBtn.classList.add('btn-loading');
            try {
                const result = await fetchAutoDetect();
                if (result.status === 'success' && result.detected.media_path_on_host) {
                    document.getElementById('media_path_in_jellyfin').value = result.detected.media_path_in_jellyfin;
                    document.getElementById('media_path_on_host').value = result.detected.media_path_on_host;
                    document.getElementById('target_path').value = result.detected.target_path;
                    currentConfig.media_path_in_jellyfin = result.detected.media_path_in_jellyfin;
                    currentConfig.media_path_on_host = result.detected.media_path_on_host;
                    currentConfig.target_path = result.detected.target_path;
                    showStatus('Paths auto-detected! Remember to Save.', 'success');
                } else if (result.status === 'success') {
                    showStatus('Auto-detection finished but could not find matching host paths. You may need to set them manually.', 'error');
                } else {
                    showStatus(result.message || 'Auto-detection failed', 'error');
                }
            } catch (err) {
                showStatus('Auto-detection failed - API unreachable', 'error');
            } finally {
                detectBtn.classList.remove('btn-loading');
            }
        }

        async function fetchAutoDetect() {
            const resp = await fetch('/api/jellyfin/auto-detect-paths', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            return resp.json();
        }

        /** Called silently after a successful test; fills only empty path fields. */
        async function autoDetectIfEmpty() {
            const targetEl = document.getElementById('target_path');
            const jfEl = document.getElementById('media_path_in_jellyfin');
            const hostEl = document.getElementById('media_path_on_host');
            if (targetEl.value && jfEl.value && hostEl.value) return;
            try {
                const result = await fetchAutoDetect();
                if (result.status !== 'success') return;
                const d = result.detected;
                if (!targetEl.value && d.target_path) { targetEl.value = d.target_path; currentConfig.target_path = d.target_path; }
                if (!jfEl.value && d.media_path_in_jellyfin) { jfEl.value = d.media_path_in_jellyfin; currentConfig.media_path_in_jellyfin = d.media_path_in_jellyfin; }
                if (!hostEl.value && d.media_path_on_host) { hostEl.value = d.media_path_on_host; currentConfig.media_path_on_host = d.media_path_on_host; }
                showStatus('Paths auto-filled — review and save.', 'success');
            } catch (_) { /* silently ignore */ }
        }

        // ──────────────────────────────────────────────────────────────
        // Folder Picker
        // ──────────────────────────────────────────────────────────────
        let _pickerTargetId = null;
        let _pickerCurrentPath = null;

        async function openPathPicker(fieldId) {
            _pickerTargetId = fieldId;
            const currentVal = document.getElementById(fieldId).value;
            document.getElementById('picker-title').textContent =
                fieldId === 'target_path' ? 'Select Target Path' :
                    fieldId === 'media_path_in_jellyfin' ? 'Select Media Path (Jellyfin side)' :
                        'Select Media Path (this machine)';
            document.getElementById('path-picker-modal').style.display = 'flex';
            await browseDir(currentVal || '');
        }

        async function browseDir(path) {
            document.getElementById('picker-body').innerHTML =
                '<p style="padding:1.5rem; text-align:center; color:var(--text-secondary);">Loading…</p>';
            let result;
            try {
                const resp = await fetch('/api/browse?path=' + encodeURIComponent(path));
                result = await resp.json();
            } catch (e) {
                document.getElementById('picker-body').innerHTML =
                    `<p class="picker-empty">Could not load directory: ${e.message}</p>`;
                return;
            }
            if (result.status !== 'success') {
                document.getElementById('picker-body').innerHTML =
                    `<p class="picker-empty">${result.message}</p>`;
                return;
            }
            _pickerCurrentPath = result.current;
            document.getElementById('picker-breadcrumb').textContent = result.current;
            document.getElementById('picker-footer-path').textContent = result.current;

            const body = document.getElementById('picker-body');
            body.innerHTML = '';

            if (result.parent) {
                const up = document.createElement('button');
                up.className = 'picker-item picker-up';
                up.innerHTML = '<span class="picker-item-icon">⬆️</span> .. (go up)';
                up.onclick = () => browseDir(result.parent);
                body.appendChild(up);
            }

            if (result.dirs.length === 0) {
                const empty = document.createElement('p');
                empty.className = 'picker-empty';
                empty.textContent = 'No subdirectories here.';
                body.appendChild(empty);
            } else {
                result.dirs.forEach(name => {
                    const btn = document.createElement('button');
                    btn.className = 'picker-item';
                    const fullPath = result.current.replace(/\/$/, '') + '/' + name;
                    const icon = document.createElement('span');
                    icon.className = 'picker-item-icon';
                    icon.textContent = '📁';
                    btn.appendChild(icon);
                    btn.appendChild(document.createTextNode(' ' + name));
                    btn.title = fullPath;
                    btn.onclick = () => browseDir(fullPath);
                    body.appendChild(btn);
                });
            }
        }

        function confirmPicker() {
            if (_pickerTargetId && _pickerCurrentPath) {
                document.getElementById(_pickerTargetId).value = _pickerCurrentPath;
            }
            closePicker();
        }

        function closePicker() {
            document.getElementById('path-picker-modal').style.display = 'none';
            _pickerTargetId = null;
        }

        function pickerOutsideClick(e) {
            if (e.target === document.getElementById('path-picker-modal')) closePicker();
        }

        async function syncAll() {
            const syncBtn = document.getElementById('sync-btn');
            syncBtn.classList.add('btn-loading');
            try {
                const response = await fetch('/api/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const result = await response.json();
                if (result.status === 'success') {
                    let totalLinks = result.results.reduce((acc, r) => acc + r.links, 0);
                    showStatus(`Sync complete! Created ${totalLinks} symbolic links.`, 'success');
                } else {
                    showStatus(result.message || 'Sync failed', 'error');
                }
            } catch (err) {
                showStatus('Sync failed - API unreachable', 'error');
            } finally {
                syncBtn.classList.remove('btn-loading');
            }
        }

        // Initialize
        if (window.location.protocol === 'file:') {
            document.getElementById('connection-warning').style.display = 'block';
        } else {
            loadConfig();
        }
    