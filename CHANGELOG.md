# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- The sidebar **Test** and **Auto-Detect** buttons did nothing at all. Both
  were left without a handler when the frontend was modularised: the inline
  `onclick` attributes went away with the monolithic script, and
  `testConnectionFromSidebar()` (`features/test-connection.js`) and
  `autoDetectPaths()` (`features/path-picker.js`) were exported but never
  imported by `app.js`, so nothing ever bound them. `#test-btn` is the only
  control that verifies the entered URL and API key before saving, and
  `#auto-detect-btn` the only one that fills the four path fields from a live
  server, so the whole connection-setup flow was unreachable from the UI
  unless the setup wizard was used. `wireConnectionButtons()` now binds both
  during `bootstrap()`. Covered by
  `tests/frontend/connection-buttons.test.js`, which asserts that bootstrap
  leaves a click handler on each button.

- The Test button stayed in its loading state forever when the metadata
  refresh after a successful connection raised. `testConnectionFromSidebar()`
  cleared the loading class only on the success path's normal exit, and
  `refreshMetadata()` throws whenever Jellyfin refuses the request, so the
  button spun until the page was reloaded. The work now runs inside
  `try`/`finally`, and a metadata failure after a good connection is reported
  as "Connected, but loading metadata failed: …" instead of escaping as an
  unhandled rejection the global handler turned into a bare, context-free
  toast.

- Auto-Detect threw `Cannot read properties of undefined (reading
  'media_path_on_host')` on a `{"status": "success"}` body that carried no
  `detected` object — an older server, or a proxy answering 200 with its own
  error page. The button then reported nothing at all: no toast, no dialog, no
  changed field. The response is now type-checked, and a success without a
  usable `detected` payload reports "could not find matching host paths". A
  body that is not an object at all is handled the same way.

### Accessibility

- The sidebar could only be resized by dragging. `#sidebar-resizer` was a bare
  `<div>` with mousedown/touch handlers: no `role`, no `tabindex`, no
  `aria-valuenow`, and no key handler. A keyboard-only or screen-reader user
  was stuck with the default width and had no way to discover that resizing
  existed. It now follows the ARIA window-splitter pattern — `role="separator"`,
  `tabindex="0"`, `aria-orientation="vertical"`, `aria-controls="sidebar"`,
  `aria-valuemin`/`aria-valuemax`, and an `aria-valuenow` kept in step with the
  applied width. ArrowLeft/ArrowRight resize by 16 px (64 px with Shift),
  Home/End jump to the 200 px/800 px bounds, and every change persists to
  `localStorage` exactly as a drag did. Unrelated keys and arrow keys combined
  with Alt/Ctrl/Meta are left alone, so the sidebar still scrolls normally. The
  separator also gets a `:focus-visible` fill, since its transparent 8 px gutter
  made the global outline trace nothing visible. Covered by
  `tests/frontend/sidebar-resizer.test.js` (13 cases).

### Security

- The folder picker rendered the server's error message with `innerHTML`.
  `GET /api/browse` echoes the rejected path in that message, and a directory
  whose name contains markup (``<img src=x onerror=...>``) is an ordinary
  filesystem entry — the app never creates it, but a mounted share can hold
  one. Navigating into such a directory made the dashboard origin parse and
  run the name, a stored XSS reachable by anyone who can write to the media
  tree. The message is now assigned through `textContent`, so the name stays
  visible text.

- `POST /api/upload_cover` accepted a payload that was not an image at all.
  The body went through `base64.b64decode(encoded)` without `validate=True`,
  which silently drops characters it does not recognise: a body of ``"@@@"``
  decoded to ``b""``, the handler wrote a zero-byte cover and answered
  ``{"status": "success"}``. The declared MIME type was never compared with
  the bytes either, so any content could be stored under a ``.png`` name. Both
  are checked now — the payload must decode under strict base64, must be
  non-empty, and must start with the signature of the MIME type it declares
  (``RIFF`` alone is not enough for WebP; the ``WEBP`` form-type marker is
  required too, since WAV and AVI share the container prefix). Line breaks in
  the base64 body are still accepted. An empty or whitespace-only
  ``group_name`` is rejected as well: covers are named ``md5(group_name)``, so
  every unnamed group was writing to the same file.

### Fixed

- One group with a non-string `name` blanked the whole dashboard. `POST
  /api/config` rejects the value (`'groups[0].name' must be a str`), but `GET
  /api/config` serves the stored file as written — `load_config()` only drops
  group entries that are not *objects* — so a hand-edited `config.json` or an
  imported file carrying `"name": 42`, `{}`, or `[]` reached the browser. The
  filter in `renderGroups()` ran `(group.name || '').toLowerCase()`, which threw
  `TypeError: ….toLowerCase is not a function`; the throw escaped through
  `updateGlobalSyncExclusionsUI()` into `loadConfig()`'s `catch`, so the page
  said "Failed to load configuration" and rendered *no* groups. Every other
  group became unreachable, including the Edit button that would have let the
  user repair the bad name. Names are now read through one helper: a string is
  used as-is, a number or boolean renders as its text form so the group stays
  visible and editable, and any other type reads as unnamed. The paths that
  need a real string — the cleanup call that names a directory and the
  scheduler exclusion ids — check the type first instead of sending or storing
  a value the server rejects. The same function also normalised `scheduler`
  only when it was *falsy*, so a stored `"scheduler": "nope"` or `42` threw
  `Cannot create property 'global_exclude_ids' on string`; it now replaces any
  non-object, and any `global_exclude_ids` that is not a list, because the
  next line calls `.filter()` on it. Covered by
  `tests/frontend/group-name-type-robustness.test.js` (20 cases).

- A group whose `source_category` was present but unusable broke the whole
  dashboard. `updateSourceTypeOptions()` read the select's value and indexed
  `sourceOptions` with it, so a value this build does not offer — `"External"`
  (capitalised) from a hand-edited `config.json` or an import, a trailing
  space, a number, or a category from a newer release — matched no `<option>`.
  The select then reported `selectedIndex` -1 and `sourceOptions[value]` was
  `undefined`; the `.forEach` on it threw `TypeError: Cannot read properties of
  undefined (reading 'forEach')`. Because the migration in `loadConfig()` only
  filled a *missing* category and copied a bogus one through, the throw escaped
  into the loader's `catch`: the page reported "Failed to load configuration"
  and rendered no groups at all, and the same call made every group's Edit
  button do nothing. The category is now resolved against the group's own
  `source_type` — `tmdb_list` only exists in the External list, so a broken
  category beside it means External, not Jellyfin — and a `loadConfig()` that
  receives a non-list `groups` or non-object entries normalises them instead of
  failing. `editGroup()` re-derives the pairing when the stored category
  contradicts the stored type, so the form cannot silently save the wrong
  category. Covered by `tests/frontend/source-category-normalisation.test.js`
  (9 cases) and `tests/frontend/source-category-load.test.js` (6 cases).

- The folder picker could write a path from a *previous* use into the field
  being edited. `_pickerCurrentPath` was only assigned on a successful
  `browseDir()`, never cleared. Open the picker for "Path in Jellyfin", reach
  `/media`, cancel, then open it for "Base Target Path": if the server refuses
  to list that field's own directory, `browseDir()` renders the error and
  returns early, so the module still held `/media` — and the breadcrumb and
  footer still named it, so pressing "Select" looked correct while writing
  `/media` into the *target path*. A wrong target path silently scatters
  symlink folders into the media tree, which is exactly what the dialog exists
  to prevent. Every opening and every browse now starts with nothing
  selectable: `#picker-select-btn` ships `disabled`, is enabled only once a
  directory loads, and is disabled again if the next browse fails. A failed
  browse leaves the footer reading "No folder selected" instead of the stale
  path. Covered by `tests/frontend/path-picker-stale-path.test.js` (3 cases).

- Importing a malformed groupings file showed an internal error and left the
  dialog half-converted. `setupImportStep2()` picked its branch with
  `data.groups || (Array.isArray(data) ? data : null)`, so any truthy value took
  the selective path, which then ran `groups.forEach(...)`: a file with
  `"groups": "not-a-list"` threw `groups.forEach is not a function` and one
  with `"groups": [null]` threw while reading `.name`. Both reached the user as
  "Failed to process import file: …" *after* step 2 had already been revealed
  and before `#confirm-import` had a handler, so the visible "Import Selected"
  button did nothing and the only way out was Cancel. The payload is now
  classified before any of the modal is rewritten: a non-list `groups`, a list
  with no usable object, and a payload that is not an object are rejected on
  step 1 with a message naming the problem, and `state.pendingImportData` is
  cleared so a rejected file is never left staged for a later save. Usable
  entries in an otherwise valid list are imported and the count of skipped ones
  is stated in `#import-warning`. That element also carries the overwrite
  warning in the template, so each branch now sets its own text — otherwise a
  later full-config import inherited the previous run's "entries skipped" note.
  Covered by `tests/frontend/import-payload-validation.test.js` (10 cases).

- The cover generator's controls were inert. Its template wired six inputs
  with inline `oninput="renderCover()"` / `onchange="renderCover()"`
  attributes, but inline handlers resolve their names on `window` and
  `cover-generator.js` only *exports* `renderCover`. Every keystroke in the
  "Cover Text" field therefore threw `ReferenceError: renderCover is not
  defined` and the preview stayed frozen at whatever `openCoverGenerator()`
  had drawn — changing the theme, border, or any of the three colours never
  redrew it. "Apply Cover" and "Download" were dead for a different reason:
  nothing had ever bound them, so clicking either did nothing at all. The
  inline attributes are gone and `initCoverGenerator()` binds the six inputs
  plus both buttons, once per element so a re-init cannot stack duplicate
  renders. Pinned by `tests/frontend/cover-controls-wiring.test.js`.

