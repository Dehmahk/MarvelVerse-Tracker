"""Checks a GitHub repo's latest Release for a newer version of
MarvelVerse Tracker than the one currently running, and (if the user
chooses to) downloads and installs it.

Only meaningful for the packaged .exe distribution -- someone running
from source (`python main.py`) has no single executable for
apply_update_and_restart() to replace; they update with `git pull`
instead. check_for_update() itself is harmless to call either way (it's
just a network request), but the app should only ever surface an
"Update available" prompt when sys.frozen is set (see
controllers.application_controller, which gates this exactly that way).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from version import APP_VERSION, EXECUTABLE_ASSET_NAME, GITHUB_REPO

logger = logging.getLogger(__name__)

_GITHUB_API_TIMEOUT_SECONDS = 10
_DOWNLOAD_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class UpdateInfo:
    """A newer version is available -- everything needed to show the
    user what it is and, if they choose, download it."""

    version: str
    download_url: str
    release_notes: str
    release_url: str
    expected_size_bytes: int | None


def _parse_version(text: str) -> tuple[int, ...]:
    """"v1.2.3" or "1.2.3" -> (1, 2, 3), compared element-wise so 1.10.0
    correctly counts as newer than 1.9.0 (a plain string compare would
    get that backwards). Anything that doesn't contain a recognizable
    number at all falls back to (0,) rather than raising, so a
    malformed or missing tag just always loses the comparison instead
    of crashing the update check."""
    parts = re.findall(r"\d+", text.strip())
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


def check_for_update(
    current_version: str = APP_VERSION, repo: str = GITHUB_REPO
) -> UpdateInfo | None:
    """None if there's no update, the repo isn't configured yet, or the
    check fails for any reason -- this is best-effort and should never
    be able to break app startup or raise into a caller that isn't
    prepared for a network failure. Whatever actually went wrong is
    logged, not swallowed silently."""
    if "/" not in repo or repo.startswith("your-github-username"):
        logger.info("Update check skipped -- version.GITHUB_REPO isn't configured yet.")
        return None

    try:
        response = requests.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            timeout=_GITHUB_API_TIMEOUT_SECONDS,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.exception("Update check failed -- couldn't reach GitHub")
        return None

    tag_name = payload.get("tag_name", "")
    if _parse_version(tag_name) <= _parse_version(current_version):
        return None

    asset = next(
        (a for a in payload.get("assets", []) if a.get("name") == EXECUTABLE_ASSET_NAME),
        None,
    )
    if asset is None:
        logger.warning(
            "Release %s has no %s asset attached -- nothing to download",
            tag_name,
            EXECUTABLE_ASSET_NAME,
        )
        return None

    return UpdateInfo(
        version=tag_name.lstrip("vV"),
        download_url=asset["browser_download_url"],
        release_notes=(payload.get("body") or "").strip(),
        release_url=payload.get("html_url", ""),
        expected_size_bytes=asset.get("size"),
    )


def download_update(info: UpdateInfo, destination: Path) -> Path:
    """Stream-download the new executable to `destination`. Unlike
    check_for_update(), this raises on failure -- by the time this is
    called, the user has already seen an "Update available" prompt and
    clicked "Download & Install", so a failure here needs to actually
    reach them, not disappear silently.

    Verifies the downloaded file's size against what GitHub itself
    reported for this asset before returning -- a network hiccup that
    truncates the download partway through can otherwise produce a
    file that looks superficially fine (it exists, it's non-empty) but
    is actually a broken executable, which wouldn't surface as an error
    here at all -- it would surface later as a mysterious crash on
    relaunch, after the original executable has already been
    overwritten and is gone.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(info.download_url, stream=True, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if chunk:
                    f.write(chunk)

    if info.expected_size_bytes is not None:
        actual_size = destination.stat().st_size
        if actual_size != info.expected_size_bytes:
            destination.unlink(missing_ok=True)
            raise RuntimeError(
                f"Downloaded file size ({actual_size:,} bytes) doesn't match the expected "
                f"size ({info.expected_size_bytes:,} bytes) -- the download was likely "
                "interrupted or corrupted. Try again, or download the update manually "
                "from the GitHub Releases page."
            )

    return destination


def default_download_directory() -> Path:
    """Where a downloaded update lands -- the user's own Downloads
    folder, so it's somewhere they'd actually look for it, alongside
    anything else they've downloaded. Falls back to the home directory
    itself if a "Downloads" folder doesn't exist for some reason (some
    non-standard setups), rather than failing outright."""
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads
    return Path.home()
