---
name: new-plugin
description: Scaffold a new Envisage plugin module with standard directory structure, interfaces, models, services, and views
disable-model-invocation: true
---

Create a new Envisage plugin module named: $ARGUMENTS

## Current State
- Plugin registry: !`cat C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src/examples/plugin_consts.py`
- Existing plugins: !`ls -d C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src/*/plugin.py 2>/dev/null | head -20`

## Steps

1. Read an existing plugin for the pattern (e.g., `electrode_controller/`) to understand:
   - `plugin.py` structure (Plugin class, id, name, contributions)
   - Interface pattern (`interfaces/i_*.py`)
   - Model pattern (`models/*.py` with HasTraits)
   - Service pattern (`services/*.py` with @observe, @provides)
   - View pattern (`views/*.py` with PySide6/Pyface)

2. Create the module directory: `src/$ARGUMENTS/`

3. Create files following the established pattern:
   - `__init__.py`
   - `plugin.py` — Plugin class extending `envisage.plugin.Plugin` with `id`, `name`, `service_offers`, `contributions`
   - `consts.py` — Module constants and topic strings
   - `interfaces/` — `__init__.py` + `i_model.py` (trait interface)
   - `models/` — `__init__.py` + HasTraits model class
   - `services/` — `__init__.py` + service class with `@provides(IInterface)` and `@observe` handlers
   - `views/` — `__init__.py` + PySide6 view class (if this is a UI plugin)

4. Register the plugin in `examples/plugin_consts.py` under the appropriate category:
   - `REQUIRED_PLUGINS` for core functionality
   - `FRONTEND_PLUGINS` for UI-only plugins
   - `BACKEND_PLUGINS` for hardware/backend plugins

5. Validate imports: `pixi run python -c "from $ARGUMENTS.plugin import *; print('OK')"`