- The SPA aborted every request after 60 s, including a full sync.
  `apiRequest()` applied one `DEFAULT_TIMEOUT_MS` to all calls, but a sync
  rebuilds each group directory link by link and walks the whole Jellyfin
  library: the server allows its worker 120 s by default (`GUNICORN_TIMEOUT`)
  and the README tells operators of large libraries to raise that further. The
  client therefore gave up on work the server was still doing and showed
  "Request timed out", while the sync kept filling directories in the
  background — so the user's retry answered `409` because the first run still
  held the run lock, and the UI reported a failure for a run that eventually
  succeeded. `runSync()` and `previewSync()` now use a 15-minute budget;
  ordinary reads keep the 60 s one. The timeout dialog also says that a sync
  may still be running and to wait before retrying, instead of implying the
  request simply failed. `features/sync.js` now calls those wrappers rather
  than posting to the endpoint itself, so the budget cannot drift between the
  two. Pinned by `tests/frontend/sync-timeout.test.js`.

- A run in which every group failed still reported "Sync complete!" in the
  success colour. `syncAll()` rendered each group's `error` in the results
  panel but built the toast from the link total alone, so a library-wide fetch
  failure — or a config whose groups were all invalid — looked like a clean
  run to anyone reading the toast. It now states how many groups failed and
  uses the `warning` style, mirroring `cleanup.js`. The same function also
  reduced over `result.results` without a guard, so a response without that key
  threw a `TypeError` inside the click handler and left the button spinning
  with no message; a missing or non-array `results` is now treated as an empty
  run, and a non-numeric `links` value is skipped rather than producing
  `NaN`. `previewSyncAll()` had the mirror problem: a malformed `results` fell
  through to "No groupings configured.", pointing the user at a config problem
  that did not exist. Pinned by `tests/frontend/sync-result-reporting.test.js`.

- A group with `create_as_collection` enabled still went through
  `_prepare_group_directory` before its items were pushed into a Jellyfin
  Boxset. The group writes no symlinks, so the only effect was an empty
  `<target>/<group>` folder left behind in the library root, which Jellyfin
  then scanned on every library refresh as an extra, permanently empty folder.
  The collection branch now skips directory preparation entirely and lets
  `_process_collection_group` resolve the cover itself. Pinned by
  `tests/test_collection_groups.py`, which also covers the previously untested
  collection path (dry-run preview, extending an existing collection versus
  creating one, per-group error reporting, and cover upload failures).

- The scheduled global sync aborted on a hand-edited `"groups": null` and left
  no trace. `_run_global_sync_job` read `config.get("groups", [])` and
  iterated the result *before* the `try` that guards `run_sync`, so a
  `groups` value that was `null` (or a number, or a string) raised
  `TypeError: 'NoneType' object is not iterable` outside every handler. On an
  APScheduler worker thread nobody is watching that exception: the tick died,
  the log held only APScheduler's own traceback, and the next scheduled run
  repeated it — a config the UI happily saves could silently disable global
  sync. The whole handler now runs inside the `try`, `groups` and the
  exclusion list are normalised to lists first (each logged once when
  malformed), and a config that lists no syncable group returns early
  instead of falling through. The per-group and cleanup handlers had the
  same shape — `load_config()` sat outside their `try` — so an unreadable
  config directory escaped them too and is now logged like any other failure.
  `tests/test_scheduler_jobs.py` covers all three handlers, the scheduling
  guard clauses, and `validate_cron`; `scheduler.py` goes from 74.65 % to
  100 % statement coverage.

- `POST /api/jellyfin/auto-detect-paths` could outlive the gunicorn worker
  timeout. The handler searches the local filesystem for the filename of up to
  `_AUTO_DETECT_SAMPLE_LIMIT` (10) sample items, and every search was given its
  own `_AUTO_DETECT_TIMEOUT` (30 s) and `_AUTO_DETECT_MAX_FILES` (50 000)
  allowance — a worst case of ten times the budget, i.e. 300 s of walking
  against the 120 s `GUNICORN_TIMEOUT`. A large or slow media tree therefore
  answered the request by killing the worker (502, no diagnostic) instead of
  returning the "nothing detected" result the UI can act on. A single
  `_DetectBudget` is now shared by every search in one call: the deadline and
  the file cap are spent once, later searches stop instead of restarting the
  allowance, and the handler breaks out of the sample loop as soon as the
  budget is gone. `tests/test_auto_detect_budget.py` pins the walk itself and
  asserts that a request creates exactly one budget rather than one per item.

- `docs/API.md` contradicted itself about authentication on `GET /api/health`.
  The overview paragraph correctly said the route stays unauthenticated so
  container probes keep working, while the route's own **Auth:** line claimed
  auth was required whenever `APP_PASSWORD` is set. `routes._check_auth`
  exempts `main.health_check`, so the section was wrong and a reader could not
  tell which sentence to believe. The section now states the real behaviour,
  and `tests/test_docs_accuracy.py` derives the exemptions from
  `_check_auth` and requires the matching docs section to agree, so the prose
  cannot drift from the code again.

- Closing a dialog dropped keyboard focus instead of returning it to the
  button that opened it. `showModal()` remembered its trigger through the
  element's `id` (`data-previous-active`), but the per-group "Cover" and
  "Edit" buttons are created in a loop in `groupings.js` and have no `id`, so
  the stored value was always the empty string and `hideModal()` restored
  nothing. Focus stayed on the now-hidden `role="dialog"`, which left the
  next Tab press restarting from the top of the document (WCAG 2.4.3). The
  trigger is now held by reference, so an element without an `id` restores
  correctly; a trigger removed by a re-render while the dialog was open is
  dropped instead of focused. The loading overlay records and restores focus
  the same way, and the `Escape` handler no longer runs a
  `[onclick*="<modal-id>"]` lookup that could never match. Showing a dialog
  that is already open keeps the original trigger, so
  `showConfirmDialog()` replacing its own contents no longer forgets the
  button the user pressed.

- The `prefers-reduced-motion` block in `variables.css` disabled only
  `animation`, so the buttons, cards, modal, and progress bar — all of which
  move through `var(--transition)` — kept animating for users who asked their
  OS to reduce motion. It now also resets `transition`, covers
  `::before`/`::after`, and turns off smooth scrolling.

- "Preview First" followed by "Sync Now" in the sync confirmation dialog
  answered `429 Please wait before syncing again`. The preview and the sync
  shared one per-IP rate-limit timestamp, so the dry run the dialog had just
  offered consumed the budget for the write the user then confirmed: nothing
  was written, and the only remedy was to click again after five seconds. A
  dry run is read-only, so previews and syncs now keep separate budgets and
  neither blocks the other, while repeated calls of the same kind are still
  throttled.

- The sync confirmation dialog promised an item count it never filled in.
  `(<span id="confirm-sync-item-count">0</span> potential media items)` was
  left behind when `showConfirmSyncDialog()` was rewritten, so every user was
  told their sync would create "0 potential media items" no matter how many
  groups were configured.

- `renderCover()` threw `TypeError: Cannot read properties of null (reading
  'getContext')` instead of doing nothing when the cover canvas was not in the
  document. The function runs from `document.fonts.ready` and a `setTimeout`
  fallback, both of which outlive the element they were scheduled against, so
  a page rendered without the cover partial — or one whose dialog was torn
  down before fonts settled — crashed in a timer. A canvas whose
  `getContext('2d')` returns `null` threw one line later on `setTransform()`.
  Both cases now return early; the dialog stays open with an empty preview.

- A failed sync or preview produced `Uncaught (in promise)` in the console
  together with a second error toast. The handlers ran
  `syncAll().finally(...)` without awaiting the result, and `finally()` passes
  the rejection on to the promise it returns, so an error that
  `apiRequest()` had already reported escaped as an unhandled rejection into
  the global listener. The loading state is now driven by an awaited helper
  that absorbs the already-reported failure.

- The folder picker rendered as an unstyled block inside the page instead of a
  dialog. Its overlay `<div id="path-picker-modal">` had lost `class="modal"`
  while keeping `role="dialog"`/`aria-modal`, and nothing in any stylesheet
  matched the `picker-*` classes at all — both were dropped when the single
  `index.html` was split into partials and CSS modules in May. The overlay was
  therefore never hidden before the first `showModal()`, so on every page load
  the picker's title, breadcrumb and empty listing appeared in the document
  flow, and once opened it had no backdrop, no fixed positioning and no
  scrollable body. The class is restored and the rules live in
  `components.css` again.

- The cleanup, preview-sync, confirm-sync, export, import and cover-generator
  dialogs opened by flipping `element.style.display` instead of calling
  `showModal()`. They looked correct, but `aria-hidden` stayed `"true"` on a
  visible `role="dialog"`, so screen readers skipped the whole dialog; focus
  was never moved inside it; and `body.modal-open` was never added, so the
  page behind the dialog still scrolled on a phone. Opening and closing now go
  through the shared lifecycle helper.

- The cover generator nested a second `role="dialog" aria-hidden="true"` on
  its own card, inside the modal that `showModal()` un-hides. The inner
  attribute was never cleared, so the entire dialog content stayed hidden from
  assistive technology even while the outer overlay was open. The card is now
  a plain content box.

- The setup wizard's overlay was missing `aria-hidden="true"`, so it was
  exposed to screen readers while closed.

- Importing a *full* configuration file that had no `groups` key (an older
  export, or a hand-written one) left `state.currentConfig.groups` undefined.
  The `renderGroups()` that runs right after the import threw from
  `updateGlobalSyncExclusionsUI()`'s `groups.map(...)`, so the dashboard went
  blank and the groups list could not be recovered without a page reload.
  The payload is now normalised: a non-list `groups` becomes `[]`, non-object
  entries are dropped, and a missing or malformed `scheduler` becomes `{}`.

