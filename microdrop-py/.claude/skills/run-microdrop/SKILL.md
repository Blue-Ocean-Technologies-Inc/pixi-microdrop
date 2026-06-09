---
name: run-microdrop
description: Launch MicroDrop application with component validation — checks pixi env, Redis, backend, and frontend
disable-model-invocation: true
---

## Current State
- Pixi env: !`cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi info 2>&1 | head -10`
- Available tasks: !`cd C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py && pixi task list 2>&1`

## Steps

1. Verify pixi environment:
   ```
   cd microdrop-py
   pixi run python -c "import PySide6; print(f'PySide6 {PySide6.__version__}')"
   pixi run python -c "import redis; print('Redis client OK')"
   ```

2. If $ARGUMENTS contains "backend":
   - Start Redis: `pixi run run_redis` (background)
   - Start backend only: `pixi run microdrop-backend`

3. If $ARGUMENTS contains "frontend":
   - Start frontend only: `pixi run microdrop-frontend`

4. Otherwise (full stack):
   - Start Redis: `pixi run run_redis` (background)
   - Start full app: `pixi run microdrop`

5. Report any startup errors with diagnostic info
