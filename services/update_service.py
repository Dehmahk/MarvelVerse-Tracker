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
import sys
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
    )


def download_update(info: UpdateInfo, destination: Path) -> Path:
    """Stream-download the new executable to `destination`. Unlike
    check_for_update(), this raises on failure -- by the time this is
    called, the user has already seen an "Update available" prompt and
    clicked "Download & Install", so a failure here needs to actually
    reach them, not disappear silently."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(info.download_url, stream=True, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if chunk:
                    f.write(chunk)
    return destination


def apply_update_and_restart(new_exe_path: Path) -> None:
    """Arranges for the running executable to be replaced by
    `new_exe_path` and relaunched, then returns -- the caller is
    responsible for quitting the application immediately afterward
    (e.g. QApplication.quit()); this function does not exit the process
    itself, since owning the app's shutdown sequence isn't this
    service's job.

    Windows-only, and only meaningful for a frozen (PyInstaller) build --
    raises RuntimeError otherwise. Windows won't let a running process
    overwrite its own .exe file while it's still executing, so this
    writes a small batch script that retries copying the new file over
    the old one once a second for up to 15 seconds (comfortably long
    enough for this process to actually exit and release the file
    handle), then relaunches the result and deletes both the downloaded
    copy and itself. That script is launched fully detached
    (DETACHED_PROCESS) so it keeps running after this process exits.
    """
    if sys.platform != "win32":
        raise RuntimeError("Auto-update's replace-and-restart step is Windows-only.")
    if not getattr(sys, "frozen", False):
        raise RuntimeError(
            "Auto-update only applies to a packaged .exe -- running from source, "
            "use `git pull` instead."
        )

    import subprocess
    import tempfile

    current_exe = Path(sys.executable)
    script_path = Path(tempfile.gettempdir()) / "marvelversetracker_update.bat"
    script_path.write_text(
        "@echo off\r\n"
        "setlocal enabledelayedexpansion\r\n"
        "set RETRIES=0\r\n"
        ":retry\r\n"
        f'copy /y "{new_exe_path}" "{current_exe}" >nul 2>&1\r\n'
        "if errorlevel 1 (\r\n"
        "    set /a RETRIES+=1\r\n"
        "    if !RETRIES! geq 15 exit /b 1\r\n"
        "    timeout /t 1 /nobreak >nul\r\n"
        "    goto retry\r\n"
        ")\r\n"
        f'start "" "{current_exe}"\r\n'
        f'del "{new_exe_path}" >nul 2>&1\r\n'
        'del "%~f0"\r\n',
        encoding="utf-8",
    )

    subprocess.Popen(
        ["cmd", "/c", str(script_path)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
