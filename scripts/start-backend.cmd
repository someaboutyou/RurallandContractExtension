@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
set "BACKEND_PATH=%PROJECT_ROOT%\backend"
set "PYTHON_EXE=D:\Programs\anaconda3\envs\erlunyanbao\python.exe"

pushd "%BACKEND_PATH%"
"%PYTHON_EXE%" -m uvicorn app.main:app --reload
popd

endlocal
