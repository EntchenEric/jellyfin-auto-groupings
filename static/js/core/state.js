// state.js – Central state management for the entire application

export const state = {
    currentConfig: { groups: [], scheduler: {} },
    pendingImportData: null,
    editingIndex: -1,
    isServerValidated: false,
    cachedMetadata: {},
    lastRenderedType: null,
};

// Window-level metadata rules (used by renderMetadataRules for real-time editing)
window._currentMetadataRules = [{ operator: '', value: '' }];

export function setState(key, value) {
    state[key] = value;
}

export const sourceOptions = {
    jellyfin: [
        { value: 'general', label: 'General (Title, Date, Rating...)' },
        { value: 'genre', label: 'Genre' },
        { value: 'actor', label: 'Actor' },
        { value: 'studio', label: 'Studio' },
        { value: 'tag', label: 'Jellyfin Tag' },
        { value: 'year', label: 'Release Year' },
        { value: 'complex', label: 'Complex Rule-set (Mixed)' },
        { value: 'recommendations', label: 'User Recommendations', requiredKey: 'tmdb_api_key' }
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

export const metadataTypes = ['genre', 'actor', 'studio', 'tag', 'year', 'complex'];

/** Category keys the source picker understands. */
export const sourceCategories = Object.keys(sourceOptions);

/**
 * Coerce a stored or selected source category to a key of `sourceOptions`.
 *
 * `config.json` is user-editable and an import can come from an older build,
 * so a group can carry a category this frontend does not know — a capitalised
 * `"External"`, a trailing space, a number, or a value from a future release.
 * Assigning such a value to the `<select>` leaves the element on no option at
 * all, and `sourceOptions[category]` is then `undefined`: `.forEach` threw from
 * `updateSourceTypeOptions()`, which aborted `loadConfig()` (the dashboard
 * reported "Failed to load configuration" and rendered no groups) and made
 * every group's Edit button die on the same call.
 *
 * The group's own `source_type` is the reliable hint for the intent: a
 * `tmdb_list` only exists in the External list, so a broken category next to
 * it means External, not Jellyfin.
 *
 * @param {unknown} category Category value from config or the select.
 * @param {unknown} [sourceType] The group's source type, used to infer.
 * @returns {string} A key of `sourceOptions`; `'jellyfin'` when nothing fits.
 */
export function resolveSourceCategory(category, sourceType = '') {
    if (typeof category === 'string' && Object.hasOwn(sourceOptions, category)) {
        return category;
    }
    const wanted = typeof sourceType === 'string' ? sourceType.trim().toLowerCase() : '';
    if (wanted) {
        for (const key of sourceCategories) {
            if (sourceOptions[key].some(opt => opt.value === wanted)) return key;
        }
    }
    return 'jellyfin';
}

export const sortLabels = {
    'imdb_list_order': 'IMDb List Order',
    'trakt_list_order': 'Trakt List Order',
    'tmdb_list_order': 'TMDb List Order',
    'anilist_list_order': 'AniList List Order',
    'mal_list_order': 'MAL List Order',
    'letterboxd_list_order': 'Letterboxd List Order',
    'recommendations_list_order': 'Recommendations Order',
    'CommunityRating': 'Community Rating',
    'ProductionYear': 'Production Year',
    'ProductionYearAsc': 'Production Year (oldest first)',
    'SortName': 'Name (A→Z)',
    'DateCreated': 'Date Added',
    'Random': 'Random',
};