- A rejected import left the in-memory config already mutated. `performImport()`
  assigned the imported groups to `state.currentConfig` *before* awaiting
  `saveConfig()`, so when the server answered 400 the UI kept showing groups it
  had never stored, the import modal closed as if it had worked, and the next
  save from anywhere in the UI failed again for a reason nothing pointed at.
  The previous config is now restored on failure and the modal stays open so a
  different file can be chosen.

- A *broken* symlink left at `<target>/<group>` aborted the sync for that
  group with `FileExistsError`. `_prepare_group_directory()` guarded the
  cleanup with `Path.exists()`, which follows links, so a link whose
  destination had been deleted reported "not there": the cleanup was skipped
  and the following `mkdir()` failed because the name was still taken. The
  dangling link is now detected with `is_symlink()` as well, removed, and
  replaced with a real directory.

- A group directory that is a symlink had the *link target's* contents
  deleted. `_clear_group_directory()` walked `iterdir()`, which follows the
  link, so a leftover `<target>/<group>` symlink pointing at a media folder
  made every sync delete the real files there and then recreate the group as
  an empty directory. The link is now removed on its own and a real directory
  is created in its place, so the target is never written to.

- A seasonal group that went out of season deleted the directories of the
  nested groups below it. Cleanup called `shutil.rmtree()` on the group's
  folder, so with both `Anime` (out of season) and `Anime/Action` (in season)
  configured, the child's symlinks were removed along with the parent's and
  only reappeared if the child happened to sync afterwards. Out-of-season
  cleanup now removes only the group's own entries, exactly as a sync does
  before refilling the folder, and drops the folder itself only when no nested
  group still lives in it.

- `jellyfin_auto_groupings.rules.group_by_decade()` and
  `jellyfin_groupings.process_groupings()` raised on a non-finite numeric
  `PremiereDate`. `int(float("nan"))` raises `ValueError` and
  `int(float("inf"))` raises `OverflowError`, so a single partially scanned
  item aborted the whole grouping pass — in `process_groupings()` the failure
  happened inside `sorted()`, discarding the sort names for every *other*
  item in the collection. Non-finite numbers are now treated as an unusable
  date and the item is skipped. A finite numeric year, including a fractional
  one, keeps its existing date-ranking behaviour.

- `jellyfin_groupings.main.main()` returned normally when `JELLYFIN_API_KEY`
  was unset, so the process exited 0 for a run that never contacted Jellyfin
  and a scheduler recorded a failed configuration as a success. It now exits
  1. The same entry point also let the errors newly reachable through the
  request timeout escape as tracebacks; a refused connection, a timeout, an
  HTTP error status, and a 200 response with a non-JSON body are now reported
  on stderr as one line, with the configured timeout value named, and exit 1.

- `jellyfin_groupings.JellyfinClient` and the root `main.JellyfinGroupings`
  built their request URLs by interpolating values into the query string, so a
  collection name that contained a URL metacharacter changed the request
  instead of the name. `"Tom & Jerry"` was sent as `Name=Tom` plus a stray
  `Jerry` parameter and created a collection called `"Tom "`; `"Best of 2024
  #1"` put a `#` in the URL, which starts a fragment, so the `Ids` parameter
  was never sent at all and Jellyfin created an empty collection while the sync
  reported success; `"C++"` became `"C   "`. `Name`, `Ids`, and `ParentId` now
  go through `params=`, which percent-encodes them.

- `tmdb.get_tmdb_recommendations()` aborted the entire sync run when TMDb
  answered `"results": null` for an item with no recommendations. The looped
  value was iterated unguarded, so the `TypeError` escaped the caller's
  `except (RequestException, RuntimeError, ValueError)` and one such item
  killed the run instead of skipping that item. A non-list `results` is now
  skipped, and a recommendation `id` that is an object or a list is dropped
  instead of being stringified into a provider id such as `"{'a': 1}"`.

- The `auto_group.py` request helpers (`get_libraries`, `get_library_items`,
  `create_collection`, `add_to_collection`) raised `AttributeError` instead of
  returning their documented empty list / `None` / `False` when
  `JELLYFIN_URL` was not a string. `url.rstrip("/")` ran before the `try`
  block, so a hand-edited `config.json` holding a number, `null`, or a list
  killed the CLI on the first library. The URL is now validated by a shared
  `_base_url()` helper, which also trims surrounding whitespace.

- `jellyfin_groupings.process_groupings` aborted the whole collection pass when
  one item carried a numeric `PremiereDate` next to items with ISO strings
  (`TypeError: '<' not supported between instances of 'str' and 'int'`). The
  sort key now normalises both shapes — a numeric year sorts as that year's
  first day — and falls back to the title when neither is usable. A null
  `Name`, and a collection whose own `Name` is null (which produced sort names
  like `"None 01"`), are handled too.

- `extract_year_from_title()` mis-parsed several everyday title shapes:
  `"Movie[2023]"` (bracket touching the title) returned no year, padded values
  such as `"  Movie (2023)  "` matched nothing and came back with their spaces
  intact, and a five-digit number was split into a bogus year —
  `"Movie 12345"` became `("Movie 1", 2345)`. A bare year is now only accepted
  when it is not part of a longer number and falls within 1800-2100, the same
  range `group_by_decade` uses. A title that is only a year (the film
  `"1917"`) keeps its text instead of becoming an empty name. Trailing
  separator punctuation is trimmed while a period that ends a name is kept, so
  `"Dr. (2023)"` keeps its `"Dr."`.

- The collection sort key treated any non-empty `PremiereDate` string as a
  date, so a placeholder such as `"not-a-date"` ranked ahead of an undated item
  and shifted every later sort name. A value only ranks as a date when it
  starts with `YYYY-MM-DD`; an out-of-range numeric year is ignored the same
  way.

- Every external list fetcher (`imdb`, `trakt`, `tmdb`, `letterboxd`) could be
  pointed at an arbitrary host. A group's `value` in `config.json` was checked
  with `urllib.parse.urlparse`, which reads everything before the last `@` as
  userinfo, so `https://evil.example\@letterboxd.com/u/list/x` reported the
  Letterboxd host. `requests`/`urllib3` end the authority at the backslash and
  connected to `evil.example`, so the server fetched an attacker-chosen URL on
  the caller's behalf — a server-side request forgery primitive driven by
  config. The validators now resolve the host with both parsers and reject the
  URL when they disagree; they also reject embedded `user:pass@` credentials.
  The shared helpers (`parse_outbound_url`, `split_outbound_url`,
  `host_matches`) live in `_common.py` so all four fetchers validate the same
  way.
- An AniList or MyAnimeList group whose `source_value` was typed with padding
  (`jane / completed`, `jane/ completed`) failed with
  `Unknown MAL status: ' completed'`, listing values that looked identical to
  the one the user had entered. Both halves of the `account/status` value are
  now trimmed before they reach the provider, and an empty status becomes
  "no status" instead of being looked up as one.

- `group_by_key` used the raw field value as a dictionary key, so an item
  whose field holds a list — Jellyfin's `Genres`, `Tags` and `Studios` all do —
  raised `TypeError: unhashable type: 'list'` and aborted the whole grouping
  pass. Unusable values are now skipped, leaving that item out of the result.

- `chunk_list([], 0)` returned `[[]]`: one empty chunk instead of none, so a
  caller that had nothing to do still saw a single work item. An empty input
  now yields no chunks at any size.

- `format_release_date()` matched its patterns from the start of the raw
  value, so a padded date bypassed every one of them and was returned with its
  whitespace intact (`"  2023-05-12  "` came back unchanged); a padded year was
  not recognised at all. Surrounding whitespace is stripped first.

- The post-save UI refresh aborted with
  `Cannot read properties of null (reading 'style')` whenever
  `updateSourceValueUI()` ran against a document without the grouping form —
  which is the case after a config save and in the wizard. The saved config
  was fine, but the group list and source-type select were left stale. The
  function now returns early when the controls it drives are absent.

- A Letterboxd list URL pasted from a browser silently synced only its first
  page. `_validate_list_url` kept the query string, fragment and any existing
  `/page/N/` segment, and the page walk then appended the next-page segment
  behind them, so `…/u/list/x?utm_source=tw` requested
  `…/u/list/x?utm_source=tw/page/2/`. Letterboxd routes on the URL path, so
  every "page" resolved back to page 1: the walk re-read the same 72 films
  until the 50-page safety cap, returned only that first page, and logged a
  truncation warning that blamed the list's length. The URL is now reduced to
  scheme, host and path, so pagination resumes where the list actually
  continues.

- `utils/formatting.py` documented that every helper normalises its input
  before formatting, but four of them did not: `slugify()` and
  `format_release_date()` raised `AttributeError`/`TypeError` from an inner
  `.strip()`/`re.match` when a field arrived as a number or a list, and
  `truncate_text()` returned that list or dict unchanged despite declaring
  `-> str`. A corrupt item could therefore turn a blank table cell into a 500.
  All four now return their documented empty result for unusable input.

- `format_resolution()` rendered booleans and junk as a resolution:
  `format_resolution(True, 1080)` returned `"Truex1080"` because `bool` is an
  `int` subclass. Pixel dimensions are now coerced through a dedicated helper
  that rejects booleans, non-integral values, `NaN`/`Infinity`, and
  non-positive numbers, accepting numeric strings (`"1920"`) and integral
  floats (`1920.0`) so existing payload shapes keep working.

- `sanitize_filename()`, `normalize_title()`, and `extract_year_from_title()`
  raised `AttributeError`/`TypeError` on a non-string argument instead of
  reporting it as unusable, contradicting the same tolerance the rest of the
  helpers provide. They now return `"unnamed"`, `""`, and `("", None)`
  respectively, so a malformed title cannot abort a grouping run.

