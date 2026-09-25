@echo off
REM ============================================================
REM  Build the debug APK with a JDK 21 toolchain.
REM
REM  Why this wrapper exists:
REM  Capacitor 7.6.9's Android libraries hardcode
REM  JavaVersion.VERSION_21, so Gradle itself must run on JDK 21.
REM  Android Studio already keeps a JBR 21 under %USERPROFILE%\.jdks,
REM  but the *command line* gradlew ignores Studio's setting
REM  (android\.gradle\config.properties) and only reads JAVA_HOME.
REM  Meanwhile the system JAVA_HOME may point at JDK 17, and the JBR
REM  bundled with the newest Android Studio is Java 25 - which
REM  Gradle 8.13 cannot run on ("Unsupported class file major
REM  version 69"). This wrapper picks the JDK 21 for this run only
REM  and leaves the machine-wide JAVA_HOME untouched.
REM
REM  Usage:
REM    build-apk.cmd                        -> assembleDebug
REM    build-apk.cmd clean assembleDebug
REM ============================================================
setlocal

set "JAVA_HOME="
for /d %%D in ("%USERPROFILE%\.jdks\jbr-21*" "%USERPROFILE%\.jdks\jdk-21*" "%USERPROFILE%\.jdks\21*") do (
  if exist "%%~fD\bin\java.exe" set "JAVA_HOME=%%~fD"
)

if not defined JAVA_HOME (
  echo.
  echo [build-apk] ERROR: no JDK 21 found under "%USERPROFILE%\.jdks"
  echo.
  echo Capacitor 7.6.9 requires Gradle to run on JDK 21.
  echo Install one via Android Studio:
  echo   Settings ^> Build, Execution, Deployment ^> Build Tools ^> Gradle
  echo   ^> Gradle JDK ^> "Download JDK..." ^> version 21
  echo Studio puts it in "%USERPROFILE%\.jdks" and this script will find it.
  echo.
  exit /b 1
)

cd /d "%~dp0"
echo [build-apk] JAVA_HOME=%JAVA_HOME%
call "%~dp0gradlew.bat" --version 2>&1 | findstr /C:"Gradle " /C:"JVM:"
echo [build-apk] command: gradlew %*
echo.

if "%~1"=="" (
  call "%~dp0gradlew.bat" assembleDebug --console=plain
) else (
  call "%~dp0gradlew.bat" %* --console=plain
)
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  echo.
  echo [build-apk] SUCCESS -^> android\app\build\outputs\apk\debug\app-debug.apk
) else (
  echo.
  echo [build-apk] FAILED, exit code %RC%
)
exit /b %RC%
