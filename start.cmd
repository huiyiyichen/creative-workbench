@echo off
setlocal DisableDelayedExpansion
title Creative Workbench

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1" -OpenBrowser %*
set "result=%errorlevel%"
if not "%result%"=="0" (
  echo.
  echo Creative Workbench could not start. See the error above.
  pause
)
exit /b %result%
