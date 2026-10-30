# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fill in the ``channel`` of package records that pixi-unpack left null.

pixi-unpack writes every ``conda-meta/*.json`` record with ``"channel":
null``; micromamba refuses to read such a record. The channel is set to the
one the package was installed from, the package URL minus its subdir and
file name. apply-update.bat runs this with the environment's own Python,
so it is standard library only.

Usage: python fix-conda-meta.py <env>/conda-meta
"""

# Standard library imports.
import json
import sys
from pathlib import Path


def fix_conda_meta(conda_meta):
    """Set a null ``channel`` from the record's URL; return how many changed."""

    fixed = 0

    for record_path in conda_meta.glob("*.json"):
        record = json.loads(record_path.read_text(encoding="utf-8"))

        if record.get("channel") is not None:
            continue

        record["channel"] = record.get("url", "").rsplit("/", 2)[0]
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        fixed += 1

    return fixed


if __name__ == "__main__":
    fixed = fix_conda_meta(Path(sys.argv[1]))

    if fixed:
        print(f"Prepared {fixed} package records for the update.")
