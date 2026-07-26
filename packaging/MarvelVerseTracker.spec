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

# Pull APP_VERSION from version.py itself rather than hardcoding a
# second copy here -- a hardcoded duplicate is exactly the kind of
# thing that quietly drifts out of sync after a few releases.
sys.path.insert(0, str(PROJECT_ROOT))
import version as _version_module

_version_parts = (_version_module.APP_VERSION.split(".") + ["0", "0", "0", "0"])[:4]
_version_tuple = tuple(int(part) for part in _version_parts)

added_files = [
    (str(PROJECT_ROOT / "themes"), "themes"),
    (str(PROJECT_ROOT / "database" / "migrations"), "database/migrations"),
    (str(PROJECT_ROOT / "alembic.ini"), "."),
    # Only the specific runtime asset files, not the whole
    # packaging/assets folder -- packaging/assets/screenshots/ holds
    # README-only documentation images that the running app never
    # displays, and bundling those into the .exe would just bloat it
    # for no benefit.
    (str(PROJECT_ROOT / "packaging" / "assets" / "icon.ico"), "packaging/assets"),
    (str(PROJECT_ROOT / "packaging" / "assets" / "icon.png"), "packaging/assets"),
    # The actual movie/show catalog -- without this, a packaged .exe had
    # no way to ever get real catalog data into a fresh install; only
    # reference data (universes/franchises/genres/achievements) gets
    # seeded by code, the catalog itself has always lived in this one
    # file. See database/__init__.py's _ensure_catalog_database_exists().
    (str(PROJECT_ROOT / "data" / "marvelverse.db"), "data"),
]

# Entirely optional -- the splash screen gracefully skips itself if this
# file isn't present (see main.py), so the spec shouldn't hard-require
# it either.
_splashscreen_path = PROJECT_ROOT / "packaging" / "assets" / "splashscreen.png"
if _splashscreen_path.exists():
    added_files.append((str(_splashscreen_path), "packaging/assets"))

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

# Windows version resource -- without this, Explorer's Properties dialog
# shows every field (File description, File version, Product name,
# Copyright, ...) completely blank.
#
# VSVersionInfo and its related helpers are NOT auto-injected into a
# .spec file's execution namespace the way Analysis/PYZ/EXE are -- they
# need to be explicitly imported from
# PyInstaller.utils.win32.versioninfo. Confirmed the hard way: a real
# Windows build failed with "NameError: name 'VSVersionInfo' is not
# defined" without this import. Both the import and the construction
# below are guarded behind the platform check since this whole module
# is Windows-only and may not even exist to import on other platforms.
_version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    _version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_version_tuple,
            prodvers=_version_tuple,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "Dehmahk"),
                            StringStruct("FileDescription", "MarvelVerse Tracker"),
                            StringStruct("FileVersion", _version_module.APP_VERSION),
                            StringStruct("InternalName", "MarvelVerseTracker"),
                            StringStruct("LegalCopyright", "Copyright (c) Dehmahk"),
                            StringStruct("OriginalFilename", "MarvelVerseTracker.exe"),
                            StringStruct("ProductName", "MarvelVerse Tracker"),
                            StringStruct("ProductVersion", _version_module.APP_VERSION),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

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
    version=_version_info,
)
