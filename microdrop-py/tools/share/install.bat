@echo off
setlocal
title Install MicroDrop

rem Work from this script's folder, wherever it was double-clicked from.
cd /d "%~dp0"

set "PACK="
for %%F in (microdrop-prod-*.tar) do set "PACK=%%F"

if not defined PACK (
    echo ERROR: no microdrop-prod-*.tar found next to install.bat.
    goto :fail
)

if not exist "pixi-unpack.exe" (
    echo ERROR: pixi-unpack.exe not found next to install.bat.
    goto :fail
)

if exist "env" (
    echo MicroDrop is already installed in:
    echo   %CD%\env
    echo.
    choice /c YN /m "Remove it and reinstall"
    if errorlevel 2 goto :done

    echo Removing the old install...
    rmdir /s /q "env"
    if exist "activate.bat" del /q "activate.bat"
)

echo.
echo Installing MicroDrop from %PACK%
echo This takes a few minutes and needs about 6 GB of free disk space (under 1 GB once done).
echo No internet connection is required.
echo.

"%~dp0pixi-unpack.exe" --output-directory . "%PACK%"
if errorlevel 1 (
    echo.
    echo ERROR: unpacking failed.
    goto :fail
)

if not exist "env\Scripts\microdrop.exe" (
    echo.
    echo ERROR: install finished but env\Scripts\microdrop.exe is missing.
    goto :fail
)

rem Shrink the install. First drop files only a compiler would use (import
rem libraries, debug symbols, C headers) - nothing loads them at run time.
rem Then apply Windows' transparent file compression: files stay readable in
rem place, the env just takes under half the disk space. XPRESS16K rather
rem than LZX: LZX squeezes out ~20% more but takes ten times as long (2.5 min
rem vs 16 s on a 1.9 GB env) and is slower to read back at every app start.
rem Both steps are optional, so a failure (e.g. a non-NTFS drive) never fails
rem the install.
set "MD_DIR=%CD%"
echo.
echo Compressing the install to save disk space...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$e = Join-Path $env:MD_DIR 'env'; Get-ChildItem $e -Recurse -File -Force -Include *.lib,*.pdb,*.a -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue; foreach ($i in 'Library\include','include') { $p = Join-Path $e $i; if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue } }; exit 0"
compact /c /s:"%MD_DIR%\env" /a /i /q /exe:xpress16k >nul 2>&1
if errorlevel 1 echo NOTE: could not compress the install (non-NTFS drive?). MicroDrop still works; it just uses more disk space.

rem The fluorescence plugin's AI ROI detection loads its SAM model weights
rem from a fixed per-user cache and would otherwise download them on first
rem use. Seed that cache from .\models so the feature works offline. Files
rem are named by their SHA-256, so an existing one is already identical.
set "OSAM_BLOBS=%USERPROFILE%\.cache\osam\models\blobs"
if exist "models\sha256-*" if not exist "%OSAM_BLOBS%" mkdir "%OSAM_BLOBS%"
for %%M in (models\sha256-*) do if not exist "%OSAM_BLOBS%\%%~nxM" copy /y "%%M" "%OSAM_BLOBS%\" >nul
if exist "models\sha256-*" echo Installed the offline AI model for fluorescence ROI detection.

rem A .bat cannot carry an icon, so make a "MicroDrop <version>" shortcut
rem that does. It holds absolute paths, which is why it is created here and
rem not shipped. The version in the name keeps several installed versions
rem apart on the Desktop; an existing Desktop shortcut of the same name is
rem left alone. The version is read from the installed package.
set "MD_DIR=%CD%"
set "MD_VERSION="
for /f "usebackq delims=" %%V in (`env\python.exe -c "import importlib.metadata as m; print(m.version('microdrop_py'))"`) do set "MD_VERSION=%%V"
set "MD_NAME=MicroDrop"
if defined MD_VERSION set "MD_NAME=MicroDrop %MD_VERSION%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d = $env:MD_DIR; $name = $env:MD_NAME + '.lnk'; $sh = New-Object -ComObject WScript.Shell; $targets = @((Join-Path $d $name)); $deskDir = [Environment]::GetFolderPath('Desktop'); if ($deskDir) { $desk = Join-Path $deskDir $name; if (-not (Test-Path $desk)) { $targets += $desk } }; foreach ($p in $targets) { $l = $sh.CreateShortcut($p); $l.TargetPath = Join-Path $d 'run-microdrop.bat'; $l.WorkingDirectory = $d; $l.IconLocation = (Join-Path $d 'env\Lib\site-packages\microdrop_style\icons\Microdrop_Icon.ico') + ',0'; $l.Description = $env:MD_NAME; $l.Save() }"
if errorlevel 1 echo WARNING: could not create the %MD_NAME% shortcut - use run-microdrop.bat instead.

echo.
echo Done. Start MicroDrop with the "%MD_NAME%" shortcut in this folder
echo (and on your Desktop, unless one with that name was already there),
echo or double-click run-microdrop.bat.
echo.
echo NOTE: the install is tied to this folder. If you move or rename the
echo folder, run install.bat again.

rem Each older install left its own "MicroDrop <version>" shortcut on the
rem Desktop, pointing at run-microdrop.bat in its folder. Now that this
rem version supersedes them, remove those shortcuts and offer to delete each
rem old install folder. A folder is only offered when its shortcut points
rem at a run-microdrop.bat inside it and it holds an install.bat; this
rem folder and any parent of it are never offered.
for /f "usebackq delims=" %%O in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$d = $env:MD_DIR; $sh = New-Object -ComObject WScript.Shell; $deskDir = [Environment]::GetFolderPath('Desktop'); $olds = @(); if ($deskDir) { foreach ($p in Get-ChildItem -Path (Join-Path $deskDir 'MicroDrop*.lnk') -ErrorAction SilentlyContinue) { $t = $sh.CreateShortcut($p.FullName).TargetPath; if ($t -and (Split-Path $t -Leaf) -ieq 'run-microdrop.bat') { $old = Split-Path $t -Parent; if ($old -ine $d) { Remove-Item $p.FullName -Force; if ((Test-Path (Join-Path $old 'install.bat')) -and -not ($d + '\').StartsWith($old + '\', 'OrdinalIgnoreCase') -and $olds -notcontains $old) { $olds += $old } } } } }; $olds"`) do call :remove_old "%%O"

:done
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1

rem Offer to delete one previous install folder (%1). Its Desktop shortcut
rem has already been removed by the sweep above.
:remove_old
echo.
echo A previous MicroDrop install was found in:
echo   %~1
echo Its Desktop shortcut has been removed. The install itself still works
echo from run-microdrop.bat in that folder.
choice /c YN /m "Delete that previous install completely"
if errorlevel 2 goto :eof

echo Deleting %~1 ...
rmdir /s /q "%~1"
if exist "%~1" (echo WARNING: could not delete it - close MicroDrop if it is running there, then delete the folder by hand.) else (echo Deleted.)
goto :eof
