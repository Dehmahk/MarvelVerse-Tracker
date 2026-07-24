# MarvelVerse Tracker

## Disclaimer

MarvelVerse Tracker is an unofficial fan-made application created for personal and community use.

This project is not affiliated with, endorsed by, sponsored by, or approved by Marvel Entertainment, LLC or The Walt Disney Company.

Marvel and all related characters, names, logos, and other intellectual property are trademarks and/or copyrights of their respective owners.

This application does not include or redistribute copyrighted Marvel artwork, logos, movie assets, or other proprietary media.

**Attribution:** Movie/TV metadata is retrieved from [The Movie Database (TMDb)](https://www.themoviedb.org/) via its public API, in accordance with TMDb's own attribution requirements — this is separate from, and does not affect, Marvel's rights as described above. This product uses the TMDb API but is not endorsed or certified by TMDb.

A desktop app for tracking your journey through the Marvel Cinematic Universe (and beyond) — browse a filterable library of movies and shows, follow the story in chronological order, log what you've watched, rate and review, unlock achievements, build custom collections, and keep everything in sync with [TMDB](https://www.themoviedb.org/).

Built with Python, [PySide6](https://doc.qt.io/qtforpython/) (Qt for Python), and a local SQLite database — no account, no cloud, no subscription. Your data stays on your machine.

---

## Features

### Library
Browse your entire catalog in four view modes — Grid, Poster, List, or Compact — with filters for universe, franchise, genre, type, status, and your own Watched / Favorite / Wishlist / Skipped flags. Search by title *or* by cast/crew member name. Sort by title, release date, rating, or runtime. Configurable page size.

### Timeline
The full story in chronological order, not release order — grouped by MCU phase (with collapsible sections, plus one-click Collapse All / Expand All) or as one continuous Chronological Order run. Filter by universe. Choose which sagas (documentaries, specials, spin-offs) to leave out of the chronological view.

### Dashboard
Your stats at a glance: a completion ring, progress broken down by Universe or by Phase, top genres you actually watch, a 6-month watch-activity chart, an "Up Next" pick based on where you left off in the timeline, the achievement closest to unlocking, a "Coming Soon" strip with release countdowns, Recently Watched, Top Rated By You, and a spotlight on one of your Collections.

### Project Details
Full details for any movie or show: synopsis, cast & crew, release date, in-universe timeline date, runtime, studio, genres, saga/phase, and its position in the chronological timeline (with Previous/Next quick-nav buttons). Log watches and rewatches, rate on a 0–10 scale, jot notes, and toggle Favorite / Wishlist / Skipped. A "Watch Trailer" button opens the trailer in your browser when one's available.

### Achievements
51 achievements across Bronze, Silver, Gold, Platinum, and Diamond tiers, plus a single Marvelous-tier capstone for unlocking everything else. Sort by tier (grouped into clearly separated sections) or by recently earned.

### Collections
Build your own curated, manually-ordered lists — a rewatch marathon, a personal ranking, whatever you like — separate from the canonical Universe/Franchise groupings.

### "Surprise Me"
Can't decide what to watch? One click picks something random from what you haven't watched yet.

### TMDB Sync & Backups
Pull movie/show data from TMDB with your own free API key, with an optional automatic re-sync schedule. Create, restore, or delete full backups of your entire library and personal data, with an optional automatic backup schedule. Export/import just your personal activity (ratings, watched status, notes) separately from a full backup — handy for moving to a new install.

---

## Getting Started

### Requirements
- Python 3.12 or newer
- A free [TMDB API key](https://www.themoviedb.org/settings/api) (optional but recommended — without one, you can still browse the pre-loaded catalog, but you won't be able to pull in new releases)

### Getting a TMDB API key

TMDB's API is free for non-commercial use like this. Each person running the app needs their own key — see [Is my API key embedded in the program?](#a-note-on-api-keys) below for why.

1. Create a free account at [themoviedb.org](https://www.themoviedb.org/signup) and verify your email.
2. Go to **[Settings → API](https://www.themoviedb.org/settings/api)** and click **Create** (or **Request an API Key** if this is your first one).
3. Choose **Developer** when asked what type of key you need — this is a personal, non-commercial use case.
4. Fill out the short application form. It asks for an application name/URL and a brief description — something like "MarvelVerse Tracker" and "Personal movie/TV tracking app" is fine. There's no review wait; the key is issued immediately.
5. On your API settings page, copy the **API Key (v3 auth)** value — a 32-character string. (Ignore the **API Read Access Token** field further down; that's a different token format this app doesn't use.)
6. In MarvelVerse Tracker, go to **Settings → TMDB Integration**, paste the key into the API Key field, and press Enter or click away — it saves automatically.

Alternatively, set a `TMDB_API_KEY` environment variable before launching the app; it always takes priority over whatever's saved in Settings, which is handy for development or CI without writing a real key to disk.

### A note on API keys

MarvelVerse Tracker doesn't (and won't) ship with a built-in TMDB key — you always need to add your own. A few concrete reasons:

- **It can't actually be hidden.** Anything embedded in distributed code or a compiled executable can be extracted trivially (a `strings` pass over the binary is enough) — there's no way to ship a secret in client-side software and have it stay secret.
- **One shared key would get rate-limited or banned almost immediately.** TMDB API keys are rate-limited per key, not per installation. If everyone running this app shared one key, sync would break for everybody the moment usage crossed TMDB's limits.
- **It's against TMDB's terms** to share a single key across an unknown number of downstream users, and a banned key is banned for everyone using it.

Getting your own key is free and takes about two minutes (see above) — you only have to do it once.

### Run from source

```bash
git clone https://github.com/<your-username>/MarvelVerseTracker.git
cd MarvelVerseTracker
pip install -r requirements.txt
python main.py
```

The app ships with a pre-populated catalog (148 MCU/Marvel Television projects) so there's something to browse immediately. Add your TMDB API key in **Settings → TMDB Integration** to pull in new releases as they're announced.

### Build a standalone executable

```bash
pip install -r requirements-dev.txt   # or just: pip install pyinstaller
pyinstaller packaging/MarvelVerseTracker.spec
```

The executable is built to `dist/MarvelVerseTracker.exe` (Windows) or `dist/MarvelVerseTracker` (macOS/Linux). On Windows, you can also just run `packaging\build_windows.bat`, which installs everything and builds it in one step.

You don't need a Windows machine to produce the real `.exe`, either — `.github/workflows/build-windows.yml` builds it automatically on GitHub's own Windows runners whenever you push a version tag (`git tag v1.0.1 && git push origin v1.0.1`), and attaches the result to a new GitHub Release. This is also what the in-app auto-update check relies on (see below) — one setup step is required before either works:

**Before your first release**, open `version.py` and set `GITHUB_REPO` to your actual `"username/repository"`. Until that's set, the update checker just quietly does nothing (it fails closed rather than erroring), so this is safe to forget temporarily, but updates won't work until it's filled in.

When packaged, your data (database, poster cache, logs, settings) lives in your OS's standard per-user application-data folder rather than next to the executable:
- **Windows:** `%LOCALAPPDATA%\MarvelVerseTracker\`
- **macOS:** `~/Library/Application Support/MarvelVerseTracker/`
- **Linux:** `~/.local/share/MarvelVerseTracker/` (or `$XDG_DATA_HOME` if set)

Running from source (`python main.py`) instead keeps everything in `./data`, `./cache`, and `./logs` right next to the code, for convenience during development.

### Checking for updates

The packaged app checks `GITHUB_REPO`'s latest GitHub Release on startup (in the background — it never blocks the UI) and again anytime you click **Check for Updates** in Settings. If a newer version is out, **Download & Install Update** downloads the new `.exe`, then replaces the running one and relaunches automatically.

A few things worth knowing:
- **This only applies to the packaged `.exe`.** Running from source has nothing for it to replace — Settings will tell you a newer version exists, but the install button only shows up in a packaged build; from source, use `git pull` instead.
- **Releases need a real `MarvelVerseTracker.exe` attached** for the check to find anything — pushing a version tag through `build-windows.yml` handles this automatically; a release created by hand without that asset attached is invisible to the update checker.
- Version comparisons are numeric (`1.10.0` correctly counts as newer than `1.9.0`), read from the release's tag name (`vX.Y.Z`) against `version.py`'s `APP_VERSION` — keep the two in sync when you bump versions (see `version.py`'s own docstring for the release steps).

### Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

---

## Settings

Every setting below saves automatically the instant you change it — there's no separate "Save" button to click. A **Reset All Settings to Default** button at the top of the Settings page puts everything back to how it was on first launch (your library, ratings, watch history, achievements, collections, backups, and TMDB API key are never affected by this — only these preferences).

**Appearance** — Dark/Light theme, accent color, font size (80–150%), Library poster card size (100–240px), and whether interface animations (page-transition fades) are enabled.

**Library & Browsing** — Default view mode (Grid/Poster/List/Compact), default sort, how many projects to show per page, and whether upcoming/announced projects are shown by default.

**Timeline** — Default sort mode (Phase or Chronological Order), and which sagas to exclude from Chronological Order (they still appear under Phase sorting).

**TMDB Integration** — Your API key, a manual "Sync from TMDB" button, and an optional automatic re-sync interval (never / 7 / 14 / 30 days).

**Data & Storage** — Poster cache size and limit, with a one-click "Clear Poster Cache" (never affects your library or personal data).

**Backups** — Create/restore/delete backups on demand, plus an optional automatic backup schedule with configurable interval and how many to retain.

**Notifications** — Achievement-unlock notifications (with an optional sound), and whether routine "Saved"/"Logged" confirmations show in the status bar.

**Personalization** — How ratings are displayed (0–10, 5-star, or thumbs up/down — this only changes the display, you still rate 0–10), date format (MM/DD/YYYY or DD/MM/YYYY), and which page opens first at launch.

**Privacy** — Whether backup deletion asks for confirmation, and a "mask ratings" toggle that hides your ratings everywhere (handy when screen sharing).

**Import / Export My Data** — Export just your personal activity as a portable JSON file, separate from a full backup.

---

## Project Structure

```
main.py                    Entry point
controllers/                ApplicationController -- wires views to services
services/                   Business logic (project_service, timeline_service,
                             achievement_service, collection_service,
                             statistics_service, tmdb_sync_service, backup_service, ...)
models/                     SQLAlchemy ORM models
database/                   Engine/session setup, Alembic migrations, seeding
views/                      PySide6 UI: pages, reusable widgets, themes
settings/                   AppConfig (settings.json) and its defaults
themes/                     Dark/Light QSS stylesheets
tests/                      pytest + pytest-qt test suite
packaging/                  PyInstaller spec, icon, Windows build script
```

## Tech Stack

- **[PySide6](https://doc.qt.io/qtforpython/)** — Qt for Python, the GUI toolkit
- **[SQLAlchemy](https://www.sqlalchemy.org/)** + **[Alembic](https://alembic.sqlalchemy.org/)** — ORM and schema migrations, on SQLite
- **[requests](https://requests.readthedocs.io/)** — TMDB API client
- **[Pillow](https://python-pillow.org/)** — poster image handling
- **[pytest](https://pytest.org/)** + **[pytest-qt](https://pytest-qt.readthedocs.io/)** — test suite

## License

MIT — see [LICENSE](LICENSE).
