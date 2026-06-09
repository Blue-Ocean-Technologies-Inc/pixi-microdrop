---
name: gen-test
description: Generate pytest tests for a module following project test conventions (Redis fixtures, conftest, common utilities)
disable-model-invocation: true
---

Generate tests for: $ARGUMENTS

## Reference Patterns
- Conftest fixtures: !`cat C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src/examples/tests/conftest.py`
- Common utilities: !`head -50 C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src/examples/tests/common.py`
- Existing tests: !`ls C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src/examples/tests/test_*.py`

## Steps

1. Read the source module to understand functions/classes to test
2. Determine test category:
   - **Unit tests** — Pure logic, no external dependencies
   - **Redis tests** — Needs Redis server (use conftest.py fixtures, place in `tests_with_redis_server_need/`)
   - **Hardware tests** — Needs DropBot connection (place in `tests_with_dropbot_connection_need/`)
3. Generate test file at `src/examples/tests/test_<module_name>.py`
4. Follow these conventions:
   - Import fixtures from `conftest.py` (redis_server, worker, etc.)
   - Import helpers from `common.py` (proxy_context, redis_client, etc.)
   - Use descriptive test names: `test_<function>_<scenario>`
   - Group related tests in classes: `class TestClassName:`
   - Use `pytest.mark.parametrize` for data-driven tests
   - Include docstrings on complex test functions
5. Run and verify: `cd microdrop-py && pixi run pytest src/examples/tests/test_<module>.py -v`
