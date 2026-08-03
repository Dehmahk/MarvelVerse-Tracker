"""Extracts one version's section from CHANGELOG.md -- used by
.github/workflows/build-windows.yml to populate the GitHub Release body
with real, human-written notes instead of GitHub's own auto-generated
commit-list summary.

That Release body is what services.update_service.check_for_update()
reads into UpdateInfo.release_notes, which is what actually shows up in
the "Update Available" popup (main_window.show_update_prompt) and the
Settings page's release notes label -- so whatever this script extracts
is exactly what a user sees when prompted to update.

Usage: python packaging/extract_release_notes.py <version> [changelog_path]
Prints the matched section to stdout, or a short fallback message if no
matching section is found (never fails/exits non-zero for a missing
entry -- a release should still publish even if someone forgets to add
a changelog entry for it, just with a plainer body instead of blocking
the whole release).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_DEFAULT_CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
_FALLBACK_MESSAGE = "See CHANGELOG.md for details."


def extract_release_notes(version: str, changelog_path: Path = _DEFAULT_CHANGELOG_PATH) -> str:
    """Returns the body text for `version`'s own "## {version} — ..."
    section (everything after that heading line, up to the next "## "
    heading or end of file), with the heading line itself included.
    Returns _FALLBACK_MESSAGE if the changelog file doesn't exist, or
    has no section for this exact version.

    Matching is intentionally exact on the version number (e.g. "1.3.0"
    must match "## 1.3.0" -- not "## 1.3.0-beta" or "## 11.3.0") so a
    version string that happens to be a substring of another one can
    never match the wrong section. Done as a plain line-by-line scan
    rather than a single regex -- much easier to get right (and to
    verify by reading) than trying to juggle MULTILINE/DOTALL
    interactions for "everything up to the next heading."
    """
    if not changelog_path.exists():
        return _FALLBACK_MESSAGE

    lines = changelog_path.read_text(encoding="utf-8").splitlines()
    heading_pattern = re.compile(rf"^##\s+{re.escape(version)}\b")
    any_heading_pattern = re.compile(r"^##\s+\d")

    start_index = None
    for i, line in enumerate(lines):
        if heading_pattern.match(line):
            start_index = i
            break
    if start_index is None:
        return _FALLBACK_MESSAGE

    end_index = len(lines)
    for i in range(start_index + 1, len(lines)):
        if any_heading_pattern.match(lines[i]):
            end_index = i
            break

    section_lines = lines[start_index:end_index]
    return "\n".join(section_lines).strip()


def main() -> int:
    if len(sys.argv) < 2:
        print(_FALLBACK_MESSAGE)
        return 0

    version = sys.argv[1].lstrip("vV")
    changelog_path = Path(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_CHANGELOG_PATH
    notes = extract_release_notes(version, changelog_path)

    output_path = _output_path_from_env_or_arg()
    if output_path is not None:
        # Written directly with explicit UTF-8 rather than relying on
        # shell redirection -- GitHub's Windows runners default to
        # PowerShell for `run:` steps, whose `>` operator has its own
        # encoding quirks (historically UTF-16LE with a BOM) that could
        # otherwise mangle the em dashes/curly quotes this CHANGELOG
        # actually uses.
        output_path.write_text(notes + "\n", encoding="utf-8")
    else:
        print(notes)
    return 0


def _output_path_from_env_or_arg() -> Path | None:
    import os

    raw = os.environ.get("RELEASE_NOTES_OUTPUT_PATH")
    return Path(raw) if raw else None


if __name__ == "__main__":
    raise SystemExit(main())
