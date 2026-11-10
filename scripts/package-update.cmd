@echo off
SETLOCAL
set "SCRIPT_DIR=%~dp0"
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%package-update.ps1" %*
ENDLOCAL
