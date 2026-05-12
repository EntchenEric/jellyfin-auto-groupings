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

export const metadataTypes = ['genre', 'actor', 'studio', 'tag', 'complex'];

export const sortLabels = {
    'imdb_list_order': 'IMDb List Order',
    'trakt_list_order': 'Trakt List Order',
    'tmdb_list_order': 'TMDb List Order',
    'anilist_list_order': 'AniList List Order',
    'mal_list_order': 'MAL List Order',
    'letterboxd_list_order': 'Letterboxd List Order',
    'CommunityRating': 'Community Rating',
    'ProductionYear': 'Production Year',
    'SortName': 'Name (A→Z)',
    'DateCreated': 'Date Added',
    'Random': 'Random',
};
