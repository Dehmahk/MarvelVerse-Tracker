@echo off
setlocal

rem Always run from the project root, regardless of where this script was
rem double-clicked/invoked from -- packaging\.. is the project root.
cd /d "%~dp0.."

echo Installing/updating dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --upgrade pyinstaller

echo.
echo Building MarvelVerseTracker.exe...
pyinstaller packaging\MarvelVerseTracker.spec --noconfirm

echo.
echo Build complete. The executable is dist\MarvelVerseTracker.exe
pause
