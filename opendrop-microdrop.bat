@ECHO OFF
:: This batch file launches the PowerShell script in the same directory.
:: It bypasses the local execution policy for this specific run,
:: so it works even if you haven't set the system-wide policy.

TITLE PowerShell Launcher

ECHO Launching PowerShell script...
ECHO.

:: "%~dp0" refers to the folder where this .bat file is located.
:: Close the quotes after the filename, then list the script arguments
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_microdrop.ps1" -Device opendrop

:: If the script finishes instantly, this pause lets you see errors.
PAUSE