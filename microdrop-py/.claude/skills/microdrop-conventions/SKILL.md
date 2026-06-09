---
name: microdrop-conventions
description: Envisage/Traits/PySide6 code conventions for MicroDrop. Apply when writing or reviewing code in this project.
user-invocable: false
---

## Architecture
- Three-layer, message-driven: Frontend (PySide6/Qt6) <-> Message Server (Redis/Dramatiq) <-> Backend (DropBot Controller)
- Entire app is plugin-based using Envisage framework
- Plugins defined in `plugin_consts.py` — REQUIRED, FRONTEND, BACKEND categories

## Model & State Patterns
- Models use `traits.api.HasTraits` with typed trait declarations, NOT plain Python classes
- Use `@observe("trait_name")` for reactive updates, NOT property setters
- Trait defaults via `_trait_name_default()` method pattern
- State changes propagate through trait observation, not manual callbacks

## Service Patterns
- Services implement `@provides(IServiceInterface)` decorator from Envisage
- Service interfaces defined in `interfaces/i_*.py` using `traits.api.Interface`
- Services receive model via dependency injection, NOT global state

## Messaging Patterns
- Pub/sub via `publish_message(topic=CONST, message=...)` through Dramatiq/Redis
- Topic constants defined in module `consts.py` files
- MQTT-style topic matching for subscriptions

## UI Patterns
- Views use PySide6 widgets or Pyface TraitsUI views
- Qt layouts (QVBoxLayout, QHBoxLayout, QFormLayout) for widget arrangement
- Collapsible sections use custom GroupBox patterns

## Naming Conventions
- Interfaces: `I` prefix (IMainModel, IRouteExecutionService)
- Constants: UPPER_SNAKE_CASE in `consts.py` per module
- Trait defaults: `_trait_name_default()` method
- Observers: `_on_<event>()` or `_<trait_name>_change()`
- Plugins: `<module_name>.plugin.Plugin` class

## Forbidden Patterns
- Never import Qt directly in service/model layers — only in views
- Never use plain instance variables for state — always use Traits
- Never publish messages outside Dramatiq workers in backend code
- Never use `exec()` for PySide6 dialogs — use `show()` with timeout instead
- Never modify `pixi.lock` directly — use `pixi add` commands