- `POST /api/config` accepted group names that every sync then refused. A
  name with a `.`/`..` segment, an embedded NUL byte, a Windows drive path,
  or a path segment longer than 255 bytes saved without complaint, and each
  sync of that group answered `Invalid group name` — or, for the oversized
  segment, failed with `ENAMETOOLONG` while creating the directory. Nothing in
  the message connected the failure to the name, so the group looked broken
  for no reason. These names are now rejected at save time with a message
  naming the rule that was broken.

- Duplicate group names were compared after trimming only, so
  `Anime/Action` and `Anime//Action` — or `Anime/Action` and `Anime / Action`
  — passed validation and then wrote into the same directory, with the second
  group overwriting the first and its scheduler job never running. The
  comparison now uses the same folder-path normalisation as the sync, while
  staying case-sensitive.

- `normalize_group_relpath` documented that absolute paths are rejected, but
  a leading `/` is stripped like any other empty segment, so `/etc/passwd`
  became the nested folder `etc/passwd`. That is the safe behaviour; the
  docstring was corrected to describe it instead of promising a rejection.

- Two overlapping sync runs corrupted each other's group directories. Each
  run clears a group's directory and then refills it one symlink at a time, so
  a second run entering the same group deleted links the first had just
  created. A scheduled sync firing during a `POST /api/sync` from the UI left
  the directory holding an arbitrary mix of both, and the reported link count
  described neither. Reproduced with two runs creating 50 links each: the
  directory ended with 91 entries (41 from one run, 50 from the other).

  `scheduler.sync_lock` never protected this. It was a `threading.Lock` taken
  only by the three scheduler job handlers, so the HTTP sync and cleanup routes
  never touched it — and because the Docker image runs gunicorn with several
  worker processes, each worker had its own unrelated copy anyway.

  Runs that write to the target directory now hold `sync.sync_run_guard()`: an
  in-process lock plus an exclusive `flock` on `<config dir>/sync.lock`, so
  scheduled runs, UI runs, and runs in other workers are all serialised. A
  conflicting `POST /api/sync` or `POST /api/cleanup` answers `409` without
  changing anything, and a scheduled job logs that it skipped instead of
  queueing a run behind a long sync. Dry runs take no lock, so previews stay
  available while a sync is running.

- A refused connection or a failed DNS lookup was reported as
  "Connection timed out.", discarding the host, the URL and the underlying
  `errno`. `urllib3.exceptions.NewConnectionError` subclasses
  `ConnectTimeoutError`, so the `isinstance` check in `network._reraise_timeout`
  matched a failure that had nothing to do with a timeout and replaced it with
  a generic message. Every caller that prints the exception text inherited the
  wrong diagnosis — most visibly `POST /api/test-server`, which answers
  `{"message": "Connection error: Connection timed out."}` for a mistyped port
  or an unresolvable hostname, pointing the user at a network timeout when the
  server was simply not listening. `NewConnectionError` is now excluded from
  the relabel, so the original message naming the host and the reason reaches
  the user. Genuine handshake timeouts (`ConnectTimeoutError` without a nested
  connection failure) still report "Connection timed out."

- A `year` group with a comparison value (`>=2000`, `<=2010`, `>1990`, `<2000`)
  silently linked the entire library. The value was forwarded verbatim to
  Jellyfin's `years` filter, which only understands literal years and
  comma-separated year lists, so the server ignored the unrecognised value and
  answered with the unrestricted library. Comparisons are now evaluated in
  memory by `_match_year`, which already implemented those operators, and the
  preview route resolves them the same way so the preview count matches what
  the sync links. Literal years and lists still use the server-side filter.

- `year` is selectable in the source-type dropdown, and a year rule in the
  complex-rule editor is a text field rather than a dropdown. The backend and
  `docs/API.md` both accepted `year`, but the UI never offered it: the
  dropdown had no entry, and the rule editor rendered an empty `<select>`
  populated from the metadata endpoint, which has no year list, so a year rule
  could not be entered at all. Year values accept a literal (`2000`), a list
  (`1999,2000`), or a comparison (`>=2000`).

- A bare string in `Tags`, `Genres`, or `Studios` is now read as one value
  instead of being iterated character by character. Jellyfin normally sends
  these fields as arrays, but a hand-edited payload, a proxy, or an older
  server can put a plain string there, and iterating that string turned a
  single tag `"action"` into six groups named `a`, `c`, `t`, `i`, `o`, `n`.
  The same bug made a studio rule unable to match at all, because
  `_match_condition` compared each letter against the rule value. All eight
  affected call sites (`group_movies_by_tag`, `group_movies_by_genre`,
  `group_by_tag`, `group_by_genre`, `group_by_studio`, `get_movies_by_query`,
  plus the legacy `jellyfin_groupings` variants and `sync._match_condition`)
  now share `utils.helpers.string_list` / `utils.helpers.studio_names`, so
  one rule covers every caller.

- `POST /api/config` now enforces the group-name rules `docs/API.md`
  documented but nothing checked: names must be non-empty after trimming and
  unique, and the list is capped at 200 entries. Duplicate names were the
  harmful case — both groups resolve to the same target directory, so the
  second silently overwrote the first, and the per-group scheduler registers
  jobs as `group_sync_<name>` so the later duplicate never ran at all. An
  empty or whitespace-only name had no directory to write to and failed at
  sync time instead of at save time. Comparison ignores surrounding
  whitespace (stripped when the folder is created) and is case-sensitive.

- A path the OS refuses to `stat` no longer turns into an HTTP 500.
  `Path.exists()` / `Path.is_dir()` only swallow the "not there" errors, so a
  single component longer than `NAME_MAX` (or an `EIO` on a damaged entry)
  raised straight out of the handler:
  `GET /api/browse?path=<4000 chars>` answered 500 instead of the `400` that
  every other malformed path gets; `POST /api/cleanup` failed the *whole*
  request — discarding the folders in the same body that could be deleted;
  and `GET`/`POST /api/cleanup` raised in the guard that is supposed to
  answer "nothing to list" / "target path not found". Those checks now go
  through `routes._safe_exists` / `routes._safe_is_dir`, which treat an
  unstattable path as absent; a rejected cleanup folder is reported in the
  `errors` array of the `207` response while the rest proceed. Error messages
  and log lines elide the offending name and quote only the OS reason, so a
  multi-kilobyte name no longer floods either.

- The SPA's error dialog now shows the reasons from a validation failure
  instead of only the generic summary. `POST /api/config` answers with
  `"Invalid config field type(s)"` plus an `errors` array naming each bad
  field; the client kept only `message`, so the user was told something was
  wrong with no clue which field to fix. Up to three details are listed with
  a count of the rest, and `.error-dialog-message` preserves the line breaks.

- A rejected save no longer looks like a successful one in the group form.
  `saveAllConfig()` swallowed every failure, so the form cleared itself and
  the rejected entry stayed in memory — reintroducing the same error on the
  next save from anywhere in the UI, with nothing pointing at the offending
  group. It now resolves `true` only when the server accepted the config; the
  form keeps the typed values and rolls the in-memory change back on failure.
  A post-save UI refresh error no longer counts as a failed save.

- `GET /api/browse` no longer blanks the folder picker when one entry in the
  directory cannot be inspected. The listing was built in a single
  comprehension whose `entry.is_dir()` call *raises* for an entry it cannot
  classify — a stale handle on a dropped mount, an I/O error — so the
  comprehension aborted and the handler answered `400`, losing every sibling
  directory the user could browse. Each entry is now classified on its own; an
  unstatable one is logged and skipped. `403` for a path outside the browse
  roots and the empty listing for an unreadable directory are unchanged.

- `GET /api/cleanup` no longer returns HTTP 500 (and no items) when a single
  directory in the target tree cannot be read. The listing walk called
  `directory.iterdir()` unguarded inside an `except OSError` that covered the
  whole traversal, so one inaccessible folder — a root-owned library
  directory, a mount that dropped away, a stale NFS handle — discarded every
  other deletable folder the user did want to see. An unreadable subtree is
  now logged and skipped, and an entry whose `stat` fails (dangling link,
  symlink loop, permission error) is not offered for deletion because it
  cannot be classified. An unreadable target root yields an empty list rather
  than an error page.

- A non-integer `TotalRecordCount` no longer aborts a Jellyfin item walk.
  The walk compared the running `StartIndex` directly against that value, so
  a proxy or server that sent it as a string (`"250"`) or replaced it with an
  object raised `TypeError: '>=' not supported between instances of 'int' and
  'str'` **after** the first page had been yielded. The caller collected part
  of the result and then lost the whole run, instead of receiving a short but
  usable list. The count is now normalised by `_total_record_count()`: a
  numeric string is converted (a `"250"` total still ends the walk as soon as
  it is reached), while an object, list, float, bool, or non-numeric string is
  logged as unusable and treated as "unknown". With no usable total the walk
  falls back to the page-length rule, which is exactly how the TMDb list
  walker already treats a malformed `total_pages`. Both
  `_paginate_jellyfin` and `fetch_all_jellyfin_items` path through the same
  comparison.

- An `Items` container that is present but `null` no longer returns `None`.
  `body.get("Items", [])` falls back to the default only when the key is
  *absent*, but Jellyfin sends `"Items": null` for an empty result set. That
  `None` reached callers documented and annotated as returning
  `list[dict[str, Any]]`, so the first `len()` or iteration raised `TypeError`
  far from the request that produced it — the whole group aborted instead of
  yielding no items. Entries inside the array that are not objects are now
  dropped as well: a `null` placeholder made `_filter_by_item_type` and every
  `item.get(...)` in the grouping pass raise `AttributeError`. The same
  coercion now covers both package clients, `JellyfinAPI`,
  `jellyfin.fetch_jellyfin_items`, `get_user_recent_items`, the paged library
  walk, `jellyfin_groupings`, `main`, `auto_group`, and `jellyfin_groupings.main`.

