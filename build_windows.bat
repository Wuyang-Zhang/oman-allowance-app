@echo on
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM 1) Check python
where python || (echo Python not found in PATH & pause & exit /b 1)
python --version

REM 2) Create venv if missing or broken
if not exist ".venv\\Scripts\\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || (echo Failed to create venv & pause & exit /b 1)
)

REM 3) Activate venv
call ".venv\\Scripts\\activate.bat" || (echo Failed to activate venv & pause & exit /b 1)

REM 4) Install deps
python -m pip install --upgrade pip || (echo pip upgrade failed & pause & exit /b 1)
python -m pip install -e . || (echo editable install failed & pause & exit /b 1)
python -m pip install pyinstaller pyside6 || (echo deps install failed & pause & exit /b 1)

REM 5) Build
python -m PyInstaller oma_gui.spec || (echo PyInstaller failed & pause & exit /b 1)

echo Build succeeded.
pause
