---
name: microdrop-conventions
description: Envisage/Traits/PySide6 code conventions for MicroDrop. Apply when writing or reviewing code in this project.
user-invocable: false
---

> The CANONICAL style guide is `microdrop-py/src/AGENTS.md` — environment,
> import sections, Traits typing, naming, docstrings, error handling, and
> the architecture rules (MVC split, TraitsUI first, decoupling). Read it
> first; this skill carries only the working directives NOT covered there.
> Apply all of it PROACTIVELY while writing new code — it is not a cleanup
> checklist to retrofit later. The user runs periodic directive sweeps over
> PRs; code that already follows them passes.

## Whitespace Inside Function Bodies (strong maintainer preference)
Function bodies are aired out so their shape reads at a glance. A body with no
blank lines is a defect even when ruff passes. Apply while writing, never as a
later pass:
- Blank line BEFORE every `if` / `for` / `while` / `try` / `with` that follows
  other statements at the same level, and AFTER the block ends before the next
  outer-level statement.
- Blank line between the setup chunk (assignments, unpacking) and the work that
  uses it, and before the final `return`.
- Inside a long block, one blank line between sub-steps; a comment introducing
  a step stays glued to that step, the gap goes above the comment.
- A guard clause after the docstring is its own chunk (blank line after it).
- Only two- or three-line bodies are exempt.

## Service Patterns
- Services implement `@provides(IServiceInterface)` decorator from Envisage
- Service interfaces defined in `interfaces/i_*.py` using `traits.api.Interface`
- Services receive model via dependency injection, NOT global state

## Plugin Decoupling (inter-plugin communication)
- Plugins MUST NOT reference other plugins directly. Forbidden: reaching into
  another plugin's pane/model (`window.get_dock_pane("other.dock_pane").model...`),
  or importing/instantiating another plugin's classes/preferences at runtime.
- Communicate strictly via Dramatiq topics, OR read shared state from the
  Redis-backed app_globals (`get_microdrop_redis_globals_manager()`).
- "Owner publishes": the plugin that owns a piece of data publishes it to
  app_globals (or a topic); consumers READ it — they never reach back for it.
  app_globals key constants live in the owning plugin's `consts.py`, aggregated
  into `APP_GLOBALS_KEYS`. Importing those key constants cross-plugin is OK
  (constants only); importing message-schema models for a topic payload is OK
  (it is the pub/sub contract).
- Bind the app_globals manager once at MODULE level
  (`app_globals = get_microdrop_redis_globals_manager()`); the proxy connects
  lazily. Wrap reads/writes that must tolerate no-Redis (tests/headless) in
  `try/except`. Note Redis JSON-stringifies dict keys (e.g. int channel ids
  round-trip to str) — convert back at the read site.

## Constants & consts.py
- Subpackages carry their OWN `consts.py` rather than inlining module-level
  magic constants/strings; name distinct formats distinctly.
- NEVER define a constant mid-file (e.g. a frozenset between two methods in a
  1500-line view). Constants go in the package `consts.py` (or, for tiny
  single-consumer values, at the very top of the module below the imports).
- One constant, ONE name. Never re-export or `import X as Y`-alias a
  constant under a different (especially shorter/vaguer) name — every
  consumer imports it from the owner's `consts.py` under its original,
  descriptive name (e.g. `DEFAULT_LOGS_SETTLING_SECONDS`, never aliased
  to `DEFAULT_SETTLING_TIME_S`).
- Never introduce a NEW constant or variable when an existing one already
  expresses the value. The pyface dialogs (`confirm()` and the other
  `pyface_wrapper` dialogs) already return `YES` / `NO` / `CANCEL` — wrappers
  return that result directly and callers compare against those codes; do
  not mint parallel decision constants (a `PROCEED`/`CANCEL` pair mapping
  1:1 onto them was reviewed and removed). Same for locals: return a call's
  result directly rather than staging it in a variable first. Same for
  thin wrapper methods: a helper whose whole body is a one-line idiom
  (e.g. `x or cls()`) gets inlined at its call sites — dedup earns a
  shared helper only when the logic is more than an idiom.

## Helper Function Placement
- Generic, reusable helpers do NOT live as module-level functions inside view
  or service files. Move them to `microdrop_utils/` — find the existing module
  that fits the category first (`decorators.py` for decorators,
  `pyside_helpers.py`, `pyface_helpers.py`, `preferences_UI_helpers.py`,
  `json_helpers.py`, ...); create a new aptly-named module only when none fit.
- Helpers that merely derive a value from a model object belong ON that model
  class as a method (e.g. dotted-path display id = `row.dotted_path()` on
  `BaseRow`, not a free `_dotted_path(row)` floating in a view module).
- One copy only: if two modules need the same helper, that is the signal it
  belongs in `microdrop_utils` or on the shared model — never duplicate it.

## Plugin Standalone Rule (protocol_grid vs pluggable_protocol_tree)
- protocol_grid (legacy) and pluggable_protocol_tree must each be fully
  functional when loaded ALONE. Never make one import from / re-export through
  the other. Ported code gets its own copy + protocol_tree-scheme names (e.g.
  `protocol_tree_tab`, id `microdrop.protocol_tree.preferences`); protocol_grid
  stays untouched until PPT-9 deletes it.

## Views
- AGENTS.md owns the TraitsUI-first and MVC rules. The free standalone
  harness they enable: `model.edit_traits()` / `configure_traits()` runs any
  view against just its model — use it to prototype and test views alone.

## Naming Supplements (beyond AGENTS.md)
- Trait defaults: `_trait_name_default()` method pattern
- Observers: `_on_<event>()` or `_<trait_name>_change()`
- Plugins: `<module_name>.plugin.Plugin` class

## Forbidden Patterns
- Never import Qt directly in service/model layers — only in views. Inject any
  Qt-aware collaborator (e.g. a flush scheduler) from the view; give services a
  Qt-free default (e.g. `threading.Timer`).
- Never use plain instance variables for state — always use Traits. Convert
  STATEFUL classes to `HasTraits` (class-level trait declarations, `traits_init`
  in place of `__init__`, `_x_default` methods). Stateless utility classes
  (only static/class methods) stay plain.
- Never import inside functions to dodge a dependency — hoist to module top, or
  remove the dependency by decoupling (see Plugin Decoupling).
- Never reach into another plugin (see Plugin Decoupling).
- Never publish messages outside Dramatiq workers in backend code
- Never use `exec()` for PySide6 dialogs — use `show()` with timeout instead
- Never modify `pixi.lock` directly — use `pixi add` commands
- Never bare `except: pass` and never `print()` for errors — catch
  `Exception` only and log it (`logger.debug(...)` for tolerated no-Redis
  paths, `logger.warning(...)` otherwise, `exc_info=True` when the stack
  matters).