- The paged Jellyfin walk treats `"Items": null` as the end of the result set
  instead of logging a "not a list" warning on every empty page. A key holding
  a string or an object is still reported as malformed and stops the walk.
  `StartIndex` now advances by the raw page length rather than the filtered
  one: advancing by the filtered length re-requested the discarded entries and
  duplicated every item that followed them, and a page whose entries were all
  discarded ended the walk while valid items remained.

- `get_users()` on both package clients returns `[]` for a body that is not an
  array. A `null` body previously came back as `None` despite the `list`
  annotation, and `get_first_admin_user_id()` raised `TypeError` while
  iterating it instead of reporting that no users were found.

- A Jellyfin field that is present but `null` no longer aborts a sync run.
  `dict.get(key, {})` returns the default only when the key is *absent*, so
  `item.get("ProviderIds", {}).get("Imdb")` raised `AttributeError` for the
  `"ProviderIds": null` Jellyfin sends for items it never matched to a
  provider. One such item failed the whole group: IMDb, Trakt, TMDb, AniList,
  MyAnimeList and Letterboxd list groups all resolve matches through that
  lookup, and the recommendations source uses the same pattern on recent
  items. Non-object values such as a string or a list are skipped the same
  way instead of being treated as a mapping.

- `get_first_admin_user_id()` tolerates a user whose `Policy` is `null`.
  The chained `u.get("Policy", {}).get("IsAdministrator")` raised
  `AttributeError` on `"Policy": null`, which aborted the call rather than
  moving on to the next user. Both the package client and the standalone
  `jellyfin_groupings` client now skip such a user and fall back to the first
  user that has an `Id`.

- `group_movies_by_tag()` and `group_movies_by_genre()` in the standalone
  `jellyfin_groupings` module skip `null` tag/genre lists and non-string
  entries. `Tags: null` raised `TypeError: 'NoneType' object is not iterable`
  and aborted the grouping pass for the entire library, while a non-string
  entry would have produced an unusable group key.

- Jellyfin responses whose body is valid JSON but not the expected container
  raise a normal Jellyfin error instead of `AttributeError`/`TypeError`.
  An error page served with status 200, or a proxy in front of the server,
  can return a list, a string, or `null` where an object or an array is
  expected. `fetch_jellyfin_items`, `get_user_recent_items`, and the paged
  library walk now report `Expected a JSON object ...`; `get_libraries`,
  `get_users`, and `get_library_id` report `Expected a JSON array ...`, and
  drop array entries that are not objects rather than failing on them.

- The confirmation dialog settles its promise on every close path.
  `showConfirmDialog()` attached click handlers only to its Confirm and
  Cancel buttons, while `hideModal()` also closes the dialog for the Escape
  key, a backdrop click, and the × button. Those three paths removed the
  dialog but never resolved the returned promise, so a caller awaiting the
  answer hung forever: after pressing Escape on **Delete Grouping** or
  **Clear All Groupings**, neither the deletion nor the cancellation ran and
  the button appeared to do nothing. A new `onModalHide()` hook settles the
  pending promise exactly once whenever the dialog is hidden, with `false`
  unless the Confirm button was the trigger.

- `hideModal()` notifies hide listeners only on a real open-to-closed
  transition, so a redundant close of an already-hidden dialog cannot settle
  a later, unrelated dialog.

- A second `showConfirmDialog()` call while one is still open settles the
  earlier promise as cancelled. Both calls share the same dialog element, so
  the first caller would otherwise wait forever for an answer that the
  replaced dialog can no longer deliver.

- The Jellyfin item walk stops when the server repeats a page.
  `fetch_all_jellyfin_items` and `_paginate_jellyfin` advance `StartIndex`
  and trust the server to honour it. A reverse proxy that strips the
  parameter, or a Jellyfin build that ignores it for a particular query,
  answered every request with the same page: the sync run hung while the
  accumulated item list grew without bound. Both walkers now compare each
  page's item IDs with the previous page and end the walk with a warning
  instead of appending the same entries forever.

- The item walk is capped at 1000 pages (`_MAX_ITEM_PAGES`). A server that
  keeps returning fresh full pages is truncated at the cap and logged as a
  warning, matching the external list fetchers, so a partial result is never
  mistaken for the whole library.

- `_paginate_jellyfin` ends the walk when `Items` is not an array instead of
  handing an unusable value to the caller (which then failed later with an
  unrelated error).

- `tests/test_item_pagination_guards.py` covers both guards: the repeated
  page, the page cap, non-array `Items`, a missing `TotalRecordCount`, and the
  normal multi-page walk.

- A partially successful cleanup reported itself with an invisible toast.
  `cleanup.js` calls `showToast(msg, 'warning')` when `POST /api/cleanup`
  answers `207 partial_success`, but `components.css` only defined
  `.status-msg.success` and `.status-msg.error`. The warning toast kept the
  bare `.status-msg` rule — no background, no border, inherited text colour —
  so instead of a notification the user got unstyled text in the corner while
  the message named exactly which folders could NOT be deleted. The `.warning`
  and `.info` variants now have rules of their own.

- The toast text in every variant missed WCAG AA against its own tinted
  background. The rules took their colour from the shared
  `--success-color`/`--error-color`/`--warning-color`/`--accent-color`
  variables, which measure 5.87:1, 4.18:1, 6.80:1, and 3.48:1 respectively —
  and the toast body is 0.85rem at weight 500, below the 18.66px-bold
  large-text threshold, so the applicable ratio is 4.5:1 and not 3:1. Each
  variant now sets its own lighter tint on the dark page and a darker one
  inside `prefers-color-scheme: light`, leaving the shared variables untouched
  for icons, borders, and headings. All four variants measure at least 5.2:1
  in both themes. `tests/frontend/toast-variants.test.js` derives the toast
  types from the `showToast()` call sites in `static/js`, fails when one has
  no CSS rule, resolves the real cascade in jsdom, and recomputes the ratios
  against the page background from `variables.css` — the toast is a fixed
  overlay, so it sits on `--bg-color` and not on a card surface.

### Changed

- `docs/ARCHITECTURE.md` listed Jellyfin-proxy, export/import, and wizard
  routes under "all HTTP endpoints". None of those exist: the blueprint serves
  16 routes, and export, import, and the wizard are client-side features that
  persist through `POST /api/config`. The section now names the real routes.

- The README `## Configuration` section documented three environment variables
  (`JELLYFIN_URL`, `JELLYFIN_API_KEY`, `DRY_RUN`) while `.env.example` — which
  points at the README "for full documentation" — listed `APP_PASSWORD`,
  `SCHEDULER_ENABLED`, the `NETWORK_RETRY_*` family, the gunicorn knobs, and
  `ALLOWED_NON_CSRF_ENDPOINTS`. All of them are now documented and grouped by
  which process reads them, including `VIRTUAL_JF_PORT` for the mock server.

### Added

- `tests/test_docs_accuracy.py` compares the prose against the code, so the
  documentation cannot drift silently again: every route the blueprint serves
  must appear in `docs/API.md`, `docs/API.md` may not document a removed route,
  `ARCHITECTURE.md` may not advertise an endpoint that was never written, and
  every variable in `.env.example` must be described in the README.

- `tests/frontend/confirm-dialog.test.js` covers all five close paths of the
  confirmation dialog (Confirm, Cancel, Escape, backdrop, ×), the outcome of
  each, and that a dismissal never leaks into the next dialog.

- `tests/test_seasonal_dates.py` and
  `tests/frontend/seasonal-dates.test.js` cover the seasonal date pickers and
  the config-save validation that guards them.

- `_common.is_valid_mmdd()` validates a seasonal `MM-DD` value against a real
  calendar. It is shared by the request validation and the tests, so the
  save-time check and the sync-time parser cannot drift apart again.

### Fixed

- A seasonal group's dates are validated as real calendar days instead of
  merely matching the `MM-DD` shape. `POST /api/config` accepted `02-31`,
  `02-30`, and `04-31`, which `sync._parse_mmdd` rejects at sync time; because
  `sync._is_in_season` treats an unparseable window as "always in season",
  such a group was synced forever and its folder was never removed at the end
  of the season. February 29 is still accepted, since the window compares only
  month and day.

- The seasonal day selectors in the group form list only the days that exist
  in the selected month. Both selects previously offered 1-31 regardless of
  the month, so picking the 31st while February was selected produced a
  `02-31` config the backend could not parse. The day list now follows the
  month, clamps a now-invalid selection to the last day of the month, and
  `editGroup()` restores a stored date through `setSeasonalDate()` so an
  existing `12-01` value survives the round trip.

- `tests/test_provider_payload_robustness.py` pins the response shapes that
  used to crash a sync. Every fetcher parses a body written by somebody else,
  and the malformed shapes below emitted `AttributeError`/`TypeError`, which
  were not in the `except` tuple at the sync layer, so one bad upstream
  payload aborted the whole run instead of failing a single group.

- Regression tests for the standalone `auto_group.py` helper moved into
  `tests/test_auto_group.py`. The previous suite lived in a root-level
  `test_auto_group.py`, but CI runs `pytest tests/`, so none of it ever
  executed; `auto_group.py` sat at 49% coverage while looking tested. The
  module is now at 79% and its config, grouping, and HTTP paths are asserted.

- A vitest suite for the SPA (`tests/frontend/`), and `npm test` now runs it
  before the node smoke test. `vitest.config.js` already pointed at
  `tests/frontend/**/*.test.js`, but that directory did not exist, so
  `npx vitest run` exited 1 with "No test files found" and the CI
  `frontend-test` job only ever ran a `1 + 1 === 2` placeholder. The first
  spec covers modal lifecycle and the folder picker's auth path.

