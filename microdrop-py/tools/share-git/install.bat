@echo off
setlocal
title Install MicroDrop

rem The git hand-off's installer. It sits beside the wheel hand-off's
rem tools\share\install.bat rather than replacing it: here MicroDrop is the
rem git clone in .\microdrop (updated with update-microdrop.bat), and only
rem the packed environment is unpacked.

rem Work from this script's folder, wherever it was double-clicked from.
cd /d "%~dp0"

set "PACK="
for %%F in (microdrop-prod-git-*.tar) do set "PACK=%%F"

if not defined PACK (
    echo ERROR: no microdrop-prod-git-*.tar found next to install.bat.
    goto :fail
)

if not exist "pixi-unpack.exe" (
    echo ERROR: pixi-unpack.exe not found next to install.bat.
    goto :fail
)

if not exist "microdrop\examples\run_device_viewer_pluggable.py" (
    echo ERROR: the MicroDrop source folder .\microdrop is missing or incomplete.
    goto :fail
)

if exist "env" (
    echo The MicroDrop environment is already installed in:
    echo   %CD%\env
    echo.
    choice /c YN /m "Remove it and reinstall"
    if errorlevel 2 goto :done

    echo Removing the old environment...
    rmdir /s /q "env"
    if exist "activate.bat" del /q "activate.bat"
)

echo.
echo Installing the MicroDrop environment from %PACK%
echo This takes a few minutes and needs about 6 GB of free disk space (under 1 GB once done).
echo No internet connection is required.
echo.

"%~dp0pixi-unpack.exe" --output-directory . "%PACK%"
if errorlevel 1 (
    echo.
    echo ERROR: unpacking failed.
    goto :fail
)

if not exist "env\python.exe" (
    echo.
    echo ERROR: install finished but env\python.exe is missing.
    goto :fail
)

rem Point the environment at the git clone: a .pth file puts .\microdrop on
rem every interpreter's import path (the app and the worker processes it
rem starts), which is what an editable install does. It holds an absolute
rem path, so moving the folder means running install.bat again.
> "env\Lib\site-packages\microdrop_git.pth" echo %CD%\microdrop

rem Shrink the install. First drop files only a compiler would use (import
rem libraries, debug symbols, C headers) - nothing loads them at run time.
rem Then apply Windows' transparent file compression: files stay readable in
rem place, the env just takes under half the disk space. Both steps are
rem optional, so a failure (e.g. a non-NTFS drive) never fails the install.
set "MD_DIR=%CD%"
echo.
echo Compressing the install to save disk space...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$e = Join-Path $env:MD_DIR 'env'; Get-ChildItem $e -Recurse -File -Force -Include *.lib,*.pdb,*.a -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue; foreach ($i in 'Library\include','include') { $p = Join-Path $e $i; if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue } }; exit 0"
compact /c /s:"%MD_DIR%\env" /a /i /q /exe:xpress16k >nul 2>&1
if errorlevel 1 echo NOTE: could not compress the install (non-NTFS drive?). MicroDrop still works; it just uses more disk space.

rem AI ROI detection loads its SAM model weights from a fixed per-user cache
rem and would otherwise download them on first use. Seed that cache from
rem .\models so the feature works offline. Files are named by their
rem SHA-256, so an existing one is already identical.
set "OSAM_BLOBS=%USERPROFILE%\.cache\osam\models\blobs"
if exist "models\sha256-*" if not exist "%OSAM_BLOBS%" mkdir "%OSAM_BLOBS%"
for %%M in (models\sha256-*) do if not exist "%OSAM_BLOBS%\%%~nxM" copy /y "%%M" "%OSAM_BLOBS%\" >nul
if exist "models\sha256-*" echo Installed the offline AI model for ROI detection.

rem A .bat cannot carry an icon, so make a "MicroDrop" shortcut that does.
rem It holds absolute paths, which is why it is created here and not
rem shipped. One name for every version: updates happen in place with
rem update-microdrop.bat, so there is only ever one install to point at.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d = $env:MD_DIR; $sh = New-Object -ComObject WScript.Shell; $targets = @((Join-Path $d 'MicroDrop.lnk')); $deskDir = [Environment]::GetFolderPath('Desktop'); if ($deskDir) { $targets += (Join-Path $deskDir 'MicroDrop.lnk') }; foreach ($p in $targets) { $l = $sh.CreateShortcut($p); $l.TargetPath = Join-Path $d 'run-microdrop.bat'; $l.WorkingDirectory = $d; $l.IconLocation = (Join-Path $d 'microdrop\microdrop_style\icons\Microdrop_Icon.ico') + ',0'; $l.Description = 'MicroDrop'; $l.Save() }"
if errorlevel 1 echo WARNING: could not create the MicroDrop shortcut - use run-microdrop.bat instead.

echo.
echo Done. Start MicroDrop with the "MicroDrop" shortcut in this folder and
echo on your Desktop, or double-click run-microdrop.bat.
echo Get the latest MicroDrop at any time with update-microdrop.bat.
echo.
echo NOTE: the install is tied to this folder. If you move or rename the
echo folder, run install.bat again.

rem Only install.bat reads the pack, so once the env is in place it just
rem takes up space. Offer to delete it, but a reinstall (e.g. after moving
rem the folder) needs it, so say so. The size is under 2 GB, so set /a
rem (32-bit) is safe.
for %%F in ("%PACK%") do set /a PACK_MB=%%~zF / 1048576
echo.
echo The packed environment %PACK% (%PACK_MB% MB) is no longer needed
echo to run MicroDrop. Without it, though, install.bat cannot run again
echo (e.g. after moving this folder) until you unzip the download again.
choice /c YN /m "Delete %PACK% now"
if not errorlevel 2 del /q "%PACK%" && echo Deleted %PACK%.

:done
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
