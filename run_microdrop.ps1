# Define the expected arguments
param (
    [ValidateSet("dropbot", "opendrop")]
    [string]$Device = "dropbot" # Sets dropbot as the default if no argument is provided
)

# Set the console window title (re-asserted here so it sticks even when the
# .ps1 is launched directly, not just via the .bat wrappers).
$Host.UI.RawUI.WindowTitle = "Microdrop (Beta)"

# Configuration: Paths
# Parent module path (microdrop-py)
$parentPath = Join-Path -Path $PSScriptRoot -ChildPath "microdrop-py"
# Application source path (microdrop-py\src)
$targetPath = Join-Path -Path $parentPath -ChildPath "src"

Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "      Pixi Microdrop Launcher           " -ForegroundColor Green
Write-Host "----------------------------------------" -ForegroundColor Cyan

# Check if Pixi is installed before trying any commands
if (-not (Get-Command "pixi" -ErrorAction SilentlyContinue)) {
    Write-Host "Error: 'pixi' command not found. Is it installed and in your PATH?" -ForegroundColor Red
    exit 1
}

# Keep pixi itself current before it updates/launches everything else.
Write-Host "Updating pixi..." -ForegroundColor Cyan
& pixi self-update
if ($LASTEXITCODE -ne 0) {
    # Non-fatal: self-update is unavailable for some install methods
    # (conda/scoop-managed pixi), and an old-but-working pixi can still launch.
    Write-Host "Warning: pixi self-update failed. Continuing with the current version..." -ForegroundColor DarkYellow
}
Write-Host "----------------------------------------" -ForegroundColor Cyan

# --- Run Microdrop (microdrop-py) ---
# The source checkout (microdrop-py/src) is left untouched: MicroDrop manages
# its own source updates, including staying on a pinned release.
if (Test-Path -Path $targetPath) {
    # Launch from the parent path where pixi.toml lives
    Set-Location -Path $parentPath

    # Use a switch statement exclusively to route the launch command
    switch ($Device) {
        "opendrop" {
            Write-Host "Starting OpenDrop Microdrop..." -ForegroundColor Green
            & pixi run opendrop-microdrop
        }
        "dropbot" {
            Write-Host "Starting DropBot Microdrop..." -ForegroundColor Magenta
            & pixi run microdrop
        }
    }
}
else {
    Write-Host "Error: The source folder path does not exist:" -ForegroundColor Red
    Write-Host "$targetPath" -ForegroundColor Red
    exit 1
}

# Pause at the end so the window doesn't close immediately if run via click
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "Done." -ForegroundColor Gray
Read-Host "Press Enter to exit"