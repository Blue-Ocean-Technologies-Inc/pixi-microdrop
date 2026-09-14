# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PostToolUse check for Edit|Write: lint only the lines this edit added.

Scans the added lines of an edited Python file for the patterns AGENTS.md
bans in new code, plus a whitespace heuristic for the "air out function
bodies" rule. Legacy lines are never reported, which is what keeps the check
usable on files that are not yet ruff-clean. Findings are advisory context,
not a block.
"""

# Standard library imports.
import ast
import json
import os
import re
import subprocess
import sys

MAX_FINDINGS = 12
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
ENTHOUGHT_NON_API = re.compile(
    r"^\s*from (traits|traitsui|pyface|envisage|apptools)\.(?!qt\b)([\w.]+) import"
)
LINE_RULES = [
    (
        re.compile(r"^\s*(from|import) PySide6\b"),
        "import Qt through `from pyface.qt import QtCore, QtGui, QtWidgets`",
    ),
    (
        re.compile(r"\blogging\.getLogger\("),
        "use `get_logger(__name__)` from logger.logger_service",
    ),
    (
        re.compile(r"\bQMessageBox\b"),
        "user-facing dialogs go through microdrop_application.dialogs.pyface_wrapper",
    ),
    (
        re.compile(r"\blogger\.(debug|info|warning|error|exception|critical)\([^)]*%"),
        "f-strings in logger calls, not %-formatting",
    ),
    (re.compile(r"[\"']\.format\("), "f-strings, not .format()"),
    (
        re.compile(r"\.observe\("),
        "wire reactions with the @observe decorator, not imperative .observe()",
    ),
    (
        re.compile(r"\b(voltage|frequency)\w*\s*=\s*Float\("),
        "voltage and frequency are Int end-to-end, never Float",
    ),
    (
        re.compile(r"^\s*except\s*:\s*$|^\s*except\b[^:]*:\s*pass\s*$"),
        "never swallow exceptions silently; a bare except needs a comment",
    ),
    (
        re.compile(r"\bpublish_message\("),
        "raw publish_message is legacy; new topics use ValidatedTopicPublisher",
    ),
]
BLOCK_OPENERS = ("if ", "for ", "while ", "try:", "with ")
CONTINUATIONS = ("elif ", "else", "except", "finally", ")", "]", "}")
DEFINITIONS = ("def ", "async def ", "class ", "@")


def git(repo, *args):
    try:
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None


def added_line_numbers(path, total_lines):
    """Return the 1-based line numbers this edit introduced, or all if untracked."""
    repo = os.path.dirname(path)
    tracked = git(repo, "ls-files", "--error-unmatch", path)

    if tracked is None:
        return set()

    if tracked.returncode != 0:
        return set(range(1, total_lines + 1))

    diff = git(repo, "diff", "-U0", "--no-color", "HEAD", "--", path)

    if diff is None:
        return set()

    added = set()

    for line in diff.stdout.splitlines():
        match = HUNK.match(line)

        if match:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            added.update(range(start, start + count))

    return added


def short_function_ranges(source):
    """Line ranges of functions with bodies of three statements or fewer (exempt)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    ranges = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(node.body) <= 3:
                ranges.append((node.lineno, node.end_lineno))

    return ranges


def whitespace_findings(lines, added, exempt):
    findings = []

    for number in sorted(added):
        if number < 2 or number > len(lines):
            continue

        if any(start <= number <= end for start, end in exempt):
            continue

        line = lines[number - 1]
        text = line.strip()
        prev = lines[number - 2]
        prev_text = prev.strip()

        if not text or not prev_text:
            continue

        if text.startswith(("#",) + CONTINUATIONS + DEFINITIONS):
            continue

        if prev_text.startswith("#") or prev_text.endswith(
            (":", "(", "[", "{", ",", "\\")
        ):
            continue

        indent = len(line) - len(line.lstrip())
        prev_indent = len(prev) - len(prev.lstrip())

        if text.startswith(BLOCK_OPENERS) and prev_indent >= indent:
            findings.append((number, "blank line before this block"))
        elif indent < prev_indent:
            findings.append((number, "blank line after the block above ends"))
        elif text.startswith(("return", "raise ")) and prev_indent == indent:
            findings.append((number, "blank line before the return"))

    return findings


def pattern_findings(lines, added, source):
    findings = []
    traits_based = "from traits" in source or "import traits" in source

    for number in sorted(added):
        if number > len(lines):
            continue

        line = lines[number - 1]

        for pattern, advice in LINE_RULES:
            if pattern.search(line):
                findings.append((number, advice))

        match = ENTHOUGHT_NON_API.match(line)

        if match and not match.group(2).endswith("api"):
            findings.append(
                (number, "import Enthought packages from their .api modules")
            )

        if traits_based and line.lstrip().startswith(("def ", "async def ")):
            if re.search(r"\)\s*->|\w+\s*:\s*[A-Za-z_][\w.\[\], |]*\s*[,=)]", line):
                findings.append((number, "no PEP 484 annotations in traits-based code"))

    return findings


def main():
    payload = json.load(sys.stdin)
    path = payload.get("tool_input", {}).get("file_path", "")
    root = os.environ.get("CLAUDE_PROJECT_DIR", "")
    normalized = path.replace("\\", "/")

    if not path.endswith(".py") or "/.claude/" in normalized:
        return

    if root and not normalized.startswith(root.replace("\\", "/")):
        return

    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return

    lines = source.splitlines()
    added = added_line_numbers(path, len(lines))

    if not added:
        return

    findings = pattern_findings(lines, added, source)
    findings += whitespace_findings(lines, added, short_function_ranges(source))

    if not findings:
        return

    findings.sort()
    report = "\n".join(f"- L{n}: {advice}" for n, advice in findings[:MAX_FINDINGS])

    if len(findings) > MAX_FINDINGS:
        report += f"\n- ... {len(findings) - MAX_FINDINGS} more"

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"Convention check on the lines you just added to "
                    f"{os.path.basename(path)} (AGENTS.md):\n{report}"
                ),
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
