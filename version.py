"""MarvelVerse Tracker's own version, and where to check for a newer one.

Bumping this is a two-step release process:
  1. Update APP_VERSION here (and pyproject.toml's version, to match).
  2. `git tag v<APP_VERSION> && git push origin v<APP_VERSION>` -- pushing
     that tag triggers .github/workflows/build-windows.yml, which builds
     MarvelVerseTracker.exe on GitHub's own Windows runners and attaches
     it to a new GitHub Release under that same tag.

services/update_service.py checks GITHUB_REPO's *latest* Release for a
tag newer than APP_VERSION, so the two need to stay in lockstep -- an
untagged commit, or a tag that doesn't match this file, never shows up
as an available update no matter how far ahead of it the actual code is.
"""
from __future__ import annotations

APP_VERSION = "1.3.0"
# When APP_VERSION above was last bumped -- shown in the About section
# alongside the version number itself. Update both together.
APP_VERSION_DATE = "2026-08-03"

# When this project was first created -- shown as-is in the About
# section's Information panel; not meant to change again.
APP_CREATED_DATE = "2026-07-21"

# "owner/repo" -- update this to your actual GitHub username/repository
# once this project is uploaded. Until then (or if left as this
# placeholder), update checks fail closed: they log the failure and
# report "no update available" rather than raising, so a not-yet-real
# repo slug never breaks the app for someone running from source.
GITHUB_REPO = "Dehmahk/MarvelVerse-Tracker"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"

# Placeholders -- fill these in with your actual invite/page links. Left
# as obvious placeholders rather than removed entirely so the About
# section's buttons/build are already wired; they just won't go
# anywhere useful until these are real URLs.
DISCORD_INVITE_URL = "https://discord.gg/your-invite-code"
BUYMEACOFFEE_URL = "https://www.buymeacoffee.com/your-username"

# The exact filename build-windows.yml's PyInstaller spec produces and
# attaches to each Release -- must match packaging/MarvelVerseTracker.spec's
# `name=` and the workflow's upload step for the update checker to find it
# among a release's other assets.
EXECUTABLE_ASSET_NAME = "MarvelVerseTracker.exe"
