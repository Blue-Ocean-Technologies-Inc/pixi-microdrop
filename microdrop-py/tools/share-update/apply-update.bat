@echo off
setlocal
title Update MicroDrop

rem Bring an existing MicroDrop install up to the package versions in
rem .\channel and .\wheels, offline. micromamba resolves the conda packages
rem against the local channel and the packages the install already has, then
rem the install's own pip installs the PyPI wheels; nothing is downloaded.
rem MicroDrop's own wheel is skipped for a git install (MicroDrop linked from
rem its clone in ..\microdrop), which update-microdrop.bat updates instead.
rem Set MICRODROP_UPDATE_NOPAUSE=1 to run it unattended (no pause at the end).

rem Work from this script's folder, wherever it was double-clicked from.
cd /d "%~dp0"
set "HERE=%~dp0"

for %%F in (micromamba.exe fix-conda-meta.py specs.txt optional-specs.txt plugins.txt pypi-specs.txt microdrop-spec.txt channel\noarch\repodata.json) do if not exist "%%F" goto :incomplete

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

echo Updating MicroDrop in:
echo   %ENV_DIR%
echo.
echo Plugins installed now:
call :show_plugins

rem The packages to install: every spec in specs.txt, plus the build
rem toolchain packages in optional-specs.txt (git, clang) only where the
rem install already has them - slim installs leave them out on purpose.
if not exist "%HERE%mamba-root" mkdir "%HERE%mamba-root"
set "INSTALL_SPECS=%HERE%mamba-root\install-specs.txt"
copy /y "%HERE%specs.txt" "%INSTALL_SPECS%" >nul
for /f "usebackq tokens=1* delims==" %%N in ("%HERE%optional-specs.txt") do if exist "%ENV_DIR%\conda-meta\%%N-*.json" >>"%INSTALL_SPECS%" echo %%N=%%O
set "COUNT=0"
for /f %%C in ('type "%INSTALL_SPECS%" ^| find /c /v ""') do set "COUNT=%%C"

echo.
echo Installing %COUNT% packages. This takes a few minutes. No internet
echo connection is needed.
echo.
if "%COUNT%"=="0" goto :installed

rem pixi-unpack records every installed package with "channel": null,
rem which micromamba refuses to read. Fill it in from the package URL.
"%ENV_DIR%\python.exe" -I "%HERE%fix-conda-meta.py" "%ENV_DIR%\conda-meta"
if errorlevel 1 goto :install_failed

rem micromamba cannot parse a channel, prefix or file path containing spaces
rem (C:\Users\John Doe\...), so hand it the 8.3 short forms, which have
rem none. A volume without short names returns the long path unchanged.
for %%I in ("%HERE%channel") do set "CHANNEL=%%~sI"
for %%I in ("%ENV_DIR%") do set "PREFIX=%%~sI"
for %%I in ("%HERE%mamba-root") do set "ROOT=%%~sI"
set "PATHS=%CHANNEL%%PREFIX%%ROOT%"
if not "%PATHS: =%"=="%PATHS%" call :warn_spaces

rem --no-rc / --no-env: ignore any conda/mamba settings on this PC. The
rem root prefix holds micromamba's package cache; keep it inside this folder.
"%HERE%micromamba.exe" install --no-rc --no-env -r "%ROOT%" -p "%PREFIX%" --offline --override-channels -c "%CHANNEL%" -y -f "%ROOT%\install-specs.txt"
if errorlevel 1 goto :install_failed

:installed
rem The PyPI wheels go in after the conda packages, with the install's own
rem pip, from .\wheels only. -I and --isolated: ignore any Python or pip
rem settings on this PC. --no-deps: the wheels are the complete set.
set "SITE=%ENV_DIR%\Lib\site-packages"
set "MICRODROP_WHEEL="
if exist "%SITE%\microdrop_py-*.dist-info" set "MICRODROP_WHEEL=1"
if exist "%SITE%\microdrop_git.pth" set "MICRODROP_WHEEL="

rem The loop variable must not be a letter that follows a percent sign in
rem %PIP_SPECS% (e.g. P), or cmd substitutes it inside the variable name.
set "PIP_SPECS="
for /f "usebackq delims=" %%L in ("%HERE%pypi-specs.txt") do call set "PIP_SPECS=%%PIP_SPECS%% %%L"
if defined MICRODROP_WHEEL for /f "usebackq delims=" %%L in ("%HERE%microdrop-spec.txt") do call set "PIP_SPECS=%%PIP_SPECS%% %%L"
if not defined MICRODROP_WHEEL call :note_git_install
if not defined PIP_SPECS goto :pip_done

echo.
echo Installing PyPI packages:%PIP_SPECS%
echo.
"%ENV_DIR%\python.exe" -I -m pip install --isolated --no-index --no-deps --disable-pip-version-check --no-warn-script-location --find-links "%HERE%wheels" --upgrade %PIP_SPECS%
if errorlevel 1 goto :install_failed

:pip_done
echo.
echo Plugins installed now:
call :show_plugins
echo.
echo Done. Start MicroDrop again to use the update.

echo.
if not defined MICRODROP_UPDATE_NOPAUSE pause
exit /b 0

:show_plugins
for /f "usebackq delims=" %%N in ("%HERE%plugins.txt") do call :show_plugin %%N
goto :eof

:show_plugin
set "FOUND="
for %%F in ("%ENV_DIR%\conda-meta\%~1-*.json") do (
    echo   %%~nF
    set "FOUND=1"
)
if not defined FOUND echo   %~1 - not installed
goto :eof

:note_git_install
echo.
echo MicroDrop itself runs from its git clone here, so this update leaves its
echo code alone: run update-microdrop.bat in your MicroDrop folder to update
echo it (that needs internet).
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
echo ERROR: the update failed - see the messages above. MicroDrop may now be
echo partly updated. To go back to the shipped versions, rerun install.bat
echo from your MicroDrop download and answer Y to reinstall. If this install
echo was not set up from a download this update was made for, ask for a full
echo update instead.
goto :fail

:fail
echo.
if not defined MICRODROP_UPDATE_NOPAUSE pause
exit /b 1
