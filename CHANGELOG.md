# Changelog

## 1.3.0 — Dashboard Movie/TV split, packaging fixes, and a real catalog bug

Covers everything since 1.1.0 — the versions in between (1.1.1 through
1.2.9) were shipped without individual changelog entries, so this rolls
all of that up alongside the new feature.

### New: Recently Watched, split by Movie / TV Show

A new Dashboard section, separate from the existing combined Recently
Watched list — one panel for the single most recent movie you've
watched or rewatched, and one for the single most recent TV show,
naming the specific episode (season, number, and title) when you've
been tracking episodes for that show. Falls back to just the show's
title if it's only ever been marked watched as a whole. When a show has
both a whole-series watch and per-episode activity, whichever is
actually more recent wins.

### A real, significant catalog bug, found and fixed

The packaged `.exe` never had any way to get the actual movie/show
catalog into a fresh installation — migrations only created empty
tables, and the app's seeding only ever covered reference data
(universes, franchises, genres, achievements), never the catalog
itself. Fixed two ways: the build now bundles the real catalog
database, and a fresh install copies it into place on first run.
Separately, existing installs now automatically pick up any newly-added
catalog projects on every launch (matched by a stable slug) without
ever touching existing projects or any personal data — so an update no
longer means starting your tracking over.

### TMDB sync fixes

- Sync now checks for an existing project with the same title and a
  release date in the same year before creating a new one — TMDB
  itself sometimes carries more than one listing for the same real
  show (e.g. an orphaned "cancelled" placeholder alongside the real,
  released entry), which previously created duplicate catalog rows.
  Deliberately conservative: only exact title matches in the *same
  year* are treated as duplicates, so genuinely different films
  sharing a name across decades are never affected.
- A new "Clean Up Duplicate Projects" tool in Settings for duplicates
  that already exist from before this fix — only ever auto-removes a
  duplicate with zero personal data attached (no rating, notes,
  watched status, watch history, watched episodes, or collection
  membership); anything with real data on it is left completely
  untouched and listed for manual review instead.
- The "Sync Episode Details from TMDB" button now disables itself with
  a clear tooltip when a show isn't linked to TMDB yet (or has no
  season count set), rather than failing silently after a click with a
  status message that's easy to miss.

### Packaging & build fixes

- Fixed a missing `VSVersionInfo` import that broke the Windows build
  entirely — PyInstaller's version-info helpers aren't auto-injected
  into a `.spec` file's namespace the way `Analysis`/`PYZ`/`EXE` are.
- The `.exe` now embeds real version metadata (file description,
  version, product name, copyright), computed from `version.py` so it
  can never drift out of sync with an actual release.
- Set Windows' AppUserModelID at startup and have `MainWindow` set its
  own icon directly rather than only inheriting the application-wide
  default — together these fix a real, reported split where the title
  bar showed the correct icon but the taskbar (while running) didn't.
- The build now only bundles the specific asset files it actually
  needs, not the whole `packaging/assets` folder — documentation
  screenshots no longer bloat the `.exe` for no reason.
