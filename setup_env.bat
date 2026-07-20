@echo off
REM Create and provision a Python virtual environment for the BMS HIL tool (Windows).
REM
REM Usage:
REM   setup_env.bat          runtime env (.venv) + editable install
REM   setup_env.bat --dev    also install dev/test deps
REM
REM After running:  .venv\Scripts\activate  &&  bms-hil selftest
setlocal
cd /d "%~dp0"

set VENV_DIR=.venv
if not exist "%VENV_DIR%" (
  echo ^>^> Creating virtual environment in %VENV_DIR%
  python -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

echo ^>^> Upgrading pip
python -m pip install --upgrade pip >nul

if "%1"=="--dev" (
  echo ^>^> Installing dev dependencies
  pip install -r requirements-dev.txt
  pip install -e ".[dev,hardware,config]"
) else (
  echo ^>^> Installing runtime dependencies
  pip install -r requirements.txt
  pip install -e .
)

echo.
echo ^>^> Environment ready. Activate it with:
echo      %VENV_DIR%\Scripts\activate
echo ^>^> Then try:  bms-hil selftest
endlocal
