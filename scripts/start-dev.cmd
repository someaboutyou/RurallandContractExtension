@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

start "Ruralland Backend" cmd /k ""%SCRIPT_DIR%start-backend.cmd""
start "Ruralland Frontend" cmd /k ""%SCRIPT_DIR%start-frontend.cmd""

endlocal
