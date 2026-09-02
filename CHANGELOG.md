# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `sync.py`: out-of-season cleanup for a seasonal group now targets the
  **normalised** group directory, matching how `_process_group` creates it.
  A group name may carry surrounding whitespace or redundant slashes (e.g.
  `" Anime / Action "`); previously the cleanup derived the path from the
  raw name, so it deleted a non-existent directory and left the real
  (normalised) group directory behind when the group went out of season.

### Changed

- `tmdb.py`: `get_tmdb_recommendations` now retries a rate-limited item
  instead of silently dropping it. A `429` response means "slow down and
  retry", not "skip this item", so a rate-limited item's recommendations
  were previously lost. The function now sleeps on the `429` (honouring
  `Retry-After` when present) and retries the same item, up to
  `_MAX_RECOMMENDATION_RETRIES` (3) attempts, before giving up. Other
  non-`200` statuses and request/parse errors still skip the item as before.

- `tests/test_tmdb.py`: updated the three `429` rate-limit tests to assert
  the item is retried (and its recommendations preserved) rather than
  dropped, and added coverage for retry exhaustion, a non-`200`/non-`429`
  status skip, and the empty-items short-circuit in `fetch_tmdb_list`.
  `tmdb.py` is back to 100% coverage.

- `app.py`: unknown `/api/*` routes now return a JSON `404` body
  (`{"status": "error", "message": "Not found"}`) instead of Flask's
  default HTML 404 page. The frontend API client expects every `/api/*`
  response to be JSON, so a mistyped or removed endpoint previously broke
  that contract and surfaced as a generic "Request failed" toast. Non-API
  paths keep the standard HTML 404 page.

- `tests/frontend/api.test.js`: added a test asserting that no
  `Authorization` header is sent when no app password is stored, closing the
  falsy-password edge case in `authHeaders`. The frontend suite is now 394
  tests (100% statement/function/line coverage, 99.87% branch coverage).

- `tests/test_routes.py`: added tests verifying that unknown `/api/*` routes
  return a JSON 404 while unknown non-API routes keep the HTML 404 page.

- `tests/frontend/api.test.js`: added a test covering the 401 password-prompt
  edge case where the user submits an empty string (rather than cancelling
  with `null`). An empty password is treated like a cancelled prompt: no
  retry, no stored password, and a `401` `ApiError` is raised. This closes
  the last remaining branch-coverage gap in `api.js`.

- `README.md`: updated the frontend test count from 392 to 393.

- `sync.py`: `_coerce_year_int` now guards against non-finite float year
  values (`inf`/`nan`) from a malformed or corrupt API response. Previously
  `int(float('inf'))` raised `OverflowError` and `int(float('nan'))` raised
  `ValueError`, which could propagate out of `_match_year` and crash a sync
  instead of simply not matching the rule. Non-finite floats now return
  `None` (no match), mirroring the existing handling for non-finite strings.

- `tests/test_sync.py`: added coverage for non-finite float year values in
  `_coerce_year_int` and `_match_year`.

- `routes.py`: `_search_local_filesystem` now measures the
  `_AUTO_DETECT_MAX_DEPTH` traversal cap relative to each search root instead
  of the filesystem root. Previously the effective depth limit varied with
  where the search root lived (e.g. `/media` vs `/home/user`), so the same
  directory tree could be pruned at different depths depending on the root.
  The cap is now consistent regardless of the root's own depth.

- `tests/test_routes.py`: added a test verifying the auto-detect depth limit
  is measured relative to the search root (a file beyond the cap is not found,
  a file within it is).

- `README.md`: updated the backend test count from 884 to 885.

- `sync.py`: `_match_year` now parses range-comparison limits (e.g.
  `>2001.0`, `>=2001.0`) with `_parse_year_int`, so float-formatted limits
  are tolerated just like float-formatted plain expressions and values.
  Previously a bare `int()` rejected these and silently returned no matches.
  Unparseable limits (e.g. `>nonsense`, `>inf`) are still rejected.

- `tests/test_sync.py`: added tests covering float-formatted range limits in
  `_match_year` (all four comparison operators) and rejection of unparseable
  range limits.

- `README.md`: documented the frontend test count (392 tests, 100%
  statement/function/line coverage) in the Frontend Tests section, matching
  the style used for the backend test count.

- `README.md`: corrected the backend test count in the Testing section from
  876 to 884 to match the current suite.

- `scheduler.py`: the background cleanup job handler (`_run_cleanup_job`)
  now catches unexpected exceptions (e.g. a `KeyError` from a malformed
  config, or an `OSError` from a filesystem issue) and logs them instead of
  silently killing the background job. This mirrors the resilience already
  added to the global and per-group sync job handlers.

- `tests/test_scheduler.py`: added tests verifying that the cleanup job
  handler catches and logs both expected (`OSError`) and unexpected
  (`KeyError`) exceptions without raising.

- `sync.py`: the symlink-filename collision disambiguation in
  `_create_group_symlinks` now also avoids colliding with anything already
  present on disk in the group directory (e.g. a leftover from a partial or
  aborted run, a manually-placed file, a directory, or a nested group's own
  symlink). Previously a generated ``(2)``/``(3)`` suffix could collide with
  an existing entry, making ``symlink_to()`` raise ``FileExistsError`` and
  silently drop the link. Every existing entry name (files, directories, and
  dangling symlinks alike) is reserved in non-dry-run mode, so previews are
  unaffected.

- `tests/test_sync.py`: added tests verifying that a pre-existing on-disk
  file, directory, or dangling symlink with a colliding name is skipped (the
  new link gets a higher suffix and the existing entry is left untouched),
  and that dry-run previews do not seed from disk.

- `tests/frontend/wizard.test.js`: added tests covering the `oninput` handlers
  on the wizard's Jellyfin URL and API key inputs — editing either field resets
  the internal `isWizardServerConnected` flag and re-renders the UI, disabling
  the Continue button on step 2 until the connection is re-tested.

- `tests/frontend/metadata.test.js`: added tests covering the rule-row
  `onchange` handlers (`opSelect`, `rowTypeSelect`, `valSelect`), the
  recommendations user-select `onchange` handler (writes the selected user id
  into the source value input), and the `source_type` `onchange` handler wired
  up in `initMetadata`.

- `tests/frontend/groupings.test.js`: added a test verifying the rendered
  Edit button is wired to `editGroup` (populates the form and switches to edit
  mode).

