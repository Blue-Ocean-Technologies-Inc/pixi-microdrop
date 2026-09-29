@echo off
setlocal
title Update MicroDrop

rem Pull the latest MicroDrop into the git clone in .\microdrop. Uses the
rem environment's own git (kept in the pack for this), so no separate git
rem install is needed; a git already on PATH works too.

cd /d "%~dp0"

if not exist "microdrop\.git" (
    echo ERROR: .\microdrop is not a git clone - this update needs the git hand-off.
    goto :fail
)

if exist "activate.bat" call "%~dp0activate.bat"

where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git was not found. Run install.bat first, or install git.
    goto :fail
)

for /f "usebackq delims=" %%V in (`git -C microdrop describe --tags --always`) do set "BEFORE=%%V"

echo Updating MicroDrop (currently %BEFORE%)...
echo.

rem --ff-only: only ever move forward along main. If the clone was edited
rem locally, this stops rather than merging, and says so.
git -C microdrop pull --ff-only
if errorlevel 1 (
    echo.
    echo ERROR: the update failed. Check the internet connection. If the
    echo message above mentions local changes, the files in .\microdrop were
    echo edited - unzip a fresh copy of the download to start clean.
    goto :fail
)

for /f "usebackq delims=" %%V in (`git -C microdrop describe --tags --always`) do set "AFTER=%%V"

echo.
if "%BEFORE%"=="%AFTER%" (
    echo MicroDrop is already up to date ^(%AFTER%^).
) else (
    echo Updated MicroDrop from %BEFORE% to %AFTER%.
    echo Restart MicroDrop if it is running.
)

echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