- Replaced the old auto-relaunch update mechanism (which required a
  fragile self-replace dance on Windows and was the source of a "Failed
  to load Python DLL" crash) with a simpler, more reliable one: the app
  downloads the new version to your Downloads folder with a clear,
  versioned filename and opens that folder for you, rather than trying
  to replace and restart itself automatically.
- Added a real integrity check on downloaded updates (verifying the
  downloaded file's size against what GitHub reports for the release
  asset) so a truncated/corrupted download is caught immediately
  instead of surfacing later as a mysterious crash after the original
  `.exe` is already gone.

### Documentation

- Added real in-app screenshots to the README (Library, Timeline,
  Dashboard, Project Details, Achievements, Collections, Actor/Director
  Pages).

## 1.1.0 — Content expansion, quality-of-life batch, and hidden achievements

A large batch of work spanning content expansion, new features, bug
fixes, and polish. Grouped by theme rather than narrated turn-by-turn,
given the scope.

### Catalog & Data

- Catalog expanded from 148 to 193 projects: added Fox's full X-Men
  library (with dedicated Original Timeline, Post-Days of Future Past
  Timeline, Deadpool, and Independent Canon franchises), Sony's
  Raimi/Amazing Spider-Man/Venom/Morbius films, the Blade trilogy,
  Ghost Rider, Fantastic Four legacy films, Punisher films, and the
  Marvel Lego Universe shorts. Two new universes (`SpiderVerse
  (Multiverse Canon)`, `Marvel Multiverse (Legacy/Parallel Canon)`) and
  one legacy-comics universe (`Marvel Comics Universe (Earth-616)`).
- Synopsis/genre/studio/cast/crew backfilled for the expansion batch —
  synopses written fresh in original wording (never copied from an
  outside source); cast/crew are factual credits research, not creative
  content. Remaining known gaps (a handful of shorts/specials with no
  confidently-sourceable credits) left honestly blank rather than
  guessed.
- New `Project` fields: `season_count`, `episode_count`,
  `cancelled_date`, `next_season_release_date` (TV only),
  `production_start_date`, and `tmdb_id` conflict protection (see Bug
  Fixes below). The four TV-only fact fields are now hidden entirely on
  movie/short/documentary Project Details pages rather than showing a
  meaningless "—".
- `services/data_integrity_service.py` (new): a read-only audit —
  duplicate title+year, duplicate `tmdb_id`, duplicate slugs, missing
  synopsis/genres/cast/runtime on released projects, and
  franchise/universe assignments where a majority of a franchise's own
  members disagree with the franchise's universe. Triggered from
  Settings → Data & Storage → "Run Data Integrity Check"; never
  modifies anything.

### New Pages & Major Features

- **Calendar** (new sidebar page): a real month-by-month calendar of
  every dated release in the catalog, past and future, with
  Previous/Next/Today navigation and click-through to Project Details.
- **Actor/Director Pages** (new): click any cast/crew name on Project
  Details to see their bio, photo, and every credit in the library
  (cast and crew credits tracked separately), sorted newest first.
  Back-navigation correctly chains Person → Project → wherever the
  project was originally activated from.
- **Episode-level tracking** (new): TV shows get a per-episode watch
  tracker, grouped by season, generated locally from a show's own
  `season_count`/`episode_count` (split as evenly as possible across
  seasons, since there's no real per-season count to draw from) the
  first time its episodes are viewed. Mark individual episodes, or a
  whole season at once.
- **Compare with a Friend** (new): import a friend's exported personal
  data (the existing "Export My Data" format) and see what you've both
  watched, what only you've seen, and what only they've seen, with an
  overlap percentage — read-only on both sides, nothing is merged into
  your own library. Rejects an incompatible/corrupt/missing file with a
  clear message rather than a raw error.
- **"Find on TMDB"** (new): for a project with no linked TMDB entry
  (mostly the expansion batch above, since the automatic sync only ever
  discovers titles under Marvel Studios' own TMDB company id), search
  TMDB directly by title and link the correct result yourself. Pulls
  full details onto the existing project without touching its curation
  fields (universe, franchise, saga, phase, timeline position).
- **TMDB video/trailer sync** (new): `get_movie_details`/
  `get_tv_details` now fetch trailer/teaser data alongside cast/crew;
  a new extraction step prefers an official trailer, then any trailer,
  then an official teaser, then any teaser, and only ever considers
  YouTube-hosted videos.
- **First-launch TMDB onboarding popup** (new): shown whenever no API
  key is configured yet (skipped entirely if the `TMDB_API_KEY`
  environment variable is set) — explains what a key unlocks, warns
  plainly that the app won't run at full capacity without one, links
  directly to TMDB's sign-up and API settings pages, and triggers an
  immediate sync the moment a key is saved. A "don't ask again"
  checkbox persists across launches if declined.

### Trailer Playback (revised)

- The original approach embedded a real player via `QtWebEngine`. This
  was replaced after it failed in a real packaged build badly enough to
  take the "Watch Trailer" button down with it — a native-level failure
  inside a bundled Chromium subprocess isn't something a Python
  try/except can catch or recover from. Replaced with a clickable
  YouTube thumbnail preview (fetched through the same proven, disk-cached
  image loader every poster in the app already uses) with a play-button
  overlay, opening the real video in the browser on click. Zero
  Chromium, zero subprocess, zero native crash surface.

### Achievements

- 10 new hidden ("secret") achievements added under a new Marvelous-tier
  batch: Perfect Order, Déjà Vu, Right on Time, Triple Feature, Quiet
  Completionist, Social Circle, Marathon Runner, The Answer to
  Everything, Renaissance Fan, and Full Circle (86 achievements total,
  up from 76). A hidden achievement's real name/description/icon are
  masked as "???" at the service layer itself (not just hidden in the
  UI) until unlocked, so the secret can't leak through some other code
  path later.
- New `AchievementCriteriaType.HIDDEN_SPECIAL`, dispatched by the
  achievement's own `key` to bespoke Python checks rather than trying to
  force these into the existing generic count/percent criteria types.

### Personalization & Accessibility

- New **Colorblind Friendly** theme (5th theme, alongside Dark, Light,
  Midnight Blue, and Emerald) — audited the app for red/green pairs used
  to convey meaning and found one real one (the sync status "OK"/"Error"
  chips); fixed to a blue/orange pairing distinguishable across
  deuteranopia, protanopia, and tritanopia alike.
- **Poster hover preview**: hovering a card in Grid/Poster view for
  ~500ms shows a larger version of its poster in a tooltip-style popup,
  without navigating away. Lazily created per-card (no extra window
  created for a card that's never actually hovered).
- **"Watched with" field**: an optional note on each watch event (not
  each project) recording who you watched something with — a quick
  prompt appears when logging a watch, shown inline in the watch history
  list.
- **Native OS desktop notifications**: a real system-tray notification
  for anything releasing today (separate from the existing in-app
  "releases in N days" status-bar reminder), on by default, toggleable
  in Settings → Notifications. Gracefully does nothing on a setup with
  no system tray at all.
- **Marvel Fact of the Day**: a new Dashboard section, one fact shown
  per calendar day (deterministic by date, not re-randomized on every
  refresh) from a curated list. Originally 30 entries written from
  general background knowledge; trimmed to 25 after a deliberate
  self-audit removed anything only moderately confident or overly
  specific, since this environment has no way to verify facts against
  an outside source. A visible in-app caveat now says as much ("General
  trivia, not independently fact-checked against an outside source"),
  not just a code comment.
- Timeline's default sort mode changed from Phase to Chronological
  Order.
- Splash screen support (`packaging/assets/splashscreen.png`, entirely
  optional — the app starts normally with no splash if the file isn't
  present).
- New "About" section at the bottom of Settings: GitHub/Discord/Buy Me a
  Coffee links, a keyboard shortcuts reference, a changelog link,
  credits for the libraries this app is built on, and diagnostics tools
  (open the log folder, copy version/OS/Qt info to the clipboard for a
  bug report).

### Bug Fixes

- **`tmdb_id` conflict on Find on TMDB**: TMDB search results for a
  query like "Agent Carter" can surface both a TV series and its own
  tie-in one-shot as separate, similarly-named entries; picking the one
  already linked to a different project used to fail with a raw,
  unhelpful `sqlite3.IntegrityError`. Now checked before saving, with a
  clear message identifying the conflicting project by name.
  Reproduced the exact reported scenario in a dedicated test.
- **Intermittent segfault in the test suite**: a background `QThread`
  (any of `TMDBSyncWorker`/`TMDBSearchWorker`/`TMDBLinkWorker`/
  `UpdateCheckWorker`/`UpdateDownloadWorker`) still running when a test
  function returned could have its completion signal fire against a
  widget pytest-qt had already torn down — landing the crash on
  whichever *next* test happened to run, not the one that actually
  caused it, which made it very hard to pin down. Fixed with a single
  autouse fixture that waits for any of the `QApplication`'s own
  `QThread` children after every test, rather than trying to
  individually audit and mock every path that could spawn one.
- A settings-view test that changed the Timeline sort combo to
  "chronological" silently stopped testing anything real once that
  became the new default (setting a combo to its already-current value
  never fires a change signal) — caught and fixed to toggle to "phase"
  instead.

### Process note

- A `rm -f data/marvelverse.db` intended to reset test-polluted state
  during this batch of work deleted the *entire* real catalog — 193
  hand-curated projects, none of which are reproducible by reseeding
  (only reference data like universes/franchises/genres/achievements
  gets reseeded, not the actual catalog). Recovered in full from the
  most recently delivered build; verified by literally re-extracting
  that zip and counting projects before continuing. No data was
  ultimately lost, but this is flagged here as a reminder that this
  file is precious and copy-first testing (which is now the standing
  practice for anything touching it) exists for exactly this reason.

## 0.11.0 — Milestone 11 complete: Themes and settings

### Added

- `views/styles.py`: rewritten around a small accent-color substitution
  scheme. Qt's QSS dialect has no variables or custom properties of its
  own, so every theme file now uses two plain-text tokens —
  `@ACCENT@` and `@ACCENT_HOVER@` — in place of a hardcoded color, and
  `load_stylesheet(theme, accent_color)` substitutes them at load time.
  `@ACCENT_HOVER@` is derived via a new `_darken_hex()` helper (~12%
  darker per channel) rather than a second hand-picked color, so any
  accent the user chooses gets a correctly-related hover shade instead
  of only the original hardcoded red's ever looking right. Also exports
  `AVAILABLE_THEMES` (currently `[("dark", "Dark"), ("light", "Light")]`)
  so the Settings page's theme dropdown and the loader can never drift
  out of sync on what themes exist. Falls back to an empty stylesheet
  for an unrecognized theme name (Qt's own default look) rather than
  raising, and falls back to the default accent color for malformed
  accent input rather than producing a broken color string.
- `themes/dark.qss`: its sixteen previously-hardcoded `#E62429`
  occurrences and one `#C81E22` (the old hand-picked primary-button
  hover shade) are now the `@ACCENT@`/`@ACCENT_HOVER@` tokens described
  above — purely a mechanical substitution, no visual change at the
  default accent color.
- `themes/light.qss` (new): a full light theme mirroring every one of
  `dark.qss`'s object-name selectors, so every page renders correctly in
  either theme with no page-specific changes needed. A few colors
  (star ratings, unlocked-achievement text, tier badges) use different,
  slightly darker values than their dark-theme counterparts specifically
  for legible contrast against a white/near-white background rather than
  reusing the same hex values verbatim.
- `views/pages/settings_view.py`: new "Appearance" panel — a theme
  dropdown (populated from `views.styles.AVAILABLE_THEMES`) and an
  accent-color swatch button that opens a native `QColorDialog`. Both
  apply live immediately on change: this view mutates
  `AppConfig.theme`/`AppConfig.accent_color` directly and emits
  `appearance_changed()`, the same "owns the live AppConfig instance"
  pattern the TMDB API key field already uses, plus an explicit
  "Save Appearance" button (persists to `config.json`) and a
  "Reset to Defaults" button (reverts both fields, re-applies, and
  saves immediately, since "reset" reads as a decisive action rather
  than a preview). `appearance_changed` is the one signal on this view
  that never reaches `ApplicationController` — applying a stylesheet is
  a pure view-layer concern with no database or service call involved,
  so `views/main_window.py` connects it directly to a handler that
  re-applies `load_stylesheet()` and shows a status message, skipping
  the controller round-trip every other signal on this page goes
  through.
- `tests/test_styles.py` (new): 10 tests covering both themes' accent
  token substitution, the default-accent fallback, a hex color missing
  its leading `#`, an unrecognized theme name safely returning an empty
  string, the two themes producing recognizably different output, and
  `_darken_hex()`'s math and its two fallback paths (non-hex input, and
  a wrong-length hex string like a 3-digit shorthand).
- 8 new tests extend `tests/test_settings_view.py` for the Appearance
  panel: the theme combo/accent swatch reflecting the configured
  values on construction, changing the theme combo updating config and
  emitting `appearance_changed`, choosing a color via a monkeypatched
  `QColorDialog` (both the accepted and the cancelled path), Save
  persisting to disk, Reset restoring defaults, and confirming the
  reset path emits `appearance_changed` exactly once (not doubled by
  the theme combo's own change handler firing during the programmatic
  reset).
- Verified with a headless smoke test: a real `ApplicationController`/
  `MainWindow` were driven end-to-end — switching the Settings page's
  theme dropdown from Dark to Light immediately changed the live
  `QMainWindow` stylesheet, picking a custom accent color immediately
  reflected that exact color in the live stylesheet, "Save Appearance"
  persisted both fields to `config.json`, and "Reset to Defaults"
  correctly reverted the live stylesheet back to the default theme and
  accent.

### Fixed

- Writing `tests/test_styles.py`'s fallback tests caught a real bug in
  an early draft of `_darken_hex()`: a wrong-length hex string (e.g. a
  3-digit CSS shorthand like `#E62`) fell through to producing a
  malformed color string (`"#E62"`) instead of falling back to the
  default accent color, the same way genuinely invalid input already
  did correctly. Fixed before it ever reached a released version.

## 0.10.0 — Milestone 10 complete: Import/export and backups

### Added

- `services/backup_service.py` (new): a "backup" is simply a timestamped
  copy of the whole SQLite database file — no separate backup format
  needed, since the entire app already lives in one file. `create_backup()`
  runs `PRAGMA wal_checkpoint(FULL)` before copying: this database runs
  in WAL mode (`database/connection.py`), so recent writes can still be
  sitting in a `-wal` sidecar file rather than the main database file,
  and a naive file copy could silently produce an incomplete snapshot
  without the checkpoint first. Backups are written to
  `<data_directory>/backups/marvelverse-backup-<timestamp>.db`, with a
  numeric suffix appended on the vanishingly unlikely chance of a
  same-second collision rather than ever silently overwriting an
  existing backup. `list_backups()` returns every backup file, newest
  first, reading size/mtime straight off disk rather than trying to
  parse a timestamp back out of the filename, so a manually-renamed or
  manually-copied-in backup still shows up correctly. `delete_backup()`
  removes one file. `restore_backup()` is the one function in the module
  that touches the database engine's lifecycle directly: disposes the
  current engine (closing every open connection so the file can be
  safely overwritten on every platform, including Windows, where an
  open/locked file can't be replaced), copies the backup over the live
  database file, removes any leftover `-wal`/`-shm` sidecar files from
  the *old* database so a stale one can never shadow the restored data,
  and re-initializes the engine and re-runs migrations via the same
  `database.init_database()` the app calls on normal startup — so the
  running app can keep going immediately afterward without requiring a
  restart.
- `services/data_export_service.py` (new): exports only the user's own
  activity — watched/favorite/wishlist/rating/notes/rewatch counts, the
  full watch history log, and achievement progress — as portable JSON,
  keyed by each project's `slug` rather than its local database id, so
  it's meaningful across installs (a fresh install synced against the
  same TMDB catalog will assign different local ids, but the same
  slugs). Deliberately excludes the canonical catalog itself (title,
  synopsis, cast, poster, ...), since a TMDB re-sync trivially rebuilds
  that any time and exporting it too would only bloat the file without
  protecting anything irreplaceable — this is the one part of the app's
  data model a re-sync can never reconstruct, per the same
  `UserProjectData`/`Project` separation `models/user_data.py` has
  documented since M2. `import_user_data(path)` matches projects by
  `slug` and overwrites matched personal-data fields outright (this is
  an explicit, user-initiated restore/migrate action, not a passive
  background sync); a project with no local match (never synced, or
  synced under a different slug) is skipped and reported by name rather
  than aborting the rest of the import. Watch history entries are only
  inserted if an equivalent one (same project, timestamp, and rewatch
  flag) doesn't already exist, so re-importing the same file twice is
  safe — this comparison is deliberately done in Python against rows
  already loaded from the database, not as a SQL `WHERE` clause:
  SQLite stores `DateTime` columns as text, and a client-supplied
  timestamp (this import) round-trips through a different string format
  than one written by the database's own `server_default=func.now()`
  (e.g. an entry from `log_watch()`), so a SQL-level equality comparison
  between the two can silently miss an otherwise-identical timestamp.
  Achievement progress is merged non-destructively: progress only ever
  moves up (`max(current, imported)`), and an unlock timestamp already
  recorded locally is never overwritten by an imported one. Raises
  `ValueError` (rather than guessing) for invalid JSON, a payload that
  doesn't look like an export, or an unrecognized `format_version`.
- `views/pages/settings_view.py`: two new panels. "Backups" has a list
  of existing backups (filename, date, human-readable size), a "Create
  Backup Now" button, and "Restore Selected"/"Delete Selected" buttons
  (both disabled until a backup is selected, and both requiring an
  explicit `QMessageBox` confirmation before emitting their signal,
  since both are irreversible). "Import / Export My Data" has an
  "Export My Data…" button (opens a native save dialog defaulting to
  `marvelverse-export.json`) and an "Import My Data…" button (opens a
  native open dialog filtered to `*.json`). New signals:
  `backup_requested()`, `restore_requested(str)`,
  `delete_backup_requested(str)`, `export_requested(str)`,
  `import_requested(str)` — the file dialogs themselves are owned by
  this view (a presentation concern, same as the API key text field),
  but every actual backup/export/import operation still goes through a
  signal to the controller, per the existing "views never touch
  services/database directly" rule.
- `views/main_window.py`: re-emits all five new signals and gained
  `set_backups(backups)` / `set_backup_status(message)` /
  `set_import_export_status(message)` passthroughs, following the same
  pattern every other page's `set_*` method already uses.
- `controllers/application_controller.py`: `_refresh_backups()` loads
  the backup list at startup, mirroring every other `_refresh_*`
  method's pattern. `_on_backup_requested()`/`_on_delete_backup_requested()`
  are thin wrappers around the corresponding service calls plus a
  refreshed list. `_on_restore_requested()` and `_on_import_requested()`
  both refresh *every* page afterward (library summary, library page,
  dashboard, timeline, achievements) rather than just the pages a
  single normal action would touch, since either operation can change
  everything in the app at once — restoring swaps the entire database
  out from under the running app, and an import can touch
  watched/rating/rewatch/achievement state for any number of projects
  simultaneously.
- `tests/test_backup_service.py` (new): 9 tests covering backup
  creation (including a real WAL-checkpoint-captures-recent-writes
  check), listing newest-first, restore correctly replacing current data
  and leaving the engine usable immediately afterward (no restart
  needed), restoring a missing file raising `FileNotFoundError`,
  deletion, and the human-readable size formatting.
- `tests/test_data_export_service.py` (new): 11 tests covering
  export skipping untouched projects vs. including anything with real
  signal, watch-history/achievement export, round-trip import by slug,
  reporting skipped/unmatched slugs, safe repeated imports (no
  duplicate watch history), the achievement progress-never-regresses
  and unlock-never-overwritten guarantees, and the three
  `ValueError` validation paths (invalid JSON, wrong shape, unrecognized
  format version). Writing the repeated-import test caught a real bug
  in an early draft of the watch-history dedup check — the SQL-level
  datetime-string-format mismatch described above — which surfaced as
  silent duplicate watch history entries on a second import; fixed
  before it ever reached this changelog entry's final form.
- 11 new tests extend `tests/test_settings_view.py` for the Backups and
  Import/Export panels: population from a tuple of `BackupInfo`,
  selection enabling/disabling the Restore/Delete buttons, confirmed vs.
  cancelled restore/delete (via a monkeypatched `QMessageBox.question`),
  and export/import emitting (or, on a cancelled file dialog, correctly
  not emitting) their signal with the chosen path (via monkeypatched
  `QFileDialog` static methods).
- Verified with a headless smoke test: a real `ApplicationController`
  drove the full lifecycle end-to-end against a fresh seeded database —
  created a project, logged a watch, created a backup, exported personal
  data to JSON, mutated a rating afterward, restored the backup and
  confirmed the mutation was reverted, imported the earlier export and
  confirmed the watched status and watch-history entry came back, and
  deleted the backup — all through the same signal/controller wiring the
  real UI uses, not by calling the services directly.

## 0.9.0 — Milestone 9 complete: Tracking and achievements

### Added

- `services/achievement_service.py` (new): `sync_achievements()` is the
  single entry point. Recomputes `progress_current` for every seeded
  `Achievement`/`UserAchievement` row in one session and unlocks
  anything that newly crosses its threshold, rather than trying to
  incrementally patch individual counters from half a dozen call sites.
  Handles the four criteria types actually used by the seeded
  achievements: `WATCH_COUNT` (distinct watched projects, not total
  watch events), `REWATCH_COUNT` (sum of `UserProjectData.rewatch_count`
  across the library), `RATING_COUNT` (count of rated projects), and
  `UNIVERSE_COMPLETE` (percent of one universe's projects watched,
  unlocking at 100% — `criteria_value` for this criteria type is a
  boolean-ish "must be fully complete" marker, not a percentage
  threshold to compare against directly). `FRANCHISE_COMPLETE` is
  implemented with the identical percent-complete logic for parity,
  though no seeded achievement uses it yet. `GENRE_COUNT` and
  `COLLECTION_COMPLETE` are explicitly left unhandled — progress is
  never touched, never unlocked, and evaluation never crashes on them —
  since Collections isn't a real feature yet
  (`views/pages/collections_view.py` is still a 24-line stub) and
  `GENRE_COUNT`'s exact semantics haven't been decided with the user.
  An already-unlocked achievement is never re-locked even if progress
  later drops (e.g. a TMDB sync adds a new, unwatched project to an
  already-100%-complete universe) — `unlocked_at` is a permanent record
  of a real past accomplishment, not a live gauge. Returns
  `(all_statuses, newly_unlocked_names)`: the achievement names are only
  ever non-empty on the call that actually pushed something over its
  threshold, so a caller can show a "just unlocked" notification exactly
  once instead of re-showing it on every routine refresh.
  `AchievementStatus` (the detached read-model returned for each row)
  exposes `percent_complete` and a criteria-appropriate `progress_label`
  (e.g. `"3 / 25"` for a count-based achievement, `"62% complete"` for a
  universe/franchise one). Results are sorted unlocked-first (most
  recently unlocked at the top), then locked achievements ordered by how
  close they are to unlocking, so the next achievable one is always
  visible near the top.
- `views/pages/achievements_view.py` (new): a real Achievements page,
  replacing the total absence of one. `AchievementsView` renders a card
  grid (reusing `views/widgets/flow_layout.py`, the same responsive
  reflow the Library's grid/poster modes use) of `AchievementCard`
  widgets — icon (a small built-in emoji map keyed off `Achievement.icon`,
  falling back to a trophy for anything unrecognized), name, a
  tier-colored badge (bronze/silver/gold/platinum), description, a
  progress bar, and either an "Unlocked <date>" or remaining-progress
  footer — plus a summary line ("`X of Y unlocked`") and an empty state.
  Takes duck-typed `AchievementStatus` objects via `set_achievements()`;
  never imports the database or services layer directly, per the
  existing rule every other page follows.
- `views/widgets/sidebar.py`: new "Achievements" entry, positioned
  between Collections and Settings specifically so it doesn't shift
  `views/main_window.py`'s existing `_LIBRARY_NAV_INDEX` fallback
  (Dashboard/Library/Timeline keep their original indices).
- `views/main_window.py`: new `achievements_view` page (added to the
  stack in the same order as the sidebar) and a `set_achievements()`
  passthrough, following the same duck-typed-passthrough pattern as
  every other page's `set_*` method.
- `themes/dark.qss`: new styling for achievement cards (a dimmed
  background/border and greyed-out name for locked ones, via a Qt
  property selector — the same `setProperty()`/`[prop="value"]` pattern
  `TimelineMarker`'s watched/unwatched styling already uses), the four
  tier-color badges, and a red/green progress bar (red while locked,
  green once unlocked).
- `controllers/application_controller.py`: `_refresh_achievements()`
  mirrors `_refresh_dashboard_stats()`'s pattern (owns its own
  try/except, logs and swallows failures so an achievements hiccup never
  blocks the rest of a refresh) and is wired into every action that
  could move an achievement's progress: `start()`, the toolbar's manual
  refresh, `_on_user_data_field_changed` (rating/watched/etc. edits),
  `_on_log_watch_requested`, and the success path of `_run_tmdb_sync`
  (a sync can bring in new, unwatched projects that change a universe's
  completion percentage, or simply add more watchable projects). Shows
  a `"🏆 Achievement unlocked: ..."` status-bar message only when
  `sync_achievements()` actually reports something newly unlocked.
- `tests/test_achievement_service.py` (new): 11 tests covering the
  zero-state on a fresh seed, `WATCH_COUNT` counting distinct watched
  projects (not repeat watches), the already-unlocked-achievement
  not-reported-twice guarantee, `REWATCH_COUNT` summing across the
  library via real `log_watch()` calls, `RATING_COUNT` counting only
  rated (not just watched) projects, `UNIVERSE_COMPLETE` unlocking only
  once every project in a universe is watched, the never-relocks
  guarantee after a new unwatched project is added to an already-complete
  universe, the empty/unknown-universe-reads-zero guard, graceful
  handling of an unsupported criteria type, and unlocked-before-locked
  sort ordering.
- `tests/test_achievements_view.py` (new): 7 tests covering the
  zero-state build, rendering cards with the correct unlocked/total
  summary, the empty-state path, rebuilding cleanly on a second
  `set_achievements()` call (no stale cards left over), the locked
  card's progress-label footer, the unlocked card's date footer, and the
  icon-fallback-to-trophy behavior.
- Verified with a headless smoke test: a real `ApplicationController`
  driven end-to-end against a fresh seeded database — confirmed the
  Achievements page renders all 6 seeded achievements, that logging a
  watch on a to-date-unwatched MCU project correctly unlocked both
  "First Steps" and "Universe Unlocked" in the same refresh, that the
  page's summary/card states reflected this immediately, and that the
  new sidebar entry navigates correctly without disturbing the existing
  page indices.

## 0.8.0 — Milestone 8 complete: TMDB API integration

### Added (part 1 — TMDB data layer)

- `settings/config.py`: `AppConfig` gains `tmdb_api_key` (persisted to
  `config.json`) and `tmdb_auto_sync_attempted` (a one-shot flag so the
  Part 2 "auto-sync on first run" behavior only ever fires once, whether
  or not it succeeds). New `resolved_tmdb_api_key()` method is the only
  sanctioned way to read the key for a request: the `TMDB_API_KEY`
  environment variable always wins over the persisted field, so a
  developer/CI box can sync without writing a secret to disk. Both new
  fields load/save correctly on top of the existing `AppConfig.load()`/
  `save()` round trip.
- `services/tmdb_client.py` (new): a small synchronous HTTP layer over the
  TMDB v3 API (`TMDBClient`). Covers `discover_movies`/`discover_tv`
  (paginated, by company id), `get_movie_details`/`get_tv_details` (each
  fetches cast+crew in one round trip via `append_to_response=credits`),
  `search_company`/`search_movie`/`search_tv`, and an `image_url()` helper
  that turns a TMDB-relative path into a full `image.tmdb.org` URL (or
  `None` if the path is absent). A small typed exception hierarchy
  (`TMDBError` base, plus `TMDBAuthError`/`TMDBNotFoundError`/
  `TMDBRateLimitError`/`TMDBConnectionError`) replaces raw `requests`
  exceptions/status codes at the boundary. HTTP 429s are retried with the
  server's `Retry-After` header honored, up to `max_retries`, before
  raising `TMDBRateLimitError`.
- `services/tmdb_sync_service.py` (new): `sync_from_tmdb(api_key, ...)` is
  the milestone's core mapping logic. Resolves "Marvel Studios" to a live
  TMDB company id via `/search/company` (falling back to the well-known
  id only if that search comes back empty — never trusts a hardcoded id
  as the primary source of truth), discovers movies and TV series for
  that company, and upserts `Project`/`Person`/`ProjectCast`/
  `ProjectCrew`/`Genre` rows. Matched by `Project.tmdb_id`/`Person.tmdb_id`
  so re-running is idempotent (updates in place, never duplicates).
  Deliberately never touches `universe_id`, `franchise_id`, `saga`,
  `phase`, or `chronological_order` on an existing project — TMDB has no
  concept of this app's MCU phase/saga/franchise groupings, so those stay
  whatever a human set them to (`NULL` on first creation). Cast/crew are
  fully replaced each sync (capped at 15 cast / 8 crew per project, crew
  filtered to a fixed set of jobs the UI actually shows) since they're
  canonical, API-owned data — but this module never imports, reads, or
  writes `UserProjectData`, so a watched flag, rating, note, favorite, or
  wishlist entry can never be clobbered by a re-sync. Per-item failures
  (e.g. one bad TMDB id) are collected into `SyncResult.errors` instead of
  aborting the rest of the run; a failure resolving the company id or
  fetching a discovery page still propagates.
- `tests/test_tmdb_client.py` (new): 16 tests covering request/param
  shaping, the 401/404/429/5xx/connection-error → exception mapping, the
  429 retry-then-succeed and retry-exhaustion paths, and `image_url()`.
  All mock the HTTP layer directly (a fake `requests.Session`-shaped
  object) — no real network calls.
- `tests/test_tmdb_sync_service.py` (new): 11 tests covering company-id
  resolution (exact match / fallback-to-first / fallback-to-constant),
  movie and TV project creation (including the TV runtime-from-
  `episode_run_time[0]` case and status-string mapping), idempotent
  re-sync (no duplicate rows, cast replaced not duplicated), the
  curation-fields-never-touched guarantee, the
  `UserProjectData`-never-touched guarantee, cross-project person
  de-duplication by `tmdb_id`, and one-bad-item-doesn't-abort-the-sync
  error handling. All inject a duck-typed fake TMDB client — no real
  network calls, and no dependency on `TMDBClient`'s internals.

### Added (part 2 — wiring TMDB sync into the UI)

- `views/pages/settings_view.py`: no longer a static placeholder. New
  "TMDB Integration" panel with a masked (`QLineEdit.EchoMode.Password`)
  API key field pre-filled from `AppConfig.tmdb_api_key`, a Save button
  that writes the key to `AppConfig` and calls `config.save()` directly
  (this view is handed the live `AppConfig` instance, unlike every other
  page, which only ever sees duck-typed service objects), a note that
  the `TMDB_API_KEY` env var always overrides the saved key, a "Sync from
  TMDB" button, and a status label for sync results/errors. New signals
  `tmdb_api_key_changed(str)` and `tmdb_sync_requested()` — the sync
  trigger itself still goes through a signal + the controller, per the
  existing "views never touch services/database directly" rule.
- `views/main_window.py`: keeps a named `settings_view` reference (was
  anonymous), re-emits its two new signals, and gained
  `set_tmdb_sync_status(message)` / `set_tmdb_sync_in_progress(bool)` so
  the controller can push sync feedback into the page without importing
  it directly.
- `controllers/application_controller.py`: handles both new signals.
  `_on_tmdb_api_key_changed()` acknowledges the save in the status bar
  (the key is already persisted by the view itself, and `AppConfig` is
  the same shared instance both objects hold, so `self.config` is
  already current). `_run_tmdb_sync(manual=...)` is the shared sync path
  for both triggers: resolves the key via `resolved_tmdb_api_key()`
  (shows "Add a TMDB API key first." and bails if none is configured),
  disables the Settings-page sync button and shows a busy message for
  the duration (`set_tmdb_sync_in_progress`), calls
  `services.tmdb_sync_service.sync_from_tmdb()` synchronously on the UI
  thread — consistent with every other service call this controller
  already makes — catches `TMDBError` and any unexpected exception
  separately (both logged, both surfaced via `set_tmdb_sync_status`, a
  manual trigger additionally gets a toolbar status message), and on
  success refreshes the library/dashboard/timeline the same way every
  other mutating action in this controller already does.
  `_maybe_auto_sync_tmdb()` runs once at the end of `start()`: skipped
  entirely (and `tmdb_auto_sync_attempted` left untouched) if no key is
  configured yet, so the app still gets one free automatic sync the
  first time a key *is* configured rather than only on literally the
  process's first-ever launch; otherwise runs a sync and sets
  `tmdb_auto_sync_attempted = True` (saved) regardless of outcome, so a
  bad/expired key never retries on every subsequent launch.
- `tests/test_settings_view.py` (new): 9 tests covering the zero-state
  build, pre-filling an existing key, Save persisting to both the
  in-memory `AppConfig` and `config.json` on disk, saving a blank value
  clearing the key, the sync button emitting its signal, and
  `set_sync_in_progress()`/`set_sync_status()`'s effect on the button and
  label.
- Verified with a headless smoke test: a full `ApplicationController`
  wired end-to-end with `services.tmdb_sync_service.sync_from_tmdb`
  mocked out — confirmed the "no key configured" path shows the correct
  status message without crashing, and (separately, with a fake API key
  configured) that `start()`'s one-time auto-sync fires exactly once,
  sets `tmdb_auto_sync_attempted`, and correctly renders
  `SyncResult.summary()` into the Settings page; a subsequent manual
  "Sync from TMDB" click ran a second, independent sync on top of that.

### Added (part 3 — real end-to-end verification and cleanup)

- `tests/test_tmdb_integration_smoke.py` (new): the real end-to-end proof
  that was still missing after part 2. Drives a genuine
  `ApplicationController.start()` with only
  `services.tmdb_sync_service.TMDBClient` swapped for a duck-typed
  `FakeTMDBClient` at the HTTP-client boundary (via
  `patch("services.tmdb_sync_service.TMDBClient", return_value=...)`) —
  the real `sync_from_tmdb()` mapping logic, the real one-shot
  auto-sync-on-first-run gating, and the real
  library/dashboard/timeline refresh path all run exactly as they would
  against a live TMDB API key. Two tests: one confirms the auto-sync
  fires exactly once on `start()`, creates real `Project` rows for a
  scripted movie and TV series, sets `tmdb_auto_sync_attempted`, and
  that those rows are visible via `list_projects()`,
  `get_dashboard_stats()`, and `get_timeline()` immediately afterward;
  the other confirms a manual "Sync from TMDB" triggered *after* the
  auto-sync has already run updates the same two rows in place
  (idempotent, per part 1's `tmdb_id` matching) rather than duplicating
  them. This matches the pattern used to live-verify M7's Timeline, but
  as a permanent, committed pytest test rather than an ad hoc script.
- `scripts/seed_dev_projects.py` **removed**: with a real, tested TMDB
  sync now verified end-to-end, the hand-written dev-data helper that
  filled the Library/Dashboard/Timeline during M1–M7 development is no
  longer needed — decided with the user rather than retired
  unilaterally, per the standing note carried over from part 1 and 2.
- README.md: "Current Status" now reads "Milestones 1–8 are complete";
  the three separate M8 (part 1/2/3) bullets are folded into one closed
  -out M8 entry with Data layer / UI wiring / Verification /
  Dev-seed-script-retired subsections; the "Where the next AI should
  pick up" section is retired (Milestone 9 planning starts fresh
  whenever that milestone begins); the Development Roadmap's item 8 is
  checked off and item 9 (Tracking and achievements) is marked as next.

## 0.7.0

### Added

- `services/timeline_service.py` (new): the Timeline page's data layer.
  `get_timeline(universe_id=None)` returns a tuple of detached
  `TimelineGroup` DTOs (each a `saga`/`phase` pair plus its
  `TimelineEntry` rows), ordered by `chronological_order` first, falling
  back to `release_date` for anything without one, with `title` as a
  final deterministic tiebreak. Projects with neither a
  `chronological_order` nor a `release_date` (e.g. an
  announced-but-undated sequel — `Avengers: Secret Wars` in the seed
  data) still get rendered, sorted to the end, rather than silently
  disappearing. Groups are built in first-appearance order along that
  same sort, so the groups themselves follow the timeline's overall
  chronology instead of being alphabetized. `TimelineEntry` carries the
  same watched/favorite/rating fields from `UserProjectData` the Library
  and Dashboard already surface.
- `views/widgets/timeline_marker.py` (new): `TimelineMarker`, a single
  timeline row reusing the Library row's visual language (poster
  placeholder, title, rating) plus a chronological-order badge and a
  watched/unwatched/favorite indicator. Duck-typed against
  `TimelineEntry`; never imports the services layer.
- `views/pages/timeline_view.py` rebuilt from the M1 placeholder: a
  universe filter dropdown (reusing the same `FilterOptions` the Library
  populates its universe filter from), a scrollable list of saga/phase
  sections each holding its `TimelineMarker` rows, and an empty state for
  when nothing has a chronological order or release date yet. Clicking a
  marker emits the same `project_activated` signal the Library and
  Dashboard already use. Presentation-only, same as every other page.
- `MainWindow` gains a stored `timeline_view` reference (previously added
  anonymously to the page stack and unreachable), wires its
  `project_activated`/`universe_changed` signals, and exposes
  `set_timeline_filter_options()`/`set_timeline_groups()` for the
  controller to push data through — still never imports the database or
  services layer itself.
- `ApplicationController` gains `_timeline_universe_id` state and
  `_load_timeline_filter_options()`/`_refresh_timeline()`/
  `_on_timeline_universe_changed()`, called at startup and everywhere the
  Library/Dashboard refreshes already are (manual refresh, and after any
  watched/favorite/wishlist/rating edit or logged watch), since all of
  those can change how a project's marker looks on the Timeline.
- `tests/test_timeline_service.py` (new): 7 tests covering
  chronological-order-first sorting, the release-date fallback, projects
  with neither sorting last instead of vanishing, saga/phase grouping
  (including a `(None, None)` group for projects with neither set),
  universe filtering, watch-state carrying onto entries, and an empty
  database returning an empty tuple.
- `tests/test_timeline_view.py` (new): 7 headless tests directly against
  `TimelineView` — zero-state on construction, the empty state showing
  for zero groups, sections/markers rendering correctly, stale sections
  being cleared on a second `set_groups()` call, a marker click emitting
  `project_activated` with the right id, and the universe combo
  populating from and emitting through `set_filter_options()`.
- New QSS rules for `timelineGroupHeading`, `timelineMarker` (plus a
  hover state and a dimmed background for unwatched projects, using a
  dynamic `watched` property), `timelineOrderBadge`, and
  `timelineWatchedIndicator`/`timelineUnwatchedIndicator`.
- Verified with a full headless smoke test (`QT_QPA_PLATFORM=offscreen`,
  not committed to the suite, same as prior milestones): a genuine
  `ApplicationController.start()` against a fresh database, seeding a
  project directly and confirming a manual refresh renders it on the
  Timeline, then firing a real `TimelineMarker.clicked` signal and
  confirming it navigates to Project Details and that Back correctly
  returns to the Timeline page. All 72 tests pass (14 new + 58 from
  prior milestones).

### Fixed

- `MainWindow`'s Project Details "Back" button always returned to the
  Library page, even when a project had been activated from the
  Dashboard's "Recently Watched" list (flagged but left unaddressed in
  M6, since Timeline landing was expected to make the gap harder to
  ignore). `show_project_detail()` now records which sidebar-navigable
  page a project was actually activated from, and Back returns there —
  Library, Dashboard, or Timeline.

## 0.6.0

### Added

- `services/statistics_service.py` gains the dashboard data layer:
  `get_dashboard_stats(recent_limit=5)` returns a single detached
  `DashboardStats` DTO with completion percentage, movies-watched vs.
  TV-watched counts (a project counts as "TV" if it's `TV_SERIES`,
  `TV_SPECIAL`, or `ANIMATED_SERIES`; everything else — movies, shorts,
  documentaries — counts as "Movies"), total hours watched (summed
  `runtime_minutes` over every project marked watched, `NULL` runtimes
  contributing nothing rather than poisoning the sum), favorites count,
  and achievements unlocked/total. Achievement counts are wired against
  the real `Achievement`/`UserAchievement` tables from M2, but since
  nothing populates or checks them yet, they correctly read as
  `0 unlocked / N total` rather than being hardcoded — real achievement
  logic is still scoped to a later milestone.
- `DashboardStats.recently_watched` is a tuple of `RecentWatchItem`
  (project id/title/type/poster, watched-at timestamp, rewatch flag,
  rating), built from `WatchHistoryEntry` newest-first — the same table
  M5's `log_watch()` already writes to. A rewatch shows up as its own,
  separate entry rather than replacing the original watch.
- `views/pages/dashboard_view.py` rebuilt from the M1 placeholder:
  `StatCard` gained `set_value()`/`set_subtitle()` so the six cards
  refresh in place instead of being rebuilt from scratch, and a new
  `RecentWatchRow` widget (reusing the Library's row QSS classes) renders
  the "Recently Watched" panel — or the existing empty-state message when
  there's nothing to show yet. Clicking a row emits the same
  `project_activated` signal the Library already uses, so it opens
  Project Details exactly like a library card/row would. Presentation-only
  and duck-typed against `DashboardStats`/`RecentWatchItem`, same as every
  other page.
- `MainWindow.dashboard_view.project_activated` is wired into the
  existing `project_activated` signal alongside the Library's, and a new
  `update_dashboard_stats()` pushes a `DashboardStats` into the page —
  `MainWindow` still never imports the database or services layer.
- `ApplicationController` gains `_refresh_dashboard_stats()`, called at
  startup and everywhere `_refresh_library_summary()` already is (manual
  refresh, and after any watched/favorite/wishlist/rating edit or logged
  watch), since all of those affect the dashboard's numbers too.
- `tests/test_statistics_service.py`: 6 new tests covering the empty-library
  zero-state (including a real achievement-table count, not a hardcoded
  one), the movies/TV split, hours summing safely across a project with no
  runtime, and `recently_watched` ordering (newest-first, rewatches as
  their own entry) and its `recent_limit`.
- `tests/test_dashboard_view.py` (new): 6 headless tests directly against
  `DashboardView` — zero-state on construction, `set_stats()` updating
  every card, the recently-watched panel populating and showing/hiding the
  empty state, a row click emitting `project_activated` with the right
  project id, and stale rows being cleared on a second `set_stats()` call.
- `tests/conftest.py` (new): defaults `QT_QPA_PLATFORM` to `offscreen` so
  the suite runs headlessly without the environment variable being set
  externally — needed now that `test_dashboard_view.py` instantiates real
  `QWidget`s, unlike any earlier test.
- Verified with a full headless smoke test (`QT_QPA_PLATFORM=offscreen`,
  not committed to the suite, same as prior milestones): a genuine
  `ApplicationController.start()` against a fresh SQLite database showing
  the correct zero-state, then seeding a project, logging a watch, and
  confirming a manual refresh updates completion/hours/favorites and the
  "Recently Watched" panel, and that clicking the new row navigates to
  Project Details end-to-end. All 58 tests pass (12 new + 46 from prior
  milestones).

### Fixed

- Caught during development (never shipped): an early draft of
  `get_dashboard_stats()` wrapped a filtered `Project`/`UserProjectData`
  join in a subquery but then aggregated columns from the *unwrapped*
  `Project` table against it, producing an unintended cross join that
  tripled `movies_watched`/`tv_watched`/`total_minutes_watched` on any
  library with more than one watched project. Rewritten to aggregate
  directly off the join instead of through a subquery.

## 0.5.0

### Added

- `services/project_service.py` gains the Project Details data layer:
  `ProjectDetail` (a detached read model with canonical fields, cast/crew
  as `CastMember`/`CrewMember`, and `watch_history` as `WatchHistoryItem`
  entries, newest first) plus `get_project_detail(project_id)`. Personal
  fields (watched, favorite, wishlist, rating, notes, rewatch_count,
  last_watched_date) come from the same optional `UserProjectData` join
  used elsewhere, defaulting safely for projects that don't have one yet.
- `update_user_project_data(project_id, **fields)`: creates or updates a
  project's `UserProjectData` row. Uses an internal `_UNSET` sentinel so a
  field can be explicitly cleared (`rating=None`, `notes=None`) without
  that being indistinguishable from "don't touch this field". Never
  writes to canonical `Project` columns, keeping the existing "API
  refresh can't clobber user data" guarantee intact.
- `log_watch(project_id, notes=None)`: the "Log a Watch" / "Log a
  Rewatch" action. Appends a `WatchHistoryEntry`, marks the project
  watched, stamps today as `last_watched_date`, and increments
  `rewatch_count` if it was already watched. Both new mutators return a
  fresh `ProjectDetail` and raise `ValueError` for an unknown project id.
- `views/pages/project_detail_view.py`: the new Project Details page —
  poster placeholder + status badge, a facts panel (release date,
  runtime, studio, universe, franchise, genres, saga, phase), synopsis,
  an "Your Activity" panel (Watched/Favorite/Wishlist toggles, a rating
  spinner with a Clear button, the Log a Watch/Rewatch button with live
  watch-stats text, and a notes editor with an explicit Save button so
  keystrokes don't spam the database), Cast & Crew columns, and a Watch
  History list. Presentation-only and duck-typed against `ProjectDetail`,
  same as every other page — never imports the database or services layer.
- Library cards/rows were already wired to emit `project_activated`
  (added in M4 but never connected); that signal now actually does
  something: `MainWindow` re-emits it, gained a `project_activated`
  page stack slot for the detail view (reachable only by activating a
  project — it has no sidebar row of its own, and the sidebar stays on
  "Library" as visual "where you came from"), and bubbles the detail
  view's edits back up as `user_data_field_changed` / `log_watch_requested`.
- `ApplicationController` wires all three: on activation it loads the
  detail via `get_project_detail` and shows it; on a field edit or a
  logged watch it persists via `update_user_project_data`/`log_watch`,
  pushes the fresh `ProjectDetail` back into the still-open detail page,
  and also refreshes the library page and status-bar summary in the
  background so watched/rating changes aren't stale if the user goes
  back to Library.
- `models/project.py`: `watch_history` relationship ordering gained a
  secondary sort by `id` (in addition to `watched_at desc`) so two
  watch events landing in the same second — SQLite's `CURRENT_TIMESTAMP`
  is only second-precision — still sort deterministically newest-first.
- New QSS rules for the detail page: `primaryButton` (a solid red action
  button — the first of its kind in the app; every prior button reused
  `secondaryButton`/`iconButton`/`filterToggle`), the poster frame and
  placeholder, fact label/value pairs, the rating spinner, the notes
  editor, and cast/crew/watch-history list rows.
- `tests/test_project_service.py`: 11 new tests covering
  `get_project_detail`'s full shape and its safe defaulting for a
  project without `UserProjectData`; `update_user_project_data` updating
  only the fields it's given, clearing a rating/notes back to `None`,
  creating a missing `UserProjectData` row on first edit, and raising for
  an unknown project id; and `log_watch`'s first-watch vs. rewatch
  behavior, `WatchHistoryEntry` creation, and its own missing-project
  error. All pass alongside the existing 35 (46/46 total).
- Verified with headless smoke tests (`QT_QPA_PLATFORM=offscreen`, not
  committed to the suite, same as prior milestones): one exercising the
  full real chain — a genuine `ProjectCard.clicked` signal fired on a
  card actually rendered by `LibraryView`, through `MainWindow` and the
  controller, landing on a correctly populated detail page; another
  driving every editable control (watched toggle, rating, notes, Log a
  Watch) end-to-end and confirming each change round-trips through
  SQLite and back into the still-open view, including the Log a
  Watch → Log a Rewatch button-label switch and Back navigation
  returning to the Library page. Both passed.

## 0.4.0

### Added

- `services/project_service.py`: the real search/filter/sort/pagination
  engine behind the Library. `list_projects()` takes a `ProjectFilter`
  (search text, universe, franchise, genre, type, status, watched,
  favorite, wishlist — all optional and combinable), a `SortField` +
  `SortDirection`, and a page/page_size, and returns a `PagedResult` of
  detached `ProjectListItem` rows so the view layer never touches a live
  ORM session. Search matches title, synopsis, studio, universe/franchise
  name, and cast/crew member names. `get_filter_options()` supplies the
  reference data (universes, franchises, genres) for the filter dropdowns.
- `views/pages/library_view.py` rebuilt from a placeholder into the real
  thing: dropdown filters (universe, franchise — dependent on the selected
  universe, genre, type, status) plus Watched/Favorites/Wishlist toggles
  and a Clear button; a sort dropdown with 8 presets; four view modes
  (Grid, Poster, List, Compact) via `views/widgets/project_card.py` and
  `views/widgets/project_row.py`; and pagination controls. The view only
  ever emits/receives primitive values and duck-typed result objects — it
  still never imports the database or services layer.
- `views/widgets/flow_layout.py`: a reusable flow layout (Qt has no
  built-in one) so Grid/Poster cards reflow responsively instead of being
  locked to a fixed column count.
- The toolbar's global search box (wired but unconsumed since Milestone 3)
  now drives the Library's search filter through the controller.
- `ApplicationController` now owns all library query state (filters, sort,
  page) and wires every Library/toolbar signal to `project_service`, then
  pushes `PagedResult`/`FilterOptions` back into the view — keeping the
  "views never touch the database or services layer" rule intact.
- New QSS rules for filter chips/dropdowns, the four card/row view modes,
  and the library scroll area.
- `tests/test_project_service.py`: 28 tests covering pagination bounds and
  clamping, every individual filter plus combined (AND, not OR) filters,
  case-insensitive substring search across title/cast/crew/universe,
  every sort field including NULL-handling, and the `ProjectListItem`
  shape for both linked and bare (no `UserProjectData`) projects.
- Verified with two headless smoke tests (`QT_QPA_PLATFORM=offscreen`):
  one exercising the full Library UI end-to-end (search, a filter toggle,
  sort, all four view modes, clear filters), and one specifically
  confirming pagination splits and button enablement across two pages of
  30 seeded projects. All 35 tests pass (28 new + 7 from prior milestones).

## 0.3.0

### Added

- Shell components extracted into reusable, presentation-only widgets:
  `views/widgets/sidebar.py` (`Sidebar`) and `views/widgets/toolbar.py`
  (`MainToolBar`), replacing the inline UI code that used to live in
  `MainWindow`.
- Sidebar can now collapse to an icon-only rail via a toolbar toggle
  button, and the sidebar/content split is a resizable `QSplitter`
  instead of a fixed-width layout, making the shell genuinely responsive.
- Toolbar gained a live page-title label (updates with navigation), a
  global search box (wired up to a `search_changed` signal, ready for the
  Library milestone to consume), and a refresh action.
- Status bar now shows real, live-computed chips: total project count,
  watched count with completion percentage, and a database connection
  indicator, backed by a new `services/statistics_service.py`
  (`get_library_summary()`).
- `ApplicationController` now fetches the library summary once at
  startup and again on every toolbar refresh, and pushes it into the
  window — `MainWindow` and its widgets never import the database or
  services layer directly, keeping the "views never touch the database"
  rule intact end-to-end.
- New QSS rules for status chips, the splitter handle, and the toolbar's
  page-title label.
- `tests/test_statistics_service.py`: summary on an empty library, and
  summary correctness after adding watched/favorited projects.
- Verified with a full headless smoke test (`QT_QPA_PLATFORM=offscreen`)
  exercising navigation, sidebar collapse, live status bar updates, and
  the refresh action end-to-end — not just unit tests of the pieces.

## 0.2.0

### Added

- SQLAlchemy 2.0 ORM models: `Universe`, `Franchise`, `Genre`, `Person`,
  `Project`, `Tag`, `Collection`, `Achievement`, `UserAchievement`,
  `UserProjectData`, `WatchHistoryEntry`, plus association objects
  `ProjectCast`, `ProjectCrew`, and `CollectionProject`.
- Strict separation between canonical `Project` data and personal
  `UserProjectData` (watched, rating, favorite, notes, rewatch count,
  wishlist) so future API sync can never overwrite user records.
- SQLite database wiring (`database/connection.py`) with foreign keys and
  WAL mode enabled on every connection.
- Alembic migrations (`database/migrations/`) with an autogenerated,
  hand-verified initial schema revision (`0001_initial_schema`).
- Idempotent reference-data seeding (`database/seed/reference_data.py`):
  MCU/SSU/Fox-X-Men/classic-TV universes, starter franchises, genres, and
  a first batch of achievements.
- `database.init_database()` now runs on every app startup from
  `ApplicationController`, ahead of the main window being created; a
  failed database init shows an error dialog instead of opening a broken
  window.
- `tests/test_database.py`: migrations create the expected schema, seeding
  is idempotent, relationships round-trip correctly, and a simulated API
  metadata refresh leaves `UserProjectData` untouched.

## 0.1.0

### Added

- Initial MarvelVerse Tracker application shell.
- PySide6 main window.
- Sidebar navigation.
- Dashboard, Library, Timeline, Collections, and Settings views.
- Dark theme.
- Centralized configuration.
- Application logging.
- Initial pytest setup.
