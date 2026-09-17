@echo off
setlocal
title MicroDrop

cd /d "%~dp0"

if not exist "env\Scripts\microdrop.exe" (
    echo MicroDrop is not installed yet. Run install.bat first.
    goto :fail
)

if not exist "activate.bat" (
    echo activate.bat is missing. Run install.bat again.
    goto :fail
)

call "%~dp0activate.bat"

rem Extra arguments are passed through, e.g.
rem   run-microdrop.bat --device portable
rem   run-microdrop.bat --device mock
rem The default device is the DropBot.
"%~dp0env\Scripts\microdrop.exe" %*

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
