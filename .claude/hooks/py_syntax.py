# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PostToolUse check for Edit|Write: byte-compile any edited Python file.

A syntax error is fed straight back so it gets fixed in the same turn. This is
the cheap half of the project's standard verification (py_compile + ruff on
touched files); ruff stays manual because legacy files are not yet ruff-clean.
"""

# Standard library imports.
import json
import py_compile
import sys


def main():
    payload = json.load(sys.stdin)
    path = payload.get("tool_input", {}).get("file_path", "")

    if not path.endswith(".py"):
        return

    try:
        py_compile.compile(path, doraise=True)
    except OSError:
        return  # file removed or unreadable; nothing to check
    except py_compile.PyCompileError as error:
        json.dump(
            {
                "decision": "block",
                "reason": f"py_compile failed for {path}:\n{error.msg}",
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()
