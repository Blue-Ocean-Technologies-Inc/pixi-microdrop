# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PreToolUse guard for Bash|PowerShell: enforce the repo's git and test rules.

Denies:
- moving the submodule pointer with git checkout/reset/submodule on src paths
- bulk staging or committing (`git add -A|--all|.`, `git commit -a|--all|-am`);
  commits must be scoped with explicit pathspecs
- staging firmware images (firmware_*.zip, *.hex, *.uf2), even with `-f`
- committing on main/master; work happens on a branch per issue
- skipping hooks or signing (`--no-verify`, `commit.gpgsign=false`, hooksPath)
- repo-wide ruff or pre-commit runs; adoption is incremental, per touched file
- committing or pushing while fine-edits mode is on (flag set by prompt_flags)

Asks:
- any pytest invocation; the test suite runs only when the user asks for it

Informs:
- on `git commit`, injects the staged file list so a commit never sweeps in
  files that were staged earlier for a different concern
"""

# Standard library imports.
import json
import os
import re
import subprocess
import sys
import tempfile

SUBMODULE_POINTER = re.compile(
    r"git (checkout|reset|submodule).*(microdrop-py/src|\bsrc/)"
)
BULK_ADD = re.compile(
    r"git add\b(?=.*(\s-A\b|\s--all\b|\s-[a-zA-Z]*A[a-zA-Z]*\b|\s\.(\s|$)))"
)
BULK_COMMIT = re.compile(
    r"git commit\b(?=.*(\s-a\b|\s--all\b|\s-[a-zA-Z]*a[a-zA-Z]*\b))"
)
FIRMWARE_ADD = re.compile(r"git add\b.*(firmware_[^\s]*\.zip|\.hex\b|\.uf2\b)")
SKIP_HOOKS = re.compile(
    r"--no-verify\b|commit\.gpgsign=false|--no-gpg-sign\b|core\.hooksPath"
)
RUFF_RUN = re.compile(r"\bruff (format|check)\b([^|;&]*)")
PRECOMMIT_ALL = re.compile(r"\bpre-commit run\b[^|;&]*--all-files")
PYTEST = re.compile(r"(^|[\s;&|])(pytest|python -m pytest|pixi run pytest)\b")
COMMIT = re.compile(r"\bgit commit\b")
PUSH = re.compile(r"\bgit push\b")
LEADING_CD = re.compile(r'^\s*cd\s+"?([^"&;]+?)"?\s*(&&|;)')
# Heredoc bodies and quoted strings are data, not commands; drop them before
# matching so a commit message or grep pattern that mentions `git add -A` is
# not mistaken for one.
HEREDOC_BODY = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1\s*$", re.DOTALL | re.MULTILINE
)
QUOTED = re.compile(r"\"(?:\\.|[^\"\\])*\"|'[^']*'")
PROTECTED_BRANCHES = {"main", "master"}


def executable_text(command):
    """Return the command with heredoc bodies and quoted strings blanked out."""
    stripped = HEREDOC_BODY.sub("", command)

    return QUOTED.sub('""', stripped)


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def repo_dir(raw_command, cwd):
    match = LEADING_CD.match(raw_command)

    return match.group(1).strip() if match else cwd


def git(repo, *args):
    try:
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_wide_ruff(command):
    for match in RUFF_RUN.finditer(command):
        targets = [t for t in match.group(2).split() if not t.startswith("-")]

        if not targets or targets == ["."]:
            return True

    return False


def fine_edits_flag(session_id):
    return os.path.join(
        tempfile.gettempdir(), "claude-flags", f"{session_id}.fine-edits"
    )


def main():
    payload = json.load(sys.stdin)
    raw = payload.get("tool_input", {}).get("command", "")
    command = executable_text(raw)
    cwd = payload.get("cwd", ".")
    session_id = payload.get("session_id", "")
    result = None

    if SUBMODULE_POINTER.search(command):
        result = deny("Do not move the microdrop-py/src submodule pointer directly.")
    elif BULK_ADD.search(command) or BULK_COMMIT.search(command):
        result = deny(
            "Bulk staging is not allowed here: the working tree carries unrelated "
            "IDE work. Stage and commit with explicit pathspecs."
        )
    elif FIRMWARE_ADD.search(command):
        result = deny("Firmware images never go in git; they ship with the boards.")
    elif SKIP_HOOKS.search(command):
        result = deny(
            "Never skip git hooks or signing; fix the underlying issue instead."
        )
    elif repo_wide_ruff(command) or PRECOMMIT_ALL.search(command):
        result = deny(
            "Never run ruff or pre-commit repo-wide; the legacy codebase is brought "
            "clean incrementally. Run them on the files you touched."
        )
    elif PYTEST.search(command):
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    "pytest runs only when the user asks for it; the standard "
                    "check is py_compile + ruff on touched files."
                ),
            }
        }
    elif COMMIT.search(command) or PUSH.search(command):
        if session_id and os.path.exists(fine_edits_flag(session_id)):
            result = deny(
                "Fine-edits mode is on: no commits or pushes until the user turns "
                "it off."
            )
        elif COMMIT.search(command):
            result = commit_checks(raw, command, cwd)

    if result:
        json.dump(result, sys.stdout)


def commit_checks(raw, command, cwd):
    repo = repo_dir(raw, cwd)
    branch = git(repo, "branch", "--show-current")

    if branch in PROTECTED_BRANCHES:
        return deny(
            f"Never commit directly to {branch}; create a branch per issue first."
        )

    if "--amend" in command:
        return None

    staged = git(repo, "diff", "--cached", "--name-status")

    if not staged:
        return None

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"On branch {branch}. A commit takes the whole index. Currently "
                f"staged:\n{staged}\nIf any of these belong to a different "
                "concern, unstage them first."
            ),
        }
    }


if __name__ == "__main__":
    main()
