# Getting Started with Pixi for Microdrop

This guide provides instructions on how to set up and run the [Microdrop](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop) project using [Pixi](https://pixi.sh/dev/installation).

## Easiest Way: the Setup & Launcher app

Download the standalone installer/launcher (no Python required) — this link
always serves the newest build:

**https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/releases/latest/download/microdrop_setup.exe**

Run it and it walks you through everything:

1. **First run (pre-install):** choose where to install, pick the branches
   for this repo and the Microdrop source (dropdowns list the real remote
   branches), and it clones the repos, installs pixi if missing (official
   installer, or a manual-install link if you prefer), and prefetches the
   environment. This phase only appears once.
2. **Every later run (launcher):** pick which plugins load on boot
   (required plugins are always on), the device (DropBot / OpenDrop / mock),
   contexts, branches, and whether each repo auto-updates on launch. From
   here you can **Launch**, **Create a Desktop Shortcut** (runs the last
   saved configuration with the Microdrop icon), or start a **New
   Installation** (optionally deleting the current one).

Settings persist in your user appdata, so shortcuts keep working across
updates. To change launch parameters, just run the app again.

On Linux/macOS (or if you'd rather not use the exe), the same app is the
`microdrop_setup.py` script at the repo root — it needs only a system
Python 3 with tkinter:

```shell
python3 microdrop_setup.py
```

> The exe is rebuilt and released automatically (tags `setup-vN`) by CI
> whenever `microdrop_setup.py` changes on `master` — that's why the
> `releases/latest` link above is permanent. The exe itself is not tracked
> in git.

## Classic scripts

With [Pixi](https://pixi.sh/dev/installation) and git installed and the repo
cloned (`git clone --recursive https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop.git`):

- **Windows:** click `microdrop.bat` (self-updating launcher), or run
  `launch_microdrop.ps1` (slim: no git/self-update, just env setup + launch;
  forwards `--device/--plugins/--contexts` to the app)
- **Mac/Linux:** `sh run_microdrop.sh` (self-updating), or
  `sh launch_microdrop.sh` (slim)

## Manual way

1. Navigate to the microdrop-py directory:

```shell
cd microdrop-py
```

2. If you cloned without `--recursive` (or need to update nested repos),
   initialize and update the submodules:

```shell
git submodule update --init --recursive
```

3. Start the Microdrop application:

```shell
pixi run microdrop
```

   The configurable entry point (what the setup app and slim launchers use)
   also accepts a plugin/context selection:

```shell
pixi run microdrop_launch --device dropbot --plugins DeviceViewerPlugin DropbotControllerPlugin
```
