# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PreToolUse guard for Edit|Write: refuse edits to generated or locked files.

Reads the hook payload from stdin and prints a deny decision when the target
path is one that must never be hand-edited (lockfiles, generated changelogs,
caches, device SVG assets, the pixi env).
"""

# Standard library imports.
import json
import re
import sys

PROTECTED = re.compile(
    r"(pixi\.lock$|/__pycache__/|/device_svg_files/|/redis_settings\.json$"
    r"|/\.pixi/|/CHANGELOG\.md$)"
)


def main():
    payload = json.load(sys.stdin)
    path = payload.get("tool_input", {}).get("file_path", "").replace("\\", "/")

    if not PROTECTED.search(path):
        return

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{path} is generated or locked; never edit it by hand "
                    "(pixi.lock via `pixi install`, CHANGELOG.md via commitizen)."
                ),
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
