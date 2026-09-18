# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Remove the intermediate build output from ``dist/``.

The pack pipeline leaves several GB behind: the full and slim packs, the
injected wheels, and the unzipped hand-off folders. Only the hand-off zips
are worth keeping, plus the download cache that makes the next pack fast.

Usage: python tools/clean_dist.py [dist_dir]
"""

# Standard library imports.
import shutil
import sys
from pathlib import Path

DIST = Path(__file__).parent.parent / "dist"

#: What survives a clean: the hand-off zips and the pixi-pack download cache.
KEEP_GLOB = "share-microdrop-*.zip"
KEEP_DIRS = {"pack-cache"}


def clean_dist(dist):
    """Delete everything in `dist` except the hand-off zips and the cache."""

    if not dist.is_dir():
        print(f"nothing to clean: {dist} does not exist")
        return

    freed = 0

    for entry in sorted(dist.iterdir()):
        if entry.name in KEEP_DIRS or entry.match(KEEP_GLOB):
            continue

        if entry.is_dir():
            size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            shutil.rmtree(entry)
        else:
            size = entry.stat().st_size
            entry.unlink()

        freed += size
        print(f"removed {entry.relative_to(dist)} ({size / 1e6:.0f} MB)")

    print(f"freed {freed / 1e9:.1f} GB; kept:")

    for entry in sorted(dist.iterdir()):
        print(f"  {entry.name}")


if __name__ == "__main__":
    clean_dist(Path(sys.argv[1]) if len(sys.argv) > 1 else DIST)
