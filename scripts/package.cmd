@echo off
SETLOCAL
set "SCRIPT_DIR=%~dp0"
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%package.ps1" %*
ENDLOCAL
