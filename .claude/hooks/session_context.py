# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""SessionStart / PostCompact context: branch and working-tree state of both repos.

Compaction is where the model loses track of which branch it is on and what
is staged. Re-inject a compact summary for the launcher and the submodule at
session start and after every compaction.
"""

# Standard library imports.
import json
import os
import subprocess
import sys


def git(repo, *args):
    try:
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True, timeout=10
        ).stdout.rstrip()
    except (OSError, subprocess.SubprocessError):
        return ""


def summarize(name, repo):
    status = git(repo, "status", "--short", "--branch")

    if not status:
        return f"{name}: not a git repo or git unavailable"

    lines = status.splitlines()
    head = lines[0].removeprefix("## ")
    entries = lines[1:]
    untracked = sum(1 for line in entries if line.startswith("??"))
    tracked = [line for line in entries if not line.startswith("??")]
    staged = [line[3:] for line in tracked if line[0] not in " ?"]
    summary = (
        f"{name}: {head}; {len(tracked)} tracked changes, {len(staged)} staged, "
        f"{untracked} untracked"
    )

    if staged:
        summary += "\n  staged: " + ", ".join(staged)

    return summary


def main():
    payload = json.load(sys.stdin)
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd", ".")
    submodule = os.path.join(root, "microdrop-py", "src")
    parts = [summarize("launcher (pixi-microdrop)", root)]

    if os.path.isdir(submodule):
        parts.append(summarize("submodule (microdrop-py/src)", submodule))

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": payload.get("hook_event_name", "SessionStart"),
                "additionalContext": "Repo state:\n" + "\n".join(parts),
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
