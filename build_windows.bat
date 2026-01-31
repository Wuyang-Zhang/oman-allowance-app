@echo on
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM 1) Check python
where python || (echo Python not found in PATH & pause & exit /b 1)
python --version

REM 2) Create venv if missing or broken
set "OMA_PY=D:\Miniconda3\Miniconda3py38\envs\oma310\python.exe"
if not exist "%OMA_PY%" (
  set "OMA_PY=python"
)
if exist ".venv\\Scripts\\python.exe" (
  for /f "tokens=2" %%v in ('".venv\\Scripts\\python.exe" --version') do set "VENV_VER=%%v"
  if "!VENV_VER:~0,3!"=="3.8" (
    echo Recreating venv with oma310 Python...
    rmdir /s /q .venv
  )
)
if not exist ".venv\\Scripts\\python.exe" (
  echo Creating virtual environment with %OMA_PY%...
  "%OMA_PY%" -m venv .venv || (echo Failed to create venv & pause & exit /b 1)
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
