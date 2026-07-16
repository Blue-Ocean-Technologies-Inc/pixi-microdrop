# Define the expected arguments
param (
    [ValidateSet("dropbot", "opendrop")]
    [string]$Device = "dropbot", # Sets dropbot as the default if no argument is provided

    # Add a flag to safely stash uncommitted work before updating
    [switch]$Stash
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

# Determine whether to use system git directly or fall back to pixi run git
if (Get-Command "git" -ErrorAction SilentlyContinue) {
    $git = "git"
} else {
    Write-Host "System git not found, using pixi run git as fallback." -ForegroundColor DarkYellow
    $git = $null  # signals to use pixi run git
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments)]$GitArgs)
    if ($git) {
        & $git @GitArgs
    } else {
        & pixi run git @GitArgs
    }
}

# --- Step 1: Update Parent Module (microdrop-py) ---
if (Test-Path -Path $parentPath) {
    Write-Host "Updating Parent Module: $parentPath" -ForegroundColor Yellow
    Push-Location -Path $parentPath

    if ($Stash) {
        Write-Host "Stashing uncommitted changes in parent module..." -ForegroundColor DarkYellow
#         Invoke-Git stash
    }

    # We attempt to pull the parent repo
    Write-Host "Pulling latest changes for parent..." -ForegroundColor Cyan
#     Invoke-Git pull
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: Could not pull parent module. Continuing..." -ForegroundColor DarkYellow
    }

    Pop-Location
    Write-Host "----------------------------------------" -ForegroundColor Cyan
}
else {
    Write-Host "Warning: Parent path not found at $parentPath" -ForegroundColor DarkYellow
}

# --- Step 2: Update Source & Run Microdrop (microdrop-py/src) ---
if (Test-Path -Path $targetPath) {
    Write-Host "Navigating to Source: $targetPath" -ForegroundColor Yellow
    Push-Location -Path $targetPath

    # Git Operations on src
    if ($Stash) {
        Write-Host "Stashing uncommitted changes in src module..." -ForegroundColor DarkYellow
        Invoke-Git stash
    }

    # A freshly-initialized submodule sits on a detached HEAD, where
    # `git pull` refuses to run — force a checkout of main in that case.
    $srcBranch = (Invoke-Git branch --show-current) | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($srcBranch)) {
        Write-Host "No branch checked out in src (detached HEAD); checking out main..." -ForegroundColor DarkYellow
        Invoke-Git checkout main
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Warning: Could not check out main. Continuing..." -ForegroundColor DarkYellow
        }
    }

    # Pull latest changes for the src submodule
    Write-Host "Pulling latest changes for src..." -ForegroundColor Cyan
    Invoke-Git pull
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: Could not pull src module. Continuing with current state..." -ForegroundColor DarkYellow
    }

    Pop-Location
    Write-Host "----------------------------------------" -ForegroundColor Cyan

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