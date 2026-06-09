---
name: issue
description: Start working on a GitHub issue — creates branch in the src submodule, links context, sets up for PR
disable-model-invocation: true
---

## Issue Context
- Issue: !`cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src && gh issue view $ARGUMENTS`

## Current State
- Branch: !`cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src && git branch --show-current`
- Status: !`cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src && git status --short`

## Steps

1. Parse the issue number from $ARGUMENTS
2. Read the issue title, body, and labels
3. Determine branch prefix from issue type:
   - `feat/` for feature requests or enhancements
   - `fix/` for bug fixes
   - `bug/` for bug reports
   - `chore/` for maintenance tasks
4. Create branch in the submodule (src/):
   ```
   cd microdrop-py/src
   git checkout main
   git pull origin main
   git checkout -b <prefix>/<issue-number>-<short-description>
   ```
5. Summarize the issue requirements and propose an approach
6. Begin implementation following the commit convention:
   - `[feat]` for new features
   - `[fix]` for bug fixes
   - `[BUG]` for bug report fixes
   - `[chore]` for maintenance