- `tests/frontend/path-picker.test.js`: added tests covering the directory-item
  and go-up button click handlers in the path picker, verifying they browse
  into the child and parent directories respectively.

- `tests/frontend/api.test.js`: added a test verifying the abort timer is
  cleared in the `finally` block even when the request throws (error path).

  These additions raise overall frontend function coverage to 100% (previously
  94%) and statement/line coverage to 100%.

- `scheduler.py`: broadened the exception handling in the background sync job
  handlers (`_run_global_sync_job` and `_run_group_sync_job`) from
  `(ValueError, OSError, RuntimeError)` to `Exception`, so an unexpected error
  (e.g. a `KeyError` from a malformed config, or a `requests` exception from a
  fetcher) is always caught and logged instead of silently killing the
  background job.

- `tests/test_scheduler.py`: added tests verifying that unexpected exceptions
  (e.g. `KeyError`) are caught and logged by both background sync job handlers.

- `tests/frontend/groupings.test.js`, `tests/frontend/metadata.test.js`,
  `tests/frontend/export-import.test.js`, `tests/frontend/wizard.test.js`,
  `tests/frontend/cover-generator.test.js`, `tests/frontend/path-picker.test.js`
  and `tests/frontend/api.test.js`: added tests covering previously uncovered
  branches — fallbacks for missing/empty group names and source values in
  `groupings.js`, the declined-confirmation path in `clearAllGroups`, the
  whitespace-only required-key and missing-rule-type fallbacks in
  `metadata.js`, raw-array and nameless-group imports in `export-import.js`,
  the missing host-path focus branch and default detection-failure message in
  `wizard.js`, the `devicePixelRatio` fallback in `cover-generator.js`, the
  default auto-detection-failure message in `path-picker.js`, and the
  `finally`-block timer cleanup on the success path in `api.js`. This raises
  overall frontend branch coverage to 99.87%.

- `static/js/features/metadata.js`: removed a redundant `|| 'genre'` fallback
  in `renderMetadataRules` — `rule.type` is always set to a truthy value for
  complex rules before the `rowType` expression is evaluated, so the fallback
  was unreachable dead code.

- `tests/frontend/wizard.test.js`, `tests/frontend/metadata.test.js` and
  `tests/frontend/export-import.test.js`: added tests covering previously
  uncovered branches — the wizard's Continue button enabled state on step 2
  when the server is connected, pre-filling the manual input for a metadata
  type when the server is not validated and a `preValue` is supplied, and
  treating a partial config (e.g. `jellyfin_url` without `api_key`) as a
  groups-only import. This raises overall frontend branch coverage to 97.65%.

- `tests/frontend/ui.test.js`: added tests covering the remaining uncovered
  branches in `static/js/core/ui.js` — Tab/Shift+Tab focus-trap wrap-around
  (from the last element, and when focus is outside the modal), the
  `previousActive` fallback in `showModal` when the active element has no id
  or is the body, and focus restoration when the trigger element is missing
  or present on Escape/close-button dismissal. This raises `ui.js` branch
  coverage to 100%.

- `static/js/features/cleanup.js`: the cleanup modal now routes its HTTP
  requests through the centralized `api.js` helpers (`getCleanupItems` /
  `performCleanup`) instead of calling `fetch` directly. This gives cleanup
  the same auth headers, request timeout, and 401 retry handling as the rest
  of the app, and removes the previously-unused `getCleanupItems` /
  `performCleanup` wrappers from dead-code status. Frontend tests were
  updated to mock the api module directly.

- `README.md`: updated the backend test count from 885 to 891 to match the
  current suite (the seasonal-cleanup regression test added six tests).

### Fixed

- `routes.py`: `_delete_folder` now explicitly rejects symlinks before
  calling `shutil.rmtree`. `Path.is_dir()` follows symlinks, so a symlink
  pointing at a directory previously passed the existence check and then hit
  `shutil.rmtree`'s confusing "Cannot call rmtree on a symbolic link" error.
  The new guard returns a clear "Refusing to delete symlink" message and
  leaves the symlink and its target untouched, matching the cleanup GET
  endpoint which already excludes symlinks. Added a regression test covering
  the symlink branch.

- `static/js/features/path-picker.js`: `browseDir` now handles explicit
  non-2xx HTTP responses (e.g. a 500 with an HTML error body) by showing a
  readable "Could not load directory (HTTP <status>)" message in the picker
  instead of letting `resp.json()` throw a confusing JSON parse error. Added
  a frontend test covering the non-OK response edge case.

- `static/js/features/cover-generator.js`: `renderCover` now reads the cover
  form fields via optional chaining with sensible defaults, so it no longer
  throws if any of the form elements are missing from the DOM. This makes
  `renderCover` consistent with the null-safe reads already used in
  `applyCover`. Added frontend tests covering the missing-form-element,
  missing-group, missing-data-URL, invalid-hex-color, and fonts-unavailable
  (setTimeout) edge cases, raising the module's branch coverage to ~99%.

- `sync.py`: `_parse_year_int` now tolerates float-formatted year expressions
  (e.g. `"2001.0"`), mirroring how `_coerce_year_int` already normalises
  float-formatted *values*. A plain year rule such as `"2001.0"` now matches
  the integer year `2001` (and vice-versa), making the plain comparison path
  symmetric with the range-comparison path. Previously `_match_year(2001,
  "2001.0")` returned `False` even though the value and expression represent
  the same year. Added `test_parse_year_int` and extended
  `test_match_year_ranges` to cover float-formatted expressions.

- `sync.py`: `_parse_year_int` and `_coerce_year_int` now also catch
  `OverflowError` when converting float-formatted year expressions/values, so
  non-finite or oversized inputs (e.g. `"inf"`, `"1e309"`) are rejected
  cleanly instead of aborting year matching. Added regression coverage for
  these inputs.

- `static/js/features/sidebar-resizer.js`: the saved sidebar width restored
  from `localStorage` is now clamped to the valid 200–800px range and validated
  as a finite number. A stale or corrupt value (e.g. from an older version, an
  out-of-range width, or a non-numeric string) can no longer break the layout;
  it falls back to the CSS default. Added frontend tests covering below-min,
  above-max, and non-numeric saved widths.

- `app.py`: `_resolve_log_level` now validates the `LOG_LEVEL` value against the
  explicit set of logging level constants (`DEBUG`, `INFO`, `WARNING`, `ERROR`,
  `CRITICAL`) instead of accepting any integer attribute on the `logging`
  module. An unrecognised value can no longer silently resolve to an unrelated
  integer constant; it now falls back to `INFO` as documented.

