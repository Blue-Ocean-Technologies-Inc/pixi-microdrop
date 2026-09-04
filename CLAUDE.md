# pixi-microdrop

This is the launcher/environment workspace for MicroDrop. Start Claude Code from
**this directory** — it is where the shared `.claude/` config (skills and hooks)
and the canonical memory store are resolved from.

## Layout

- `microdrop-py/` — the pixi workspace: `pyproject.toml` (the pixi manifest),
  `pixi.lock`, and the env under `.pixi/envs/default`.
- `microdrop-py/src/` — git submodule holding the actual MicroDrop source
  (Pyface/Envisage app). Remote: `Blue-Ocean-Technologies-Inc/Microdrop`, branch `main`.
- `microdrop-py/fluorescence-microdrop-plugin-py/` — the fluorescence plugin, its
  own git repo, deliberately untracked here (same as the heater and magnet plugins).

The full project instructions live in the submodule's docs folder so both this
repo and the standalone Microdrop clone share one copy:

@microdrop-py/src/docs/CLAUDE.md

## Releases

Versioned by commitizen from Conventional Commits, like the launcher: every
push to `master` with a releasable commit (`feat`/`fix`/breaking) bumps the
version, rewrites `CHANGELOG.md`, tags `vX.Y.Z`, and publishes a GitHub
Release (`.github/workflows/release.yml`). `CHANGELOG.md` is generated — never
edit it by hand. `pixi run setup-hooks` (from `microdrop-py/`) installs the
commit-message hook here as well as in the source and plugin clones.

## Repo hygiene

Never commit firmware images (`firmware_*.zip`, `.hex`, `.uf2`), experiment
capture data, or scratch notes to this repo — firmware ships with the boards.
`.gitignore` enforces this; do not add exceptions.

Pre-commit runs ruff, the copyright-header inserter, and the shared
`microdrop-dev-hooks` hooks on the launcher's own Python files; the
submodule and plugin clones have their own configs.
