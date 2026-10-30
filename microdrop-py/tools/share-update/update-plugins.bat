@echo off
setlocal
title Update MicroDrop plugins

rem Install the newer plugin packages in .\channel into an existing MicroDrop
rem install, offline. micromamba resolves them against the local channel
rem and the packages the install already has; nothing is downloaded. Only
rem conda packages change: MicroDrop itself (its wheel, or the git clone in
rem .\microdrop) is left alone.
rem Set MICRODROP_UPDATE_NOPAUSE=1 to run it unattended (no pause at the end).

rem Work from this script's folder, wherever it was double-clicked from.
cd /d "%~dp0"
set "HERE=%~dp0"

for %%F in (micromamba.exe fix-conda-meta.py specs.txt base-plugins.txt channel\noarch\repodata.json) do if not exist "%%F" goto :incomplete

rem Find the install: this folder unzipped inside the MicroDrop folder (the
rem expected case), the MicroDrop folder itself, or ask for it.
set "MD_DIR="
if exist "..\env\python.exe" for %%D in ("%CD%\..") do set "MD_DIR=%%~fD"
if not defined MD_DIR if exist "env\python.exe" set "MD_DIR=%CD%"
if not defined MD_DIR call :ask_folder
if not defined MD_DIR goto :fail

set "ENV_DIR=%MD_DIR%\env"
if not exist "%ENV_DIR%\python.exe" if exist "%MD_DIR%\conda-meta" set "ENV_DIR=%MD_DIR%"
if not exist "%ENV_DIR%\python.exe" goto :no_install
if not exist "%ENV_DIR%\conda-meta" goto :no_install

rem Windows cannot replace files a running program has open, so refuse
rem while anything runs out of the install (MicroDrop, its Redis server).
powershell -NoProfile -ExecutionPolicy Bypass -Command "$e = (Resolve-Path -LiteralPath $env:ENV_DIR).Path.TrimEnd('\') + '\'; $p = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($e, 'OrdinalIgnoreCase') }; if ($p) { exit 3 }; exit 0" 2>nul
if "%ERRORLEVEL%"=="3" goto :running

echo Updating the MicroDrop plugins in:
echo   %ENV_DIR%
echo.
echo Installed now:
call :show_plugins

rem The bundle was built against one shipped install. A different one most
rem likely still updates fine, but say so in case it does not.
set "MISMATCH="
for /f "usebackq delims=" %%P in ("%HERE%base-plugins.txt") do if not exist "%ENV_DIR%\conda-meta\%%P.json" set "MISMATCH=1"
if defined MISMATCH call :warn_mismatch

rem The loop variable must not be a letter that follows a percent sign in
rem %SPECS% (e.g. S), or cmd substitutes it inside the variable name.
set "SPECS="
for /f "usebackq delims=" %%L in ("%HERE%specs.txt") do call set "SPECS=%%SPECS%% %%L"

echo.
echo Installing:%SPECS%
echo This takes about a minute. No internet connection is needed.
echo.

rem pixi-unpack records every installed package with "channel": null,
rem which micromamba refuses to read. Fill it in from the package URL.
"%ENV_DIR%\python.exe" -I "%HERE%fix-conda-meta.py" "%ENV_DIR%\conda-meta"
if errorlevel 1 goto :install_failed

rem micromamba cannot parse a channel or prefix path containing spaces
rem (C:\Users\John Doe\...), so hand it the 8.3 short forms, which have
rem none. A volume without short names returns the long path unchanged.
if not exist "%HERE%mamba-root" mkdir "%HERE%mamba-root"
for %%I in ("%HERE%channel") do set "CHANNEL=%%~sI"
for %%I in ("%ENV_DIR%") do set "PREFIX=%%~sI"
for %%I in ("%HERE%mamba-root") do set "ROOT=%%~sI"
set "PATHS=%CHANNEL%%PREFIX%%ROOT%"
if not "%PATHS: =%"=="%PATHS%" call :warn_spaces

rem --no-rc / --no-env: ignore any conda/mamba settings on this PC. The
rem root prefix holds micromamba's package cache; keep it inside this folder.
"%HERE%micromamba.exe" install --no-rc --no-env -r "%ROOT%" -p "%PREFIX%" --offline --override-channels -c "%CHANNEL%" -y %SPECS%
if errorlevel 1 goto :install_failed

echo.
echo Installed now:
call :show_plugins
echo.
echo Done. Start MicroDrop again to use the updated plugins.

echo.
if not defined MICRODROP_UPDATE_NOPAUSE pause
exit /b 0

:show_plugins
for /f "usebackq tokens=1 delims==" %%N in ("%HERE%specs.txt") do call :show_plugin %%N
goto :eof

:show_plugin
set "FOUND="
for %%F in ("%ENV_DIR%\conda-meta\%~1-*.json") do (
    echo   %%~nF
    set "FOUND=1"
)
if not defined FOUND echo   %~1 - not installed
goto :eof

:ask_folder
echo Could not find MicroDrop next to this folder. Unzip the update inside
echo your MicroDrop folder - the one with install.bat and the env folder -
echo or type the path of that folder below.
echo.
set /p "MD_DIR=MicroDrop folder: "
if not defined MD_DIR goto :eof
set "MD_DIR=%MD_DIR:"=%"
goto :eof

:warn_mismatch
echo.
echo WARNING: this update was made for an install with these plugins:
for /f "usebackq delims=" %%P in ("%HERE%base-plugins.txt") do echo   %%P
echo The installed plugins differ - this install was set up from another
echo MicroDrop download, or was updated before. Continuing anyway.
goto :eof

:warn_spaces
echo WARNING: the MicroDrop folder or this update folder has spaces in its
echo path and Windows has no short name for it. If the update fails, move
echo this folder to a path without spaces, e.g. C:\MicroDrop-update.
echo.
goto :eof

:incomplete
echo ERROR: this folder is incomplete. Unzip the whole update download again.
goto :fail

:no_install
echo ERROR: no MicroDrop install found in
echo   %MD_DIR%
echo (env\python.exe is missing). Unzip the update inside your MicroDrop
echo folder, next to its env folder, and run this again.
goto :fail

:running
echo ERROR: MicroDrop is running from
echo   %MD_DIR%
echo Close MicroDrop (and its Redis server window, if one is open), then run
echo this again.
goto :fail

:install_failed
echo.
echo ERROR: the plugin update failed - see the messages above. MicroDrop may
echo now be partly updated. To go back to the shipped plugin versions, rerun
echo install.bat from your MicroDrop download and answer Y to reinstall.
goto :fail

:fail
echo.
if not defined MICRODROP_UPDATE_NOPAUSE pause
exit /b 1
