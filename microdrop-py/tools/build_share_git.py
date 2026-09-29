# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Assemble the git hand-off folder and zip around a slim prod pack.

The git hand-off is for a user who cannot fetch conda packages but can use
git: the packed environment (with git kept in it) installs offline, and
MicroDrop itself is a git clone of Microdrop's main branch rather than a
wheel inside the pack, so the user pulls every update pushed to main with
update-microdrop.bat. It always carries the AI stack and the default SAM
weights.

It sits beside build_share.py (the wheel hand-off) and reuses its download
helpers.

Usage: python tools/build_share_git.py <platform>
"""

# Standard library imports.
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

# Local imports.
from build_share import (
    DEFAULT_AI_MODEL,
    DIST,
    HANDOFF_PLATFORM,
    collect_model_blobs,
    fetch_pixi_unpack,
    write_windows_text,
)

TEMPLATES = Path(__file__).parent / "share-git"

#: The repository and branch the customer's clone tracks.
MICRODROP_REPO = "https://github.com/Blue-Ocean-Technologies-Inc/Microdrop.git"
MICRODROP_BRANCH = "main"

FOLDER_NAME = "share-microdrop-git"

SCRIPTS = ("install.bat", "run-microdrop.bat", "update-microdrop.bat")


def read_pack_info(pack_path):
    """The pixi-pack version the pack was made with, after checking the
    pack is what this hand-off needs: the AI stack and git in, and no
    MicroDrop wheel (the clone is MicroDrop here — a packed copy would
    shadow it)."""
    names = set()

    with tarfile.open(pack_path) as pack:
        metadata = json.load(pack.extractfile("pixi-pack.json"))

        for member in pack:
            names.add(member.name.rsplit("/", 1)[-1])

    if not any(name.startswith("osam-") for name in names):
        raise SystemExit(f"{pack_path} has no AI stack (osam) - pack the prod env")

    if not any(name.startswith("git-") for name in names):
        raise SystemExit(f"{pack_path} has no git - prune it with --keep git")

    if any(name.startswith("microdrop_py-") for name in names):
        raise SystemExit(f"{pack_path} carries a MicroDrop wheel - pack without it")

    return metadata["pixi-pack-version"]


def clone_microdrop(destination):
    """Clone Microdrop's main branch with full history (tags included, so
    ``git describe`` names the version); returns that description."""
    subprocess.run(
        [
            "git",
            "clone",
            "--branch",
            MICRODROP_BRANCH,
            MICRODROP_REPO,
            str(destination),
        ],
        check=True,
    )
    described = subprocess.run(
        ["git", "-C", str(destination), "describe", "--tags", "--always"],
        check=True,
        capture_output=True,
        text=True,
    )

    return described.stdout.strip()


def build_share_git(platform):
    if platform != HANDOFF_PLATFORM:
        raise SystemExit(
            f"hand-off scripts only exist for {HANDOFF_PLATFORM}, not {platform}"
        )

    pack_path = DIST / f"microdrop-prod-git-slim-{platform}.tar"
    pixi_pack_version = read_pack_info(pack_path)

    folder = DIST / "share" / FOLDER_NAME

    if folder.exists():
        # A clone's pack files are read-only on Windows; clear the flag so
        # rmtree can delete them.
        shutil.rmtree(folder, onexc=lambda _func, path, _exc: _force_remove(path))

    folder.mkdir(parents=True)
    version = clone_microdrop(folder / "microdrop")

    for script in SCRIPTS:
        write_windows_text(folder / script, (TEMPLATES / script).read_text())

    title = "MicroDrop for Windows (64-bit) - git edition"
    readme = (
        (TEMPLATES / "README.txt")
        .read_text()
        .format(
            title=title,
            title_rule="=" * len(title),
            pack_name=pack_path.name,
            version=version,
        )
    )
    write_windows_text(folder / "README.txt", readme)

    shutil.copy2(pack_path, folder / pack_path.name)
    shutil.copy2(fetch_pixi_unpack(pixi_pack_version), folder / "pixi-unpack.exe")

    models = folder / "models"
    models.mkdir()

    for blob in collect_model_blobs(DEFAULT_AI_MODEL):
        shutil.copy2(blob, models / blob.name)

    zip_path = DIST / f"share-microdrop-git-{version}-{platform}.zip"

    # Fastest deflate level, as for the wheel hand-off: the payload is mostly
    # already-compressed package archives.
    with zipfile.ZipFile(
        zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1
    ) as archive:
        for path in sorted(folder.rglob("*")):
            archive.write(path, Path(FOLDER_NAME) / path.relative_to(folder))

    print(f"folder: {folder}")
    print(f"zip:    {zip_path} ({zip_path.stat().st_size / 1e6:.0f} MB)")


def _force_remove(path):
    Path(path).chmod(0o700)
    Path(path).unlink()


if __name__ == "__main__":
    build_share_git(sys.argv[1])