### Fixed

- `trakt._extract_imdb_ids_from_page` accepts only non-empty strings as an
  IMDb ID. The deduplication check `imdb_id not in seen` ran before any type
  check, so an object or a list in `ids.imdb` raised
  `TypeError: unhashable type: 'dict'`. That exception is not in the sync layer's per-group
  `except` tuple, so a single malformed Trakt entry aborted the entire run
  instead of failing one group. A numeric value is now skipped too: it would
  never match Jellyfin's string provider IDs. Surrounding whitespace is
  trimmed so `" tt0111161 "` still matches.

- `tmdb._collect_tmdb_ids_from_page` skips a non-scalar `id`. A malformed item
  carrying an object or a list became the provider id `"{'a': 1}"` via
  `str()`, which was then looked up in the library (never matching) and
  written into the group's stored ID list.

- `mal.fetch_mal_list` bounds its pagination and refuses to follow a foreign
  next-page URL. The walker followed `paging.next` with no page cap, so an
  upstream that kept returning a next URL looped forever and the sync run
  never finished. It now stops at the shared 50-page safety cap with a
  warning that matches the other fetchers. A next URL is followed only when
  it is HTTP(S) on `api.myanimelist.net`; previously any host was requested
  with the user's MAL client ID in a header, which turned a malformed or
  tampered body into a request-forgery primitive.

- `mal.fetch_mal_list` validates the username before building the request
  URL. Mal names are letters, digits, `-` and `_`. The value was pasted
  straight into the path, so `"../../admin"` produced
  `/users/../../admin/animelist` and escaped the `/users/` prefix.

- `tmdb._normalize_tmdb_list_id` reads the list ID from the correct path
  segment. A real TMDb list URL is rendered as
  `https://www.themoviedb.org/list/8204231/my-list-name`, and the previous
  implementation took the *last* segment, so a correctly pasted URL sent the
  human-readable slug to `api.themoviedb.org/3/list/<slug>` and the group
  failed with a 404. The URL's host is now checked against `themoviedb.org`
  and its subdomains instead of a substring test on the raw input, so
  `https://evil.example/themoviedb.org/list/123` is rejected rather than
  fetched. A bare numeric ID and a scheme-less `themoviedb.org/list/<id>`
  still work; a whitespace-only value is reported as a missing ID instead of
  being requested as `/list/`.

- `trakt._parse_trakt_list_url` resolves a URL by its host and path instead
  of searching the whole input. The old regex matched
  `trakt\.tv/users/([^/]+)/lists/([^/?#]+)` anywhere in the string, so
  `https://evil.example/?u=trakt.tv/users/jane/lists/my-list` was accepted
  and the sync queried the Trakt API for `jane`'s list. Only `trakt.tv` and
  `www.trakt.tv` are accepted now, with the username and slug read from the
  path. The Markdown-link form (`[text](url)`, as pasted from a chat client),
  the scheme-less `trakt.tv/users/...` form, and the `username/list-slug`
  shorthand — including usernames containing a dot — keep working.

- List identifiers supplied through a group's `value` are now validated as a
  whole instead of being pattern-matched anywhere inside the string.
  `imdb.fetch_imdb_list` searched the entire input for `ls\d+`, so a typo such
  as `ls123abc` or `garbage-ls123` was silently truncated to `ls123` and the
  sync fetched a *different* list than the one the user named, with no error
  to show for it. A bare `ls\d+` ID or a URL whose host is `imdb.com` /
  `www.imdb.com` / `m.imdb.com` and whose path contains `/list/ls\d+` is
  accepted; everything else raises `ValueError` before any request is made.

- `letterboxd.fetch_letterboxd_list` validates the list host properly. The
  check was `"letterboxd.com" in list_url`, so
  `https://evil.example/?r=letterboxd.com` and
  `https://letterboxd.com.evil.tld/...` were accepted and the server then
  fetched pages from that host — a request-forgery primitive driven by
  `config.json`. The URL must now be HTTP(S) on `letterboxd.com` or a
  subdomain of it. Scheme-less input such as `letterboxd.com/user/list/x`
  still works and gets `https://` prepended.

- `tmdb.fetch_tmdb_list` and `anilist.fetch_anilist_list` treat a response
  body that is not a JSON object as a failed fetch instead of crashing. Both
  called `.get()` on the decoded body, so a bare list or a string body from
  the upstream API raised `AttributeError`, which the sync layer's per-group
  handler does not catch; one malformed page aborted the whole run rather
  than failing that single group. TMDb now reports the shape from
  `_fetch_tmdb_page` as `TypeError` and converts it in `fetch_tmdb_list`;
  AniList raises `RuntimeError` directly — the type every caller handles.
  `tmdb._fetch_tmdb_page` also converts a JSON decode error to
  `RuntimeError`, matching the other fetchers' error contract.

- External list fetchers no longer crash on a malformed response body.
  `tmdb.get_tmdb_recommendations` turned a result with no `id` into the
  literal TMDb id `"None"` and passed it to Jellyfin; `tmdb.fetch_tmdb_list`
  read `total_pages` without a type check, so a string ended pagination after
  page 1, and non-object `items` raised `AttributeError`; `mal.fetch_mal_list`
  raised `AttributeError` on a non-object payload or a non-dict entry and
  requested a non-string `paging.next` as a URL; `anilist.fetch_anilist_list`
  let a JSON decode error escape as `ValueError`; and `trakt.fetch_trakt_list`
  let the page parser's `TypeError` escape as-is. All of these now skip the
  unusable data or raise `RuntimeError`, the type the callers handle.

- Boolean IDs are rejected in `anilist.py` and `tmdb.py`. `bool` subclasses
  `int`, so `"mediaId": true` was collected as media ID 1 and `"id": true`
  became TMDb id `"True"`.

- `imdb.fetch_imdb_list` validates the list ID properly. The old
  `startswith("ls")` check accepted `ls` and `lsabc`, and both were pasted
  into the request URL only to come back empty or as an error page.

- `imdb.fetch_imdb_list` uses the shared 50-page safety cap and logs a
  warning when it truncates. It previously stopped at 20 pages silently —
  about 2 000 films — while the README promised a 50-page cap for every list
  source.

- Letterboxd lists longer than one page are no longer silently truncated to
  their first 72 films. The page loop tested for the literal
  `class="next"`, but Letterboxd renders the next-page control with a trailing
  space (`class="next "`) and adds state classes to it
  (`class="next  is-disabled"`), so the test never matched and every list
  appeared to end on page 1. The check now splits the `class` value into
  tokens, treats a disabled control as the real end of the list (so the last
  page is not requested twice), and ignores lookalikes such as
  `class="next-door"`. The page cap is shared with the other list fetchers
  (50) instead of the previous 10 (about 720 films), and reaching it now logs
  a warning, because the result is truncated rather than complete.

- `auto_group.py` no longer crashes on the regex patterns it invites users to
  configure. `extract_base_title` called `match.group(1)` unconditionally, so a
  pattern without a capture group (`^Star Wars`) raised `IndexError`, and a
  pattern whose first branch did not match (`^(\d{4})|(.*)$`) raised
  `AttributeError` on the resulting `None`. One bad entry in the `PATTERNS` list
  aborted the whole run. The first participating group is used now, falling
  back to the whole match, matching how
  `jellyfin_auto_groupings.client._matched_group_name` already behaved.

- `auto_group.py` config values are validated after the JSON file is merged.
  `MIN_GROUP_SIZE=abc` raised `ValueError` during import, before the CLI could
  print anything; a `MIN_GROUP_SIZE` below 1 made every item its own group; and
  `"DRY_RUN": "false"` in a config file stayed truthy because a non-empty
  string is truthy, silently keeping a run in dry-run mode. Non-numeric values
  fall back with a warning, values below 1 clamp to 1, `DRY_RUN` is parsed as a
  boolean, and a non-list `PATTERNS` falls back to the defaults.

- `auto_group.py` skips items whose `Name` is `null` or blank instead of
  merging them all into one unnamed `""` collection, and drops unusable item
  IDs before building a request. Jellyfin rejects an entire collection when one
  ID in the `Ids` list is unusable, so a run that contained a single corrupt
  entry used to fail the whole group.

- The `auto_group.py` `--help` epilog no longer advertises
  `python -m jellyfin_auto_groupings.cli --config myconfig.json`: that module
  has no `--config` flag (the flag belongs to `auto_group.py` itself), so
  following the documented example failed with an argparse error.

- Complex-query parsing no longer turns operator typos into filter values that
  silently match nothing. `parse_complex_query` split the query on
  whitespace-delimited operators and treated whatever remained as a value, so
  `AND Action` became the genre `"AND Action"`, `Action AND AND Comedy` became
  the genre `"AND Comedy"`, and `Action AND NOT OR Comedy` became `"OR Comedy"`.
  Each one previewed as zero results with no error, which read as "this group
  matches nothing" rather than "your query is malformed". Operators are now
  tokenised separately from values: a leading or trailing operator is dropped,
  stacked operators collapse to the one nearest the operand (never dropping a
  `NOT`, so the filter is not inverted), and stacked `NOT`s toggle so
  `NOT NOT Comedy` is just `Comedy`. A query carrying no operand at all
  (`NOT`, `genre:`, `AND`) returns no rules instead of an empty-valued rule.

- The duration, file-size, and bitrate formatters no longer emit
  `"1.0m 30.599999999999994s"`, `"nan B"`, or `"inf TB"`. They accepted
  `int | float` and formatted with `//` and `%`, so a fractional second
  survived into the string as floating-point noise, and `NaN` / `Infinity`
  from a partially scanned item passed the `> 0` guard and were rendered
  literally. Non-finite, non-numeric, and `bool` inputs now read as unset, and
  fractional seconds are truncated so a duration never claims a second that
  has not elapsed. `truncate_text` with a non-positive width also returned a
  prefix of the input (a negative slice) instead of an empty string.