- `perform_cleanup` no longer rejects nested group names (e.g. `"Anime/Action"`)
  via the now-removed `_is_valid_folder_name` check. The cleanup UI lists nested
  groups by their full relative path, but the API previously rejected any name
  containing a `/`, so nested groups could never be deleted through the API.
  Validation now relies solely on `normalize_group_relpath` inside
  `_delete_folder`, which supports nested paths while still rejecting path
  traversal. Removed the resulting dead `_is_valid_folder_name` helper and added
  a regression test.

- `static/js/features/export-import.js`: `downloadJSON` now revokes the blob
  URL asynchronously via `setTimeout(0)` instead of synchronously right after
  `a.click()`. In some browsers (notably Firefox and Safari) a synchronous
  revoke can abort the download before the browser has started fetching the
  blob URL, resulting in a failed or empty export. The two `execExport`
  frontend tests were updated to await the deferred revoke.

### Added

- `SECURITY.md`: document the security hardening headers applied to every
  HTTP response (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `X-XSS-Protection`, and `Permissions-Policy`), including
  their purpose and where they are set in `routes.py`.

- `tests/test_network.py`: add coverage for the `NETWORK_RETRY_STATUS_FORCELIST`
  edge cases in `_parse_retry_config` — an empty or whitespace-only value yields
  an empty status list (no status-code retries), and empty entries between
  commas (e.g. `"429, ,500"`) are tolerated and skipped. This documents the
  intended behaviour of the retry configuration parser.

- `routes.py`: the `_add_security_headers` after-request hook now also sets
  `Referrer-Policy: no-referrer` (prevents leaking the current URL, which may
  contain query parameters, in the `Referer` header of outbound requests) and
  `X-XSS-Protection: 1; mode=block` (legacy XSS filter for older browsers).
  Added `tests/test_routes.py` coverage asserting both the HTML index and API
  responses carry all four security hardening headers.

- `routes.py`: the `_add_security_headers` after-request hook now also sets a
  `Permissions-Policy` header that disables browser features this app does not
  use (`camera`, `microphone`, `geolocation`, `payment`, `usb`, `midi`, etc.)
  while allowing fullscreen for the cover-image viewer. This reduces the
  browser attack surface and prevents silent feature abuse. Extended the
  `tests/test_routes.py` security-header assertions to cover the new header.

- `tests/frontend/cleanup.test.js` and `tests/frontend/sync.test.js`: add edge-case
  coverage for the `cleanup.js` and `sync.js` modules — the fallback error message
  when an API error response has no `message` field, the `partial_success` warning
  toast that lists per-folder errors, and the `initCleanup` / `initSync` no-op
  initialisers being callable without throwing. This raises the full frontend
  suite to 333 tests across 15 files.

- `tests/frontend/path-picker.test.js`: add coverage for the previously-uncovered
  `path-picker.js` branches — the auto-detect success-without-host-path warning,
  the auto-fill of empty path fields from a detected result, the no-op when
  auto-detection returns a non-success status, and the root-directory path-join
  edge case (no double slash when browsing `/`). This raises `path-picker.js`
  statement coverage from ~97% to 100% (branch ~85% to ~98%).

- `tests/frontend/export-import.test.js`: add coverage for the previously-uncovered
  `export-import.js` branches — the non-`SyntaxError` import-processing failure
  path (e.g. when the parsed JSON is `null`) and the `initExportImport` no-op.
  This raises `export-import.js` statement coverage from ~98% to 100% (branch
  ~89% to ~91%) and the full frontend suite to 328 tests across 15 files.

- `tests/frontend/groupings.test.js`: add coverage for the previously-uncovered
  `groupings.js` branches — the external source-category label, the fallback to
  the raw `source_type` when the category is unknown, the fallback to the raw
  `sort_order` when it has no known label, the no-badge rendering when
  sort/seasonal/collection are unset, the delete-button wiring, the missing
  count-badge and search-input no-op paths, the hidden optional panels when a
  group has no sort/schedule/seasonal, the skip-disk-cleanup path when a group
  has no name, the disk-cleanup failure toasts for both delete and clear-all,
  the append-vs-splice re-insert path when the array shrinks during a save
  failure, and the missing-scheduler / missing-`global_exclude_ids`
  initialisation plus the unnamed-group skip in the exclusions UI. This raises
  `groupings.js` statement coverage from ~97% to 100% (branch ~78% to ~93%)
  and the full frontend suite to 322 tests across 15 files.

- `tests/frontend/ui.test.js`: add coverage for the remaining uncovered
  `ui.js` modal focus-trap and progress-bar edge cases — excluding focusables
  nested inside a hidden ancestor from the trap, preventing Tab (and keeping
  focus on the modal) when a modal has no focusable elements, closing a modal
  via Escape or its close button when no trigger element exists, and guarding
  `_updateProgressBar` when the overlay exists but its progress children are
  missing. This raises `ui.js` branch coverage from ~92% to ~95% (statement
  coverage stays at 100%) and the full frontend suite to 306 tests across 15
  files.

- `tests/frontend/metadata.test.js`: add coverage for the remaining uncovered
  `metadata.js` statements — the `updateSourceValueUI` preValue parsing path
  (parsing a filter string into rules for a validated metadata type) and the
  `initMetadata` event-handler wiring (source-category change, add-rule click,
  and the `window` exports). This raises `metadata.js` statement coverage from
  ~97% to 100% and the full frontend suite to 301 tests across 15 files.

- `tests/frontend/config.test.js`: add coverage for the previously-uncovered
  `config.js` branches — the main-form reconnect flow (loading overlay,
  `refreshMetadata` success and failure paths), the env-override banner
  `sidebar.prepend` fallback when the connection-warning element is missing,
  the `people`→`actor` source-type migration when `source_category` is already
  set, the `saveAllConfig` failure path, missing-scheduler creation, invalid
  cleanup-schedule rejection, and the empty-credentials load path. This raises
  `config.js` statement coverage from ~90% to 100% (branch ~88% to 100%) and
  the full frontend suite to 294 tests across 15 files.

- `tests/frontend/ui.test.js`: add coverage for the previously-uncovered
  `ui.js` modal event handlers and progress-bar ETA logic — `hideModal`
  focus restoration and `modal-open` body-class management (including the
  keep-class-when-another-modal-visible case), the Escape-key and backdrop
  click handlers, and the `_updateProgressBar` ETA display (show when
  remaining > 2s, hide when small or on the final step). This raises
  `ui.js` statement coverage from ~90% to 100% and the full frontend suite
  to 281 tests across 15 files.

