# Getting Started with Pixi for Microdrop

This repo is the launcher/environment workspace for
[Microdrop](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop): a
reproducible [pixi](https://pixi.sh/dev/installation) environment
(`microdrop-py/pyproject.toml` + `pixi.lock`) wrapping the Microdrop source as
the `microdrop-py/src` submodule.

## Easiest way: the MicroDrop Launcher

The standalone [MicroDrop Launcher](https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher)
bootstraps everything before any project environment exists — it needs only
**git** on the machine and installs pixi itself. Permanent links to the newest
release:

| OS | Download |
|---|---|
| Windows x64 | [microdrop_setup.exe](https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher/releases/latest/download/microdrop_setup.exe) |
| Linux x64 | [microdrop_setup-linux-x86_64](https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher/releases/latest/download/microdrop_setup-linux-x86_64) |
| Linux ARM64 (Raspberry Pi) | [microdrop_setup-linux-aarch64](https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher/releases/latest/download/microdrop_setup-linux-aarch64) |
| macOS Apple Silicon | [microdrop_setup-macos-arm64.dmg](https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher/releases/latest/download/microdrop_setup-macos-arm64.dmg) |

1. **First run (setup):** choose where to install and which branches of this
   repo and the Microdrop source to use; it clones this repo (with the
   submodule) into that directory, installs pixi if missing, and prefetches
   the environment.
2. **Every later run (launcher):** pick the launch mode (frontend / backend /
   dual), the device (dropbot / portable / opendrop / mock), and the plugins
   per group; manage branches and git maintenance; edit server settings
   (Redis host/port, Dramatiq workers). Save named config profiles and create
   desktop shortcuts that launch a profile directly.

See the launcher README for platform notes (Linux `chmod +x` and picking the
asset by `uname -m`; macOS first-launch approval of the unsigned app).

## Classic scripts

With [pixi](https://pixi.sh/dev/installation) and git installed and the repo
cloned (`git clone --recursive https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop.git`),
the scripts at the repo root update pixi and launch the app. They leave the
MicroDrop source checkout alone — the app manages its own source updates.

- **Windows:** double-click `microdrop.bat` (DropBot) or
  `opendrop-microdrop.bat` (OpenDrop). Both run `run_microdrop.ps1`, which
  runs `pixi self-update`, then launches.
- **Mac/Linux:** `sh run_microdrop.sh` (same self-update, then launch).

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

   Other tasks: `pixi run microdrop-frontend` / `microdrop-backend` (one side
   only), `pixi run opendrop-microdrop` (and its `-frontend` / `-backend`
   variants), `pixi run run_redis`, and `pixi run setup-hooks` (installs the
   git hooks in the source and plugin clones).

   The configurable entry point the launcher uses, `microdrop.py`, takes a
   device and an explicit plugin selection:

```shell
pixi run microdrop_launch --device portable --plugins DeviceViewerPlugin PortableDropbotControllerPlugin
```

## Peripheral plugins

The heater, magnet, and fluorescence plugins for the classic DropBot rig live
in their own repos, cloned alongside the source under `microdrop-py/` for
editable installs (they are deliberately not tracked here). The launcher
lists them as toggleable plugin groups.
