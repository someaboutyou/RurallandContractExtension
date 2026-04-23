@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
set "FRONTEND_PATH=%PROJECT_ROOT%\frontend"

pushd "%FRONTEND_PATH%"
npm run dev
popd

endlocal