- `tests/frontend/metadata.test.js`: add unit tests for the `metadata.js`
  feature module (`parseMetadataValue`, `getFilterValue`,
  `updateSourceTypeOptions`, `renderMetadataRules`, `addMetadataRule`,
  `updateSourceValueUI`, `refreshMetadata` and `previewGrouping`), raising
  its statement coverage from ~4% to ~95% and overall frontend coverage from
  ~43% to ~54%.

- `tests/frontend/test-connection.test.js`: add coverage for
  `testConnectionFromSidebar` (success, API error and network-failure paths),
  bringing the `test-connection.js` feature module to 100% statement coverage.

- `tests/frontend/sync.test.js`, `tests/frontend/cleanup.test.js`,
  `tests/frontend/export-import.test.js` and `tests/frontend/wizard.test.js`:
  add unit tests for the previously-untested frontend feature modules. This
  raises overall frontend statement coverage from ~23% to ~42% (cleanup,
  sync and export-import each go from 0% to 80%+).

- `tests/frontend/state-advanced.test.js`: add a regression-guard test that
  verifies every sort option in the `sort_order` dropdown template has a
  corresponding entry in the frontend `sortLabels` map, so a missing label
  (like the `ProductionYearAsc` one fixed below) is caught by the test suite.

- `tests/frontend/path-picker.test.js`: add unit tests for the `path-picker.js`
  feature module (opening the picker per target field, browsing directories
  including empty/error/loading states, confirming and closing, backdrop
  dismissal, host-path auto-detection and `autoDetectIfEmpty`), raising its
  statement coverage from 0% to ~97% and the full frontend suite to 168 tests
  across 12 files.

- `tests/frontend/config.test.js`: add unit tests for the `config.js` feature
  module (`loadConfig` incl. legacy data migration, `saveAllConfig` incl.
  client-side cron validation, `performSilentTest`, `syncDomToState`, the
  scheduler toggles and `initConfig`), raising its statement coverage from
  ~10% to ~74% and the full frontend suite to 186 tests across 13 files.

- `tests/frontend/groupings.test.js`: add unit tests for the `groupings.js`
  feature module (`renderGroups` incl. empty state, badges, search filter and
  cover-button wiring, `editGroup`, `cancelEdit`/`resetFormUI`, `deleteGroup`
  incl. invalid-index and save-failure rollback, `clearAllGroups`, the
  scheduler/seasonal/sort toggles, `populateSeasonalDays` and
  `updateGlobalSyncExclusionsUI` incl. stale-exclusion pruning), raising its
  statement coverage from 0% to ~97% and the full frontend suite to 211 tests
  across 14 files.

- `tests/frontend/cover-generator.test.js`: add unit tests for the
  `cover-generator.js` feature module (`openCoverGenerator` incl. field
  population, defaults and modal display, `renderCover` canvas drawing,
  `downloadCover` incl. inactive guard and download trigger, `applyCover`
  incl. upload/save flow, group update and error handling, and
  `initCoverGenerator`), raising the full frontend suite to 223 tests across
  15 files.

- `tests/frontend/cover-generator.test.js`: extend the cover-generator suite
  to cover the canvas rendering internals — every theme background and text
  branch, all eight border styles (incl. the dashed `industrial-dash` and
  corner-ornament `ornate` paths), the `wrapText` line-wrapping and
  character-splitting edge cases, and the post-render canvas-state reset.
  This raises `cover-generator.js` statement coverage from ~42% to 100%
  and overall frontend coverage from ~81% to ~92% (240 tests across 15
  files).

- Groups can be restricted to movies or series via a new `item_type` setting
  ("Media Type Filter" in the UI). Jellyfin often files the same genre under
  different names per media type (`Action` for movies, `Action & Adventure`
  for series) while sharing others (`Drama`), so filtering by genre alone
  could neither reliably separate nor combine them. Metadata groups filter
  server-side via `IncludeItemTypes`; complex and list-backed groups filter
  the resolved items.

- `jellyfin.py`: new `ProductionYearAsc` sort order (oldest first). The existing
  `ProductionYear` order is newest-first, which is the wrong way round for
  watching a franchise from the start — a "Marvel Studios" group now sorts into
  release order and gets numbered symlink prefixes accordingly.

- Nested groups: a group name may now contain `/` to create a folder tree
  (`Anime/Action` → `<target>/Anime/Action`). Point one Jellyfin library at the
  tree root and browse it as folders — useful on TV clients, where navigating
  folders is far easier than using filters.
