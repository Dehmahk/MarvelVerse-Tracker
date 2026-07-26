# PyInstaller spec for MarvelVerse Tracker.
#
# Build with:
#   pyinstaller packaging/MarvelVerseTracker.spec
# (see packaging/build_windows.bat for a one-command Windows build)
#
# This bundles everything main.py needs at runtime that isn't already
# picked up by PyInstaller's own import analysis: the QSS theme files,
# the Alembic migration scripts + alembic.ini (both read from disk via
# resource_paths.resource_root(), not imported as Python), and the app
# icon. User data (the database, poster cache, logs, settings) is never
# bundled -- see settings/config.py's _default_data_root(), which
# resolves to a proper per-user application-data directory at runtime
# instead.

import sys
from pathlib import Path

block_cipher = None

# Resolve paths relative to this .spec file's own location, not whatever
# directory `pyinstaller` happens to be invoked from.
SPEC_DIR = Path(SPECPATH)
PROJECT_ROOT = SPEC_DIR.parent

added_files = [
    (str(PROJECT_ROOT / "themes"), "themes"),
    (str(PROJECT_ROOT / "database" / "migrations"), "database/migrations"),
    (str(PROJECT_ROOT / "alembic.ini"), "."),
    (str(PROJECT_ROOT / "packaging" / "assets"), "packaging/assets"),
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        # Alembic's migration scripts are loaded dynamically by file path
        # at runtime (see database/__init__.py), not `import`-ed directly,
        # so PyInstaller's static analysis can't discover their own
        # dependencies on its own -- these are what that dynamic loading
        # actually needs at runtime. logging.config specifically is
        # database/migrations/env.py's own import (for fileConfig()), and
        # without this, that dynamic load fails at runtime with
        # "ModuleNotFoundError: No module named 'logging.config'" even
        # though `import logging` on its own works fine.
        "logging.config",
        "sqlalchemy.sql.default_comparator",
        "sqlalchemy.dialects.sqlite",
        "alembic.op",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MarvelVerseTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX compression is a well-documented cause of antivirus false
    # positives on PyInstaller onefile builds -- a compressed/packed
    # executable looks more suspicious to heuristic scanners, and some
    # AV products will quarantine a file out of the onefile bootloader's
    # extracted temp folder *while the app is still running*, which
    # shows up as exactly this: "Failed to load Python DLL" from
    # %TEMP%\_MEI#####\pythonXXX.dll, mid-session rather than at launch.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Windows: no console window behind the GUI. Harmless no-op on
    # platforms where it doesn't apply.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "packaging" / "assets" / "icon.ico") if sys.platform == "win32" else None,
)