- A non-ASCII `APP_PASSWORD` no longer makes every authenticated request
  fail with HTTP 500. `_check_auth` compared the supplied password with
  `hmac.compare_digest` directly, and that raises `TypeError: comparing
  strings with non-ASCII characters is not supported` for `str` arguments
  outside ASCII. An operator who set `APP_PASSWORD=pässwort` locked
  themselves out of the entire UI. Both sides are now UTF-8 encoded first,
  which keeps the comparison constant-time and byte-exact.

- The folder picker no longer shows "HTTP 401" for every directory when
  `APP_PASSWORD` is set. `browseDir` used a bare `fetch()`, which omits the
  Basic-Auth header the shared API client attaches, so the one control that
  needs credentials to be useful was the only one that never sent them. It
  now goes through `browsePath`/`apiGetSilent`, and reports the server's
  message (`403 Access to this path is not permitted`) inline instead of
  stacking an error dialog over the picker.

- Closing a dialog with its `×`/Cancel button no longer leaves the page
  scroll-locked. The `.close-modal-btn` handler set `display: none` directly
  instead of calling `hideModal()`, so `body.modal-open` — which applies
  `position: fixed` below the mobile breakpoint — was never removed and the
  page could not be scrolled until reload. The closed dialog also kept
  `aria-hidden` unset, leaving it exposed to screen readers.

- Letterboxd list imports no longer fall back to one HTTP request per film.
  `_extract_ids_from_list_page` matched a film's slug and its TMDb/IMDb ID
  with a non-DOTALL `.*?` across the whole page. Real Letterboxd markup wraps
  a single film's attributes over several lines, so those patterns never
  matched and every film was re-fetched from its detail page, making a list
  import N+1 requests and prone to rate limiting. The page is now split into
  per-film segments and each segment is scanned on its own, which also stops a
  film without an ID from inheriting the next film's ID.

- A malformed entry inside `groups` no longer aborts the whole sync run.
  `run_sync` called `.strip()` on `groups[].name` and used `sort_order` and
  `source_type` directly as dict keys and set members, so `"name": 42` raised
  `AttributeError` and `"sort_order": ["SortName"]` raised
  `TypeError: unhashable type: 'list'`. Either one turned `POST /api/sync` and
  every scheduled sync into an HTTP 500 (or a silently dead background job) for
  *all* groups, not just the broken one. Those fields now yield a per-group
  result with an `error` for the offending entry while the remaining groups
  still sync. `null` and absent values keep their previous defaults.
- `POST /api/grouping/preview` returns `400` instead of `500` when
  `watch_state` or `item_type` is not a string. Both were read straight from
  the JSON body and `.strip()`ed, so `{"watch_state": 42}` raised
  `AttributeError` and the whole preview failed. A non-string
  `anilist_api_url` in a hand-edited `config.json` is now ignored with a
  warning rather than crashing the same route.
- A hand-edited `groups` value of the wrong type no longer crashes the web UI
  or silently disables every scheduled sync. `_fill_defaults` only replaces a
  stored value when the *default* is a dict, so `"groups": null` (or `42`,
  `"text"`, `true`, `{}`) survived loading untouched and then failed in the
  callers that iterate it. `GET /api/health` raised `TypeError: object of type
  'NoneType' has no len()` from `len(config.get("groups", []))`, and
  `GET /api/cleanup` raised `AttributeError: 'NoneType' object has no
  attribute 'get'` from `g.get("name")`. Both surfaced as HTTP 500 for the
  whole page even though the rest of the config was valid. `load_config` now
  coerces list-valued top-level sections back to their defaults and drops
  `groups` entries that are not objects, logging a warning with the count so
  the bad line stays findable. The file on disk is left unchanged, matching the
  existing repair-on-read behaviour for missing keys.

### Changed

- `jellyfin_auto_groupings.cli.main` now returns its exit code on every
  failure path instead of calling `sys.exit(1)` in some branches and returning
  `1` in others. The docstring already promised a return code, so callers that
  invoked `main()` in-process had to handle both behaviours. `argparse` usage
  errors are converted the same way, so a missing option value returns `2` and
  `--help` returns `0` rather than raising `SystemExit`. The `python -m` guard
  still forwards the code to `sys.exit`, so process exit statuses are
  unchanged.

### Fixed

- Groups sorted by `Random` now come out in a random order. `Random` is
  offered in the UI sort dropdown, but `sync._sort_items_in_memory` looked it
  up in `SORT_MAP` and then sorted on an item field named `Random`, which no
  Jellyfin item has. Every item therefore took the "missing field" branch and
  the input order was returned unchanged, so the option silently did nothing
  for external-list groups (IMDb, Trakt, TMDb, AniList, MyAnimeList,
  Letterboxd, recommendations). It now shuffles the resolved list.
- In-memory sorting no longer raises on mixed value types. A Jellyfin response
  can report the same field as a float for one item and a string for another
  (`CommunityRating` of `8.1` versus `"7.5"`), and `sorted()` raised
  `TypeError: '<' not supported between instances of 'float' and 'str'`,
  which aborted the whole group instead of ordering it. Values are now
  normalised before comparison: numeric strings sort numerically, text sorts
  case-insensitively the way Jellyfin orders `SortName`, and items missing the
  sort field always land at the end in both directions (previously a
  descending sort on a mixed field could place unrated titles first).
- In-memory sorting now applies the secondary key from `SORT_MAP`. Entries
  such as `"ProductionYear,SortName"` only ever used `ProductionYear`, so
  titles from the same year kept whatever order Jellyfin happened to page
  them in. Ties now break in name order, and each key keeps its own direction
  (`"Descending,Ascending"` means newest year first, names A-to-Z within a
  year).
- `config.load_config` no longer crashes when `config.json` is valid JSON but
  not an object. A file containing `[]`, `"text"`, `null` or `42` parsed fine
  and then raised `TypeError: list indices must be integers or slices, not
  str` from `_fill_defaults`; only `json.JSONDecodeError` was handled, so the
  failure escaped every endpoint that loads the config, including app startup
  and the scheduler. Such a file is now quarantined to
  `config.json.corrupt.bak` (unchanged, so the original stays inspectable)
  and defaults are returned, matching the existing invalid-JSON recovery.
  The backup logic is shared with that path via `_quarantine_broken_config`.
- `sync_groupings` no longer sends unusable item IDs to Jellyfin. It built its
  `Ids` list with `str(item["Id"]) for item in items if "Id" in item`, so an
  item whose `Id` was present but `None` or `""` contributed the literal
  strings `"None"` and `""`. Jellyfin rejects the whole `Ids` parameter when
  one entry is invalid, so a single malformed item blocked collection creation
  for every item in the group. Such items are now skipped, matching the guard
  the prefix-grouping paths of `process_groupings` and `create_groupings`
  already applied. `min_items` is now measured against usable IDs, so a group
  that shrinks below the threshold after filtering is not created (previously
  it was created with the remaining valid items only by luck of ordering).
- `utils.helpers.parse_media_tags` no longer raises `AttributeError` on
  non-string tag entries. Jellyfin returns `null` for empty tag lists and can
  include non-string values, which `tag.strip()` rejected; those entries are
  now skipped, which is what `rules.group_by_tag` and
  `client.group_movies_by_tag` already did.
- A malformed `config.json` section no longer crashes the app. Because
  `config.json` is user-editable and `POST /api/config` takes untrusted JSON,
  `"scheduler": null`, `"groups": "text"`, or a numeric cron value used to
  raise `AttributeError`/`TypeError` from `.get()`, `.strip()`, or iteration.
  Through the API that surfaced as an HTTP 500 instead of the expected 400,
  and on startup it aborted `update_scheduler_jobs()`, so the scheduler came
  up with no jobs. `_validate_cron_expressions` now walks both sections
  defensively and `validate_cron` reports non-string input as a validation
  error; `update_scheduler_jobs` logs and skips wrong-typed sections, and a
  non-list `global_exclude_ids` is normalised to an empty list instead of
  being handed to the job.
- `JellyfinClient.create_collection` turned an empty response body into
  `{"Id": "None"}`: `_post` returns `None` for a bodyless success, and the
  fallback wrapper stringified it. Jellyfin answers `POST /Collections` with no
  body in some versions, so callers received a collection whose id was the
  literal text `None`. A missing body now yields `{}`.
- The prefix-grouping paths in `process_groupings` and `create_groupings`
  collected `item.get("Id", "")`, so an item with no `Id` contributed an empty
  string to the `Ids` parameter and Jellyfin rejected the whole collection.
  Items without a usable id are skipped, and a group whose usable ids fall
  below the size threshold is no longer created.
- Mode 1 of `process_groupings`, which re-sorts items inside existing
  collections, read each item's id with `item.get("Id")` without validating
  it. An item missing `Id` therefore produced a write to `/Items/None`, which
  Jellyfin rejects with a 404; the exception escaped `update_item_sort_name` and
  aborted the sort pass for every item and collection after it. Such items are
  now skipped while still consuming their position, so the following sort names
  keep numbering without gaps. This matches the guard the prefix-grouping paths
  already applied.
- `config.load_config` returned a config whose nested containers aliased
  `DEFAULT_CONFIG`: the returned dict was a shallow copy, so the `scheduler`
  dict and the `groups` list were shared with the module-level defaults. Any
  caller that mutated the returned config (for example toggling a scheduler
  flag or appending a group) silently rewrote the process-wide defaults for
  every later load. Defaults are now deep-copied on the missing-file,
  corrupt-file, and unreadable-file paths.
- `utils.helpers.parse_media_tags` docstring claimed the result was sorted,
  but the implementation keeps first-seen order while deduplicating
  case-insensitively. The docstring now describes the real behaviour.