- `_common.py`: `normalize_group_relpath()` normalises a group name into a safe
  relative path (trims segments, collapses empty ones, accepts `\` as a
  separator) and rejects `.`/`..` segments and NUL bytes.

- `routes.py`: add `/api/version` endpoint returning the current application
  version string.
- `routes.py`: include `version` field in `/api/health` response.
- `tmdb.py`: handle HTTP 429 (rate limit) in `get_tmdb_recommendations` by
  respecting the `Retry-After` header and backing off.

- `tests/frontend/api.test.js`: expand coverage of the centralised API client
  (`api.js`) to 100% statement / 100% function coverage. Adds tests for the
  401 auth-retry flow (with and without a stored password), request timeout
  (`AbortError`), network errors (`TypeError`), unexpected errors, non-JSON
  error bodies, `browsePath` query-string building, and all convenience
  wrappers.

- `tests/frontend/wizard.test.js`: add coverage for `finishWizard` (field
  validation and focus behaviour, successful save + reload, and save-failure
  handling) and `initWizard` (button wiring and setup-done gating), raising
  `wizard.js` statement coverage from ~72% to 100%.

- `tests/frontend/config.test.js`: add coverage for the environment-override
  warning banner rendered by `loadConfig` (known label mapping, unknown-key
  fallback, and the no-overrides case) and the API config form submit handler,
  raising `config.js` statement coverage from ~74% to ~90%.

- `tests/frontend/export-import.test.js`: add coverage for selective export,
  full-config import (Overwrite All), group import (append selected), the
  file-reader error path, and the incompatible-file-structure path, raising
  `export-import.js` statement coverage from ~83% to ~98%.

### Changed

- `routes.py`: validate that a group's `source_type` is one of the recognised
  source types and that `sort_order` is a recognised Jellyfin sort key or
  external-list order at config-save time. Previously an invalid value passed
  config validation and only surfaced later as an "Unknown source type" error
  during a sync (or was silently ignored for sorting).
- `static/js/core/ui.js`: add a keyboard focus trap for modals. When a modal
  is open, Tab/Shift+Tab now cycle focus within the topmost visible modal
  instead of letting keyboard users tab out into the background page
  (WCAG 2.1.2 / 2.4.3). The topmost modal is derived from the DOM, so the
  trap stays correct even when modals are hidden through other means.
- `tests/frontend/ui.test.js`: add unit tests covering the modal focus trap
  (Tab wrap, Shift+Tab wrap, no-trap-when-closed, and topmost-modal
  selection when several modals are open).
- `README.md`: update test count from 855 to 856 (a cleanup test was added in
  the symlink-exclusion fix).
- `README.md`: update test count from 749 to 855 and document the `/api/version`
  endpoint in the Diagnostics table.
- `docs/API.md`: document the `/api/version` endpoint (returns the current
  application version string).
- `docs/API.md`: document the `version` field returned by the `/api/health`
  endpoint (it was present in the response but missing from the docs table).
- `_common.py`: update `DEFAULT_SCRAPING_HEADERS` User-Agent from Chrome/122 to
  Chrome/131 to reduce the chance of being blocked by scraping targets.

### Fixed

- `sync.py`: `_match_year()` now matches float production years (e.g.
  `2001.0` from some API responses) against plain integer expressions like
  `"2001"`, instead of comparing `"2001.0" == "2001"` and returning `False`.
  Non-numeric values still fall back to string comparison and never match a
  plain numeric expression.

- `sync.py`: `_match_year()` now also handles *string* production years (e.g.
  `"2001.0"` from APIs that serialise the year as a string) in both plain and
  range (`>`, `>=`, `<`, `<=`) comparisons. Previously a string float year
  failed to match a plain integer expression and made every range comparison
  return `False` (e.g. `_match_year("2001.0", ">2000")` was `False`).

- `trakt.py`: `_fetch_trakt_page()` now raises a clear `RuntimeError` when the
  Trakt API returns invalid JSON, and a `TypeError` when it returns a non-list
  response body, instead of letting a raw `ValueError`/`AttributeError`
  propagate. `_extract_imdb_ids_from_page()`
  also tolerates malformed entries (non-dict items, non-dict `media`/`ids`
  objects) by skipping them, so a single bad record can no longer abort the
  whole list fetch. This matches the robustness already present in `mal.py`
  and `tmdb.py`.

- `Dockerfile`: the gunicorn entrypoint now binds to `$FLASK_PORT` (default
  `5000`) instead of a hardcoded port, so the container honors the `FLASK_PORT`
  environment variable (e.g. the E2E compose maps the app to host port `5005`).

- `static/js/core/state.js`: the `sortLabels` map was missing the
  `ProductionYearAsc` entry, so a group sorted oldest-first showed the raw
  value `ProductionYearAsc` in its card badge instead of a friendly label.
  The backend (`jellyfin.py`) and the sort dropdown already supported this
  order; the label map now matches them.
- `routes.py`: the cleanup endpoint (`GET /api/cleanup`) no longer lists
  symlinked directories as deletable items. A symlink may point outside the
  target directory, so offering it as a cleanup candidate could let a user
  delete an unrelated location. This mirrors the browse endpoint, which already
  excluded symlinks.
- `sync.py`: groups with source type `complex` matched the **entire library**
  instead of evaluating their rules. `_resolve_group_source()` only routed a
  group into the rule evaluator when its type was one of the metadata types
  (`genre`, `actor`, …) — `complex` itself was missing from that set, so such
  groups fell through to the metadata fetch, which has no filter for them and
  returned everything. Every `complex` group therefore linked the whole
  library. The preview endpoint was unaffected, which made the two disagree.
  Both paths now share the same condition.
- `sync.py`: `year:` rules now support `<`, `<=`, `>` and `>=` (e.g.
  `year:>2000`), so a group can select a period without listing every year.
  Previously only exact matches worked, and a comparison silently matched
  nothing.
- `sync.py`: syncing a group whose directory also parents nested groups wiped
  those children. With both `Action` and `Action/Filme` configured, preparing
  `<target>/Action` called `rmtree()` on the whole subtree, deleting the child
  group's symlinks — whether they reappeared depended on the order groups
  happened to sync in. The group directory is now cleared entry by entry,
  removing only the group's own symlinks and cover while leaving
  subdirectories to the nested groups that own them.
- `sync.py`: complex queries (`genre:Action OR genre:Adventure`, any rule using
  `AND`/`OR`/`NOT`) failed with a read timeout on non-trivial libraries. The
  full-library fetch always requested Jellyfin's `People` field, which expands
  the entire cast for every item — on a ~4400-title library one 500-item page
  took ~75 s versus ~5 s without it, so the very first page blew past the 30 s
  timeout and *every* complex group errored out. `People` is now requested only
  when a rule actually needs it (i.e. an `actor` rule); the two field variants
  are cached separately so a lean result is never served to an actor query.
- `unraid/jellyfin-groupings.xml`: the config volume mapped the host path onto
  `/app/config.json`, but the app reads `/app/config/config.json`. When the host
  file did not exist yet, Docker created a *directory* at `/app/config.json` and
  the app silently ran unconfigured forever — settings saved in the UI vanished
  without any error. The mapping is now a directory (`/app/config`).
- `unraid/jellyfin-groupings.xml`, `docker-compose.yml`, `README.md`: the media
  root was documented as `/mnt/user:/media` with "Host Root" set to `/media`.
  Since the host-side path is written verbatim into every generated symlink,
  that produces links Jellyfin cannot resolve, and the resulting library appears
  empty. Docs now mount media under the same container path Jellyfin uses.
- `README.md`: document that a folder exposed under a different name in Jellyfin
  (host `tv` served as `/data/tvshows`) needs a second bind mount with that
  exact target — a host symlink does not work, because `_translate_path` calls
  `Path.resolve()` and rewrites the target back to the real folder name.
- `sync.py`: renamed `_get_cover_path` to public `get_cover_path` for
  consistency — the function was already imported and used cross-module.
  (PR #1062)

### Dependencies

- `.github/workflows/*.yml`: bump `actions/cache` pinned SHA to latest v5
  release. (PR #1060)
- `.github/workflows/*.yml`: bump `actions/checkout` pinned SHA to latest v6
  release. (PR #1059)
- `routes.py`: add health check endpoint at `/api/health` for Docker/Kubernetes
  probes, returning service status, config sanity, and uptime. (PR #561)
- `routes.py`: add global error boundary (`unhandledrejection` + `error` events)
  to surface runtime errors as toast notifications. (PR #561)
- `config.py`: add corrupt config file backup to `config.json.corrupt.bak`
  before falling back to defaults. (PR #561)
- `config.py`: add environment flag parser `_env_flag()` for boolean env vars.
  (PR #561)
- `routes.py`: add `ALLOWED_NON_CSRF_ENDPOINTS` env var for CSRF opt-out.
  (PR #561)

### Fixed

- `static/js/app.js`: cache modal NodeList query in `wireKeyboardShortcuts`
  for performance (query once, reuse on every keydown). (PR #568)
- `static/js/core/api.js`: use `URL` constructor instead of string
  concatenation for `browsePath` query parameters. (PR #568)
- `static/js/features/groupings.js`: fix race condition in `deleteGroup` —
  when `saveConfig` fails after splicing a group, re-insertion now uses
  `push` (instead of `splice`) if the original index is out of bounds.
- `static/js/features/groupings.js`: fix `clearAllGroups` error handling —
  groups array is now backed up and restored on save failure. (PR #568)
- `static/js/features/path-picker.js`: use `URL` constructor instead of
  string concatenation for `browseDir` query parameters. (PR #568)
- `static/js/features/path-picker.js`: fix root-path edge case — trailing
  `encodeURIComponent("/")` on the empty-string root path now produces
  a correct `/` prefix. (PR #568)
- `routes.py`: add null byte check (`\x00`) to `_is_valid_folder_name`
  for security hardening. (PR #568)
- `anilist.py`: catch `requests.RequestException` in `fetch_anilist_list()`
  and wrap it in a descriptive `RuntimeError`, matching the pattern used by
  the other fetcher modules for consistent error reporting.
- `start_virtual_jellyfin.py`: add `VIRTUAL_JF_PORT` env var for overriding the
  default mock Jellyfin port 8096. (PR #561)
- `Dockerfile`: update `HEALTHCHECK` to use `/api/health` endpoint instead of
  the homepage root. (PR #561)
- `static/js/app.js`: improve hamburger button with `aria-expanded` and
  `aria-label` toggling for accessibility. (PR #561)
- `static/js/app.js`: improve password toggle buttons with `aria-pressed` and
  dynamic `aria-label` based on the input field name. (PR #561)

### Changed

- `README.md`: update test count from 642+ to exact 749 and improve
  `_validate_group_entry` docstring. (PR #1039)
- `config.py`: localize `Path(CONFIG_DIR)` / `Path(CONFIG_FILE)` to module-
  level variables for cleaner coverage tracking. (PR #568)
- `routes.py`: cache `dir_depth = len(Path(dirpath).parts)` in
  `_search_local_filesystem` to avoid re-resolving `Path.parts` on every
  directory entry. (PR #568)
- `routes.py`: move `_MIME_TO_EXT` from inside `upload_cover()` to module
  level, promoting local `import re as _re` to module-level `import re`
  to eliminate per-invocation import overhead. Flatten nested `if` in
  seasonal-date validation (ruff SIM102). (PR #563)
- `config.py`: improve corrupt config backup with timestamp-based collision
  handling and more descriptive error logging. (PR #563)
- `static/js/app.js`: set initial `aria-expanded` and `aria-controls` on
  hamburger button based on actual DOM state; improve password toggle
  `aria-label` to prefer `aria-label`/`placeholder` attributes and compute
  initial `aria-pressed` from actual input type. (PR #563)

- `routes.py`: health endpoint now reports `uptime_seconds` (computed from
  the application start time) and an ISO 8601 `started_at` timestamp instead
  of a raw `uptime` string. (PR #561)
- `config.py`: use `Path().with_suffix()` for corrupt config file backup
  path construction (instead of string concatenation).
- `Dockerfile`: add `ENV PYTHONUNBUFFERED=1` to final stage for immediate
  container log output. (PR #560)
- `run_tests_to_file.py`: increase subprocess timeout from 120s → 300s,
  enable `--tb=short` for concise tracebacks, and log Python version and
  CWD at report start. (PR #560)
- `variables.css`: add `color-scheme: dark` / `color-scheme: light` declarations
  for proper native form control styling in both themes. (PR #554)
- CSS custom property system for z-index layers (`--z-content`, `--z-toast`,
  `--z-modal`, `--z-loading-overlay`, `--z-wizard`, `--z-skip-link`)
  in `variables.css` to centralise stacking context. All hardcoded z-index
  values across CSS files now reference these variables for maintainability.
- `variables.css`: add `--z-locked-overlay` custom property (value `10`)
  for the lock-section overlay badge. (PR #549)
- `Makefile`: add configurable `PYTEST_ARGS` variable (default `-q`) so
  callers can override pytest verbosity (e.g. `make test PYTEST_ARGS="-v"`)
  without editing the Makefile. (PR #557)
- `Makefile` and `README.md`: apply `PYTEST_ARGS` to `test-all` and
  `test-cov` targets for consistency, add `.env.example` & pre-commit hooks
  to dev setup docs, and document `PYTEST_ARGS` override tip. (PR #558)

### Changed

- `run_tests_to_file.py`: print subprocess exit code after test run completes.
  (PR #554)
- `static/css/components.css`: replace hardcoded `z-index: 10` on
  `.locked-overlay-text` with `var(--z-locked-overlay)`. (PR #549)
- `README.md`: update test count from "650+" to exact "650".
- `static/js/app.js`: keyboard shortcut modal detection now uses
  `getComputedStyle` instead of fragile `[style*=]` CSS attribute selector,
  making it resilient to style-attribute changes.

- `.env.example`: add comment noting `NETWORK_RETRY_TOTAL=0` to disable
  retries entirely. (PR #554)
- `tests/test_routes_uncovered.py`: 12 new direct unit tests for
  `_validate_cron_expressions` covering all valid/invalid cron patterns
  (global schedule, cleanup schedule, group schedule, disabled groups).
  (PR #535)
- `README.md`: update test count from 642+ to 650+. (PR #535)
- `static/js/app.js`: add <kbd>R</kbd> keyboard shortcut to reload the
  groups list without a full page refresh.
- Closed stale PR #545 — already merged into main.

### Fixed

- `network.py`: guard against NaN/Inf `NETWORK_RETRY_BACKOFF_FACTOR` values
  that parses as valid ``float`` but produce unusable retry behaviour.
- `anilist.py`: add missing ``from typing import Any`` import to fix ruff
  F821 undefined-name error.
- `network.py`: fix incorrect ``cast("requests.Session", ...)`` on bound
  method — the ``getattr`` result is a ``Callable``, not a ``Session``, which
  fixes the mypy ``operator`` error. (PR #538)

### Added

- `tests/test_network.py`: add tests for NaN, +Inf, and -Inf backoff factor
  fallback values.
- `static/js/core/state.js`: add ``recommendations_list_order`` display label.
- `templates/partials/main/groupings.html`: add ``recommendations_list_order``
  sort-order dropdown option.
- `routes.py`: add type validation for config fields (`api_key`, `anilist_api_url`,
  `trakt_client_id`, `tmdb_api_key`, `mal_client_id`) and group-level fields
  (`source_type`, `source_value`, `sort_order`, `watch_state`, `schedule`,
  `schedule_enabled`, `seasonal_enabled`, `create_as_collection`, `seasonal_start`,
  `seasonal_end`, `rules`). Validate `jellyfin_url` format (must start with
  `http://` or `https://`). Check file in mount-point directory before pruning
  subdirectories during filesystem search.
- `tests/test_routes_uncovered.py`: 18 new tests covering config type validation
  edge cases (group boolean fields, seasonal date format, rules structure,
  jellyfin_url format).
- `tests/test_routes.py`: 2 new mount-point edge-case tests for
  `_search_local_filesystem` in mount-point directories.
- `.github/CODEOWNERS`: add default code owner (`@entcheneric`).

### Changed

- (empty)

### Added

- `tests/test_sync_uncovered.py`: add `test_build_letterboxd_items_unmatched_id_skipped`
  to cover the `continue` branch when `_match_letterboxd_id` returns `None`.

### Fixed

- `sync.py`: fix `_build_letterboxd_items` docstring — dedup description was
  incorrectly scoped to `letterboxd_list_order` only; dedup applies to all
  sort orders.

### Changed

- `README.md`: update test count from 598+ to 608+.

### Added

- `tmdb.py`: add O(1) dedup set in `fetch_tmdb_list` for defensive duplicate filtering.
- Dockerfile: add `--preload` to gunicorn CMD for memory sharing between workers.
- Dockerfile: increase healthcheck `--start-period` from 10s to 15s for slower gunicorn boot times.
- `anilist.py`: validate user-provided AniList list status against known values; unknown statuses now raise `ValueError` with valid options in the message.
- `routes.py`: add `_ALLOWED_NON_CSRF_REQUESTS` frozenset so endpoints can opt out of the CSRF `X-Requested-With` check (for non-browser clients).
- `tests/test_external.py`: add tests for `_resolve_anilist_status` — valid, invalid, and parametrized invalid values.
- `tests/test_routes.py`: add test confirming CSRF-exempted endpoints can POST without the required header.
- `routes.py`: add `ALLOWED_NON_CSRF_ENDPOINTS` env var support to configure CSRF-exempt endpoints at process start.
- `.env.example`: document the `ALLOWED_NON_CSRF_ENDPOINTS` env var under a new CSRF/Security section.
- `README.md`: document `ALLOWED_NON_CSRF_ENDPOINTS` in env vars table and Docker compose snippet.
- `tests/test_routes.py`: add test verifying env-var parsing populates `_ALLOWED_NON_CSRF_REQUESTS` correctly.
- `.gitignore` now excludes `.ruff_cache/`, `.coverage`, and `htmlcov/`.
- `pyproject.toml` now includes a `[tool.ruff.format]` section with explicit
  quote-style, indent-style, and line-ending settings.

### Changed

- `docker-compose.yml`: sync healthcheck `start_period` from 10s → 15s to match the Dockerfile.
- Dockerfile: remove `requirements-dev.txt` copy from builder stage (unused in production).
- `routes.py`: extract CSRF-mutating method check into `_CSRF_MUTATING_METHODS`
  module-level tuple to avoid re-creating the tuple on every request.
- `routes.py`: use walrus operator in `_ALLOWED_NON_CSRF_REQUESTS` frozenset
  to avoid calling `strip()` twice per env-var element.
- `Makefile`: add `test-to-file` target wrapping `run_tests_to_file.py` for
  developer convenience.
- `pyproject.toml` ruff lint config reverted from `select`/`ignore` back to
  `extend-select`/`extend-ignore`. The change was reverted because `select`
  overrides Ruff's default rule sets (E, F, W, etc.), while `extend-select`
  adds custom rules on top of defaults. `extend-ignore` remains the correct
  key for suppressing rules; `extend-ignore`/`select` were never deprecated.
- `scheduler.py` `validate_cron` docstring: removed skipped doctest examples
  that were never executed.
- `letterboxd.py` `_extract_ids_from_list_page`: removed unnecessary
  `re.DOTALL` flags from single-line regex patterns.
- `ANILIST_API_URL` environment variable example in `docker-compose.yml`.
- Tests for `_fill_defaults` resilience when `scheduler` is `null` or a non-dict
  value in the stored config.
- Documented Makefile targets in README.md (test, lint, typecheck, run, format, etc.)
  for contributor discoverability.
- Initial CHANGELOG.md for project tracking.
- Added `anilist_api_url` to `DEFAULT_CONFIG` to prevent KeyError when config
  is accessed before the key is explicitly set.
- Documented `NETWORK_RETRY_*` environment variables in the README env vars table
  and added them to `.env.example` and `docker-compose.yml` for discoverability.
- Add test coverage for `/api/health` endpoint (configured and unconfigured cases)
  via PR #494.
- Added SVG favicon (`🎬` emoji) to base template for better browser tabs.
- Print-friendly stylesheet with hidden UI chrome, expanded link URLs, and
  readable code blocks when printing docs/setup guides.
- `network.py` now gracefully falls back to default retry settings when
  environment variables contain invalid values (previously raised `ValueError`
  at module import time).
- `sync.py` logs a warning when the config contains no groups to sync.
- `scheduler.py` now logs warnings when a group with `schedule_enabled` is
  missing a name or has a non-string name.
- Path-traversal protection in `routes.py` `_delete_folder`: rejects names
  with path separators and validates the resolved path stays within the
  target base directory.
- `config.py` `_fill_defaults` now recursively populates nested defaults
  (e.g. scheduler sub-keys) instead of only one level deep.
- Added tests for the new code paths:
  - `test_parse_retry_config_module_level_fallback` covers the `ValueError`
    fallback in `network.py` at module import time.
  - `test_delete_folder_invalid_name` covers invalid folder name rejection
    in `_delete_folder`.
  - `test_delete_folder_path_traversal_via_symlink` covers the path-traversal
    detection via symlink resolution.
  - `test_delete_folder_resolve_oserror` covers OSError from `Path.resolve()`.
  - `test_search_filesystem_ismount_oserror` covers OSError from
    `os.path.ismount()` in `_search_local_filesystem`.
- Robust containment check in `routes.py` `_delete_folder` using
  `resolved.relative_to(base_resolved)` instead of substring matching.
- `config.py` `_fill_defaults` now uses `copy.deepcopy` for missing nested
  keys via membership check, eliminating aliasing with `DEFAULT_CONFIG`.
- Scrollbar thumb colors now use `color-mix(in srgb, var(--text-secondary) …%,
  transparent)` instead of hardcoded `rgba(255,255,255,…)` — adapts correctly
  in light theme.
- `#topbar` and `#sidebar::-webkit-scrollbar-thumb` backgrounds use
  `color-mix()` with theme variables for light-mode compatibility.
- Footer color uses `var(--text-secondary)` with `opacity` instead of hardcoded
  `rgba(148, 163, 184, 0.45)`.
- `.pre-commit-config.yaml` splits ruff into `ruff-lint` and `ruff-format`
  hooks to match `make lint` target.
- Removed deprecated `page-break-*` CSS properties (courtesy of CodeRabbit
  review) — using modern `break-*` equivalents only.
- Improved `network.py` error logging to include the actual invalid value when
  `NETWORK_RETRY_TOTAL` or `NETWORK_RETRY_BACKOFF_FACTOR` fails to parse.
- Stricter `_handle_http_error` signature in `routes.py` to accept `HTTPException`
  instead of the generic `Exception`, eliminating a dead re-raise branch.
- Explicit type annotation for `_scheduler` in `scheduler.py`.
- `_prepare_group_directory` now resolves the cover path even during dry runs,
  so callers can access `source_cover` for preview purposes regardless of mode.
- Merged PR #496: Add Makefile for common dev commands; address CodeRabbit review
  comments.
- Fixed `.PHONY` declaration in Makefile to match actual targets (removed `dev`/`docs`,
  added `docker-build`/`docker-run`).
- Simplified `_parse_mmdd` in sync.py by removing redundant `day <= 0` check
  (already covered by `calendar.monthrange` validation).
- Standardised README example commands to use `python3` for consistency with
  system defaults.
- Healthcheck in `docker-compose.yml` uses `python3` for consistency.
- Updated README Docker environment example to include `NETWORK_RETRY_*` vars.
- Fixed output path in `run_tests_to_file.py` to use absolute repo-root path.
- Added PUT and PATCH method support to `_request_or_raise` in jellyfin.py
  (future-proofing — network.py already provides retry-aware helpers for these).
- Achieved 100% code coverage across all 12 source modules (1881/1881 lines).
- Moved `_SOURCE_DISPATCH` routing from a module-level dict of lambdas to a
  `match/case`-based `_dispatch_list_source` function, removing the unused
  dispatch table.
- Renamed `_LIST_SOURCES` to `_LIST_SOURCE_TYPES` and added
  `_COMPLEX_QUERY_SOURCE_TYPES` for more descriptive naming.
- Removed redundant cache clear at end of `run_sync` (the cache is already
  cleared at the start of each sync run).
- Mypy type fixes in `tests/virtual_jellyfin.py` dashboard helper.
- Fixed CONTRIBUTING.md to remove `-n auto` flag from the recommended test
  command, since `pytest-xdist` is not included in dev dependencies.
- Removed unnecessary single quotes from font-family declarations in CSS
  (Inter, Outfit, JetBrains Mono) for valid CSS identifier syntax.
- Fixed `currentcolor` typo → `currentColor` in `responsive.css` high-contrast
  media query for standards compliance.
- `letterboxd.py` `_extract_ids_from_list_page`: DRY three similar regex loops
  into a single `_ID_LIST_PAGE_PATTERNS` list with documented priority ordering.
- `config.py` `_fill_defaults`: replace `elif not isinstance(current, dict)` with
  plain `else` (the missing-key case is already handled by the prior membership
  check).
- `scheduler.py` `validate_cron`: call `expr.strip()` once instead of twice.

### Fixed

- Fixed `_search_local_filesystem` returning `None` on timeout/file-limit
  instead of continuing to the next search root (prevents unbounded filesystem
  scanning after the limit is reached).
- Fixed `_build_letterboxd_items` deduplication: both branches (priority and
  list-order) now use a shared `seen_jf_ids` set to prevent duplicate symlinks
  when a Letterboxd entry matches both IMDb and TMDb provider IDs.
- Fixed `_fill_defaults` in `config.py` to use `copy.deepcopy` for nested
  default dicts instead of `dict.copy()`, preventing shallow-copy issues
  and aliasing with `DEFAULT_CONFIG`.
- Fixed order-dependent `test_clear_library_cache` test in `test_sync_more_edges.py`
  by clearing the module-level cache before populating it.
- Improved CSRF testing check in `routes.py` to use the standard Flask
  `current_app.config.get("TESTING")` pattern instead of `current_app.testing`.
- Better type handling for seasonal start/end strings in `_is_in_season` when
  passed non-string types (already handled gracefully as a fallback).
- Fixed double-checked locking pattern in `_fetch_full_library()` so the cache
  is not overwritten if another thread populated it during the fetch.

## [1.0.0] - 2025-03-01

### Added

- Initial release of Jellyfin Groupings.
- Metadata-based groups (genre, actor, studio, tag, year).
- External list support (IMDb, Trakt, TMDb, Letterboxd, AniList, MyAnimeList).
- Complex query logic with AND, OR, and NOT operators.
- Smart sorting with numeric prefixes.
- Docker-first deployment.
- Auto-detect path mapping.
- Scheduler for automatic syncing and cleanup.
- Seasonal group support.
- Collection (Boxset) mode.
- 550+ tests with 100% coverage.
- REST API for programmatic use.
- Unraid Community Applications support.
