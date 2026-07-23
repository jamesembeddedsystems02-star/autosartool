@echo off
REM Simplest way to run the BMS HIL tool on Windows.
REM   Double-click this file            -> interactive menu
REM   run.bat test                      -> run the test suite
REM   run.bat demo                      -> run the demo
cd /d "%~dp0"
where python >nul 2>&1
if %errorlevel%==0 (
  python run_bms_hil.py %*
) else (
  py run_bms_hil.py %*
)
echo.
pause