- `utils.formatting.truncate_text` had an unreachable `available <= 0` guard:
  the earlier `max_width <= len(suffix)` check already returns in that case.
  The dead branch is removed and the remaining arithmetic is documented.
- `Makefile`: the `test-fast` target listed five test files
  (`tests/test_config.py`, `test_cleanup.py`, `test_scheduler.py`,
  `test_network.py`, `test_sync.py`) that no longer exist, so `make test-fast`
  failed immediately with "file or directory not found". It now runs the
  `tests/` directory with the slow/exhaustive suites ignored.
- `client.update_item_sort_name` now calls `raise_for_status()`. Previously a
  rejected update (for example HTTP 401 or 404) was reported as success, so
  every item looked re-sorted while Jellyfin kept the old order.
- `get_movies_by_query`, `group_movies_by_tag`, and `group_movies_by_genre`
  no longer raise `TypeError`/`AttributeError` when Jellyfin returns
  `"Tags": null`, `"Genres": null`, or non-string entries inside those lists;
  unusable values are skipped.
- `rules.group_by_tag`, `group_by_genre`, and `group_by_studio` apply the same
  null/non-string filtering, and `group_by_studio` no longer strings unexpected
  values into bogus studio names.
- `process_groupings` no longer raises `TypeError` when a collection item has
  `"PremiereDate": null`, and skips collections that have no `Id` instead of
  querying items with an empty parent ID.
- `process_groupings(..., dry_run=True)` no longer creates collections in mode 2;
  a dry run now leaves the server untouched in both modes.
- `_resolve_release_year` and `rules.group_by_decade` treat `True`/`False` as
  "no year" instead of as release years, and accept whitespace-padded year
  strings.
- `_resolve_release_year` now still falls back to `PremiereDate` when
  `ProductionYear` is present but unusable (for example `"n/a"`).
- `utils.helpers.sanitize_filename` no longer reshuffles `./` prefixes in a
  way that could drop a leading `../../`, and the implementation is a single
  documented pass instead of dead intermediate steps.
- `config.save_config` rotated a timestamped `.bak` file on every save and
  never removed old ones, so a running instance accumulated one backup per
  configuration save (a development checkout had reached 774 backups /
  3.1 MB). The newest `config._BACKUP_KEEP` (5) rotation backups are now
  retained; `.corrupt*.bak` files are left untouched.
- `sync.parse_complex_query` folded a dangling logical operator into the last
  filter value, so `"Action AND NOT"` became a `"not"` genre rule that matched
  nothing and the group silently linked no media. A trailing `AND`/`OR`/
  `AND NOT`/`OR NOT` is now dropped before the query is split.
- `sync._match_year` raised `AttributeError` when a rule's year value was
  `None`, which aborted the entire sync instead of skipping one malformed
  rule. A missing expression now means "no match", and non-string scalars are
  compared by their string form so a numeric rule value still matches.

### Added

- `tests/test_process_groupings_missing_ids.py`: regression tests proving mode
  1 of `process_groupings` never writes a sort name for an item without a
  usable `Id`, that skipped items still consume a position so later sort names
  stay stable, and that a real server error still propagates.
- `tests/test_config_backup_rotation.py`: cover backup retention (cap
  enforced, newest kept, `.corrupt*.bak` and unrelated files preserved, and a
  pruning failure not breaking the save).
- `tests/test_complex_query_edge_cases.py`: cover complex-query parsing
  (operators, negation, typed prefixes, dangling operators, operator-like
  words such as "Rock" or "Thunder") and `_match_year` on malformed input.
- `tests/test_config_defaults_isolation.py`: regression tests proving
  `load_config` never aliases `DEFAULT_CONFIG` on the first-run, repeated-load,
  and corrupt-file paths, and that mutations to a returned config do not leak
  into the defaults.
- `tests/test_utils_extended.py`: cover the height-based resolution fallbacks,
  the exact-suffix-length `truncate_text` boundary, whitespace/punctuation-only
  `slugify` inputs, year-month and bare-year `format_release_date` forms, and
  the first-seen ordering of `parse_media_tags`.
- `tests/test_null_field_robustness.py`: regression tests for `null` tag,
  genre, studio, and premiere-date metadata, boolean production years,
  collections without an `Id`, dry-run collection creation, and HTTP error
  propagation from `update_item_sort_name`.

### Changed

- Untracked committed runtime artifacts that `.gitignore` already excludes:
  leftover dispatcher marker files (`marker_*`) and the `venv3/lib64`,
  `venv4/lib64` virtualenv symlinks. The files stay on disk; only the git
  tracking is removed.
- `rules.parse_grouping_rules` returns `{}` when `collections` is present but
  is not a mapping, instead of returning the non-mapping value.

### Added

- CLI: `--url` falls back to `$JELLYFIN_URL` (falling back to the
  `http://localhost:8096` default when the variable is unset or empty) and
  `--api-key` falls back to `$JELLYFIN_API_KEY`. Keeping the key in the
  environment rather than on the command line avoids leaking it through shell
  history and process listings.
- CLI: a missing API key is now reported as a clear error on stderr with exit
  code `1` instead of `argparse`'s usage dump, and the successful-run summary
  distinguishes dry runs from applied syncs.
- `tests/test_package_coverage_gaps.py`: 58 new tests covering previously
  untested error paths and branches across the migrated package modules
  (HTTP plumbing in `client._get`/`_post`/`_delete`, CLI argument-validation
  and request-failure exits, tag/genre grouping min-size filters, both
  `process_groupings` modes, legacy-module library fetch / sort-name failure
  branches, loader-failure fallbacks in `jellyfin_groupings/__init__`, and
  the `jellyfin_groupings.main` `__main__` guard).
- `tests/test_package_coverage_gaps.py`: tests for the CLI environment-variable
  fallbacks, the explicit-flag override, the blank-`$JELLYFIN_URL` case, and
  both summary strings.

### Changed

- Coverage ratchet raised from `--cov-fail-under=44` to `46` in the Tests
  workflow; package modules `client.py`, `rules.py`, `cli.py`, and
  `__init__.py` are now at or near 100% line coverage under the standard
  test job.

### Security

- `routes.py`: the HTTP Basic Auth password check in `_check_auth` now uses
  `hmac.compare_digest` instead of a plain `==` string comparison. A plain
  comparison short-circuits on the first mismatching byte, leaking the
  password length and prefix through response timing; `compare_digest` runs
  in constant time, closing that timing side-channel.

### Fixed

- CLI: the `--pattern` help text rendered a mangled default (`^( .* )`,
  followed by a stray trailing clause); it now reads as the actual default
  `^(.*)`.
- `_common.py`: `normalize_group_relpath` now rejects Windows drive-letter
  absolute paths (e.g. `"C:\\foo"` or `"C:/foo"`). Previously these were
  normalised into a *relative* path rooted at a literal `"C:"` segment,
  silently creating a confusing `C:` folder inside the target directory
  instead of the intended location. A bare `"C:"` and names with a colon
  inside a single segment (e.g. `"a:b"`) are still accepted as valid
  relative names. `tests/test_common.py` updated to cover the rejection.

- `_common.py`: the Windows drive-letter rejection in
  `normalize_group_relpath` now only matches ASCII `[A-Za-z]` drive
  letters. Previously any Unicode letter (e.g. `"Ä:"`, `"é:"`, `"Ω:"`)
  followed by a colon was also rejected, even though Windows drive letters
  are strictly ASCII — such names are valid relative folder names and are
  now accepted again. `tests/test_common.py` updated to cover these cases.

- `routes.py`: the `/api/browse` endpoint now returns a clean `400` (instead
  of an unhandled `500`) when the requested path cannot be resolved — e.g.
  a symlink loop or a malformed path that makes `Path.resolve()` raise
  `OSError`/`RuntimeError`.

- `docs/API.md`: document the `400` error returned by `/api/browse` when a
  path cannot be resolved, keeping the API reference in sync with the
  endpoint's behaviour.

- `tmdb.py`: corrected the `_fetch_tmdb_page` docstring, which described the
  `api_key` parameter as the "Jellyfin API key" when it is in fact the TMDb
  API key (matching `fetch_tmdb_list` and `get_tmdb_recommendations`).

- `sync.py`: out-of-season cleanup for a seasonal group now targets the
  **normalised** group directory, matching how `_process_group` creates it.
  A group name may carry surrounding whitespace or redundant slashes (e.g.
  `" Anime / Action "`); previously the cleanup derived the path from the
  raw name, so it deleted a non-existent directory and left the real
  (normalised) group directory behind when the group went out of season.

- `sync.py`: `_parse_year_int` and `_coerce_year_int` now reject genuinely
  **fractional** year values (e.g. `"2001.5"` or `2001.5`) instead of
  silently truncating them to a whole year.  A rule like `>2001.5` previously
  matched year `2001` (and `"2001.5"` matched `2001` exactly), which could
  produce surprising results from a typo or a malformed API response.
  Whole-number float serialisations (e.g. `"2001.0"`) are still tolerated.
  `tests/test_sync.py` updated to cover the fractional rejection.

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

- `static/js/core/ui.js`: the toast close button now carries a descriptive
  `aria-label` ("Dismiss notification") and an explicit `type="button"`.
  Previously a screen reader announced the raw `×` glyph, which is not a
  meaningful control name (WCAG 4.1.2 Name, Role, Value). The frontend suite
  is now 395 tests (100% statement/function/line coverage, 99.87% branch
  coverage).

- `tests/test_routes.py`: added a test asserting that the password check
  in `_check_auth` is routed through `hmac.compare_digest` (timing-safe)
  rather than a raw equality comparison.

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
  884 to 905 to match the current suite (888 collected + 17 skipped). Previously
  the count had drifted as the suite grew, reporting a stale number to users.

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
