# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Strip build-toolchain packages out of a pixi-pack archive.

The DropBot driver chain (dropbot -> base-node-rpc -> clang-helpers,
conda-helpers) declares the firmware code-generation toolchain as run
dependencies: three clang distributions and git, ~560 MB of the download and
~2 GB installed. A packed install only talks to the instrument; it never
generates or builds firmware.

conda has no way to exclude a transitive dependency, so the packages are
removed from the finished pack instead: their archives, their repodata
records, and their environment.yml pins. pixi-unpack installs what the
pack's channel lists without re-solving, so the dependents install fine.

The small Python helpers (clang_helpers, conda_helpers, nanopb_helpers,
pypandoc) are imported at module level by the driver and must stay; only the
binaries behind them are stripped.

Usage: python tools/prune_pack.py <pack.tar> <slim.tar>
"""

# Standard library imports.
import io
import json
import re
import sys
import tarfile

#: Conda package names to strip, matched against the repodata record name.
STRIPPED_PACKAGE_PATTERNS = (
    r"clang",
    r"clangdev",
    r"clangxx",
    r"clang-\d+",
    r"clang-tools",
    r"libclang",
    r"libclang\d+",
    r"libclang-cpp[\d.]*",
    r"compiler-rt\d*(_.+)?",
    r"git",
)

STRIPPED_PACKAGE_REGEX = re.compile(rf"^({'|'.join(STRIPPED_PACKAGE_PATTERNS)})$")

REPODATA_SECTIONS = ("packages", "packages.conda")


def strip_repodata(repodata):
    """Remove stripped packages from a repodata dict, in place.

    Returns
    -------
    dict
        Archive filename -> package name, for every record removed.
    """

    removed = {}

    for section in REPODATA_SECTIONS:
        records = repodata.get(section, {})

        for filename in list(records):
            name = records[filename]["name"]

            if STRIPPED_PACKAGE_REGEX.match(name):
                removed[filename] = name
                del records[filename]

    return removed


def strip_environment_yml(text, package_names):
    """Drop the ``- name=version=build`` pins of the given packages."""

    kept_lines = []

    for line in text.splitlines(keepends=True):
        pin = line.strip().removeprefix("- ")

        if pin.split("=")[0] in package_names:
            continue

        kept_lines.append(line)

    return "".join(kept_lines)


def add_bytes(tar, member, data):
    member.size = len(data)
    tar.addfile(member, io.BytesIO(data))


def prune_pack(source_path, slim_path):
    # Pass 1: the repodata files decide which archives go, and they can sit
    # anywhere in the tar relative to the archives they index.
    slim_repodata = {}
    removed_archives = {}

    with tarfile.open(source_path) as source:
        for member in source:
            if not member.name.endswith("/repodata.json"):
                continue

            repodata = json.load(source.extractfile(member))
            subdir = member.name.rsplit("/", 1)[0]

            for filename, name in strip_repodata(repodata).items():
                removed_archives[f"{subdir}/{filename}"] = name

            slim_repodata[member.name] = json.dumps(repodata).encode()

    removed_names = set(removed_archives.values())
    removed_bytes = 0

    # Pass 2: copy everything else across.
    with tarfile.open(source_path) as source, tarfile.open(slim_path, "w") as slim:
        for member in source:
            if member.name in removed_archives:
                removed_bytes += member.size
                continue

            if member.name in slim_repodata:
                add_bytes(slim, member, slim_repodata[member.name])

            elif member.name == "environment.yml":
                text = source.extractfile(member).read().decode()
                stripped_text = strip_environment_yml(text, removed_names)
                add_bytes(slim, member, stripped_text.encode())

            elif member.isfile():
                # pixi-pack's --use-cache keeps a download that was cut short
                # as an empty file and packs it; pixi-unpack then fails on the
                # user's machine, so catch it here.
                if member.size == 0:
                    raise ValueError(
                        f"{member.name} is empty - delete it from "
                        f"dist/pack-cache and re-run the pack"
                    )

                slim.addfile(member, source.extractfile(member))

            else:
                slim.addfile(member)

    for archive in sorted(removed_archives):
        print(f"stripped {archive}")

    print(f"removed {len(removed_archives)} packages, {removed_bytes / 1e6:.0f} MB")


if __name__ == "__main__":
    prune_pack(sys.argv[1], sys.argv[2])
