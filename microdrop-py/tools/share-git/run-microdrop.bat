@echo off
setlocal
title MicroDrop

rem The git hand-off's launcher: runs MicroDrop from the git clone in
rem .\microdrop with the unpacked environment. Sits beside the wheel
rem hand-off's tools\share\run-microdrop.bat rather than replacing it.

cd /d "%~dp0"

if not exist "env\python.exe" (
    echo MicroDrop is not installed yet. Run install.bat first.
    goto :fail
)

if not exist "activate.bat" (
    echo activate.bat is missing. Run install.bat again.
    goto :fail
)

if not exist "env\Lib\site-packages\microdrop_git.pth" (
    echo The environment is not linked to .\microdrop. Run install.bat again.
    goto :fail
)

call "%~dp0activate.bat"

rem Run from the source root, like a developer checkout, so relative paths
rem inside MicroDrop resolve the same way.
cd /d "%~dp0microdrop"

rem Extra arguments are passed through, e.g.
rem   run-microdrop.bat --device portable
rem   run-microdrop.bat --device mock
rem The default device is the DropBot.
"%~dp0env\python.exe" -m examples.run_device_viewer_pluggable %*

if errorlevel 1 (
    echo.
    echo MicroDrop exited with an error - see the messages above.
    goto :fail
)

exit /b 0

:fail
echo.
pause
exit /b 1
