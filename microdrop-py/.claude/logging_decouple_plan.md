# Plan: Decouple the protocol-tree logging service + dock pane

Goal: remove cross-plugin coupling and code-style anti-patterns from the
`pluggable_protocol_tree` logging feature, per the repo conventions
(decouple via app_globals / dramatiq; HasTraits + traits.api; constants in
`consts.py`; no Qt in service/model layers; no imports inside functions).

Scope: `pluggable_protocol_tree` (logging service + dock pane and what they
touch). One minimal, justified change in `device_viewer` is required as the
"owner publishes" enabler (see Decision D1).

## Anti-patterns found (from the sweep)

1. `views/dock_pane.py:43-61` `_logging_device_context()` — reaches into the
   **device_viewer dock pane's model** via `get_dock_pane("device_viewer.dock_pane")`
   to read `electrodes.channel_electrode_areas_scaled_map` and
   `electrodes.svg_model.filename`. Also imports `LoggingDeviceContext` inside the closure.
2. `services/logging/controller.py` — runtime cross-plugin / Qt / lazy imports:
   - `_default_settling_provider` imports `protocol_grid.preferences.ProtocolPreferences`.
   - `_qtimer_flush_scheduler` imports `pyface.qt.QtCore.QTimer` (Qt in a service layer — forbidden).
   - `_get_app_globals` lazily imports `get_microdrop_redis_globals_manager` (non-canonical).
   - `MediaCaptureMessageModel` imported inside two functions.
   - Module-local constants `_TIME_FMT`, `_MEDIA_CAPTURES_KEY`, inline `"%Y%m%d_%H%M%S"`, inline `3.0`.
   - `ProtocolLoggingController` is a plain class holding mutable state.
3. `services/logging/ingestion.py` — `LoggingIngestion` is a plain class holding mutable state.
4. `services/logging/reporting.py` — in-function imports (`plotly`, `microdrop_utils.plotly_helpers`,
   `LoggingPersistence`); inline `"%Y%m%d_%H%M%S"` at line 319.
5. `services/logging/models.py` — `LoggingDeviceContext` is a `@dataclass`, not HasTraits.

## Decisions

- **D1 (device_viewer enabler):** the report heatmap loads the device SVG by
  path (`reporting._heatmap` → `create_plotly_svg_dropbot_device_heatmap(str(svg), ...)`),
  but only the SVG *stem* is in app_globals today (`"microdrop.device_svg.name"`).
  Add `DEVICE_SVG_PATH_KEY = "microdrop.device_svg.path"` to `device_viewer/consts.py`
  (+ `APP_GLOBALS_KEYS`) and publish the **full path** alongside the stem in
  `device_viewer/models/main_model.py`. This is the only out-of-`pluggable_protocol_tree`
  change; it is the "owner publishes" half that lets the dock pane stop reaching into the DV pane.
- **D2 (app_globals access):** bind the manager at **module level**
  (`app_globals = get_microdrop_redis_globals_manager()`) in `controller.py` and `dock_pane.py`,
  matching the canonical idiom (~16 modules). Keep operation-level `try/except` around the
  media reset/drain so the feature degrades gracefully without Redis (tests/headless).
  Remove the `_get_app_globals()` helper.
- **D3 (settling time):** remove the protocol_grid reference from PPT **entirely** (not just the
  service). The controller's default `settling_provider` reads
  `app_globals.get(LOGS_SETTLING_TIME_S_KEY, DEFAULT_SETTLING_TIME_S)`. The pane does NOT inject a
  pref reader (only renames its `controller._settling_provider()` call to `controller.settling_provider()`).
  Implication: until protocol_grid mirrors `logs_settling_time_s` to app_globals (out-of-scope
  follow-up — the "owner publishes" half), the settling time uses the 3.0 default — identical to
  today's default, differing only if a user customised the pref. Chosen over touching protocol_grid
  to keep the PR scoped to PPT (+ the unavoidable device_viewer svg enabler in D1).
- **D4 (flush scheduler):** remove the Qt `_qtimer_flush_scheduler` from the service. The default
  becomes a Qt-free `threading.Timer(settling, _flush)` scheduler (respects the settling delay).
  The pane keeps injecting its real `_schedule_flush_with_progress` (Qt) — unchanged.
- **D5 (media model):** `MediaCaptureMessageModel` is a shared pydantic **message schema**
  (used by protocol_grid too) — importing it is the pub/sub contract, not a forbidden reach.
  Hoist the two in-function imports to module top.
- **D6 (constants):** create `services/logging/consts.py` with `TIME_FMT`, `RUN_TIMESTAMP_FMT`,
  `MEDIA_CAPTURES_KEY`, `LOGS_SETTLING_TIME_S_KEY`, `DEFAULT_SETTLING_TIME_S`. Import the
  device_viewer app_globals key constants (`CHANNEL_AREAS_KEY`, `DEVICE_SVG_PATH_KEY`,
  `LIQUID/FILLER_CAPACITANCE_KEY`) from `device_viewer.consts` (constants-only reuse — sanctioned).
- **D7 (HasTraits):** convert the **stateful** classes — `ProtocolLoggingController`,
  `LoggingIngestion`, `LoggingDeviceContext` — to `traits.api.HasTraits` (class-level traits,
  `traits_init`, `_x_default`). `LoggingPersistence`/`LoggingReport` are stateless static-method
  utilities — leave as-is.

## Behaviour changes

- Channel areas + SVG path now come from app_globals instead of the live DV model. The DV publishes
  both already (channel areas) / after D1 (svg path), so behaviour is preserved. Channel-area keys are
  JSON-stringified in Redis → converted back to `int` when building the context (matches `on_actuation`'s
  `int(ch)` lookup and the test's int-keyed context).
- Settling time: identical default (3.0). Production still reads the live pref (via the pane, D3).

## Test impact

`tests/test_logging_controller.py`: the two media tests monkeypatch `controller._get_app_globals`;
switch them to `monkeypatch.setattr(ctrl_mod, "app_globals", fake_globals)` (D2). All other tests
construct `ProtocolLoggingController(settling_provider=..., flush_scheduler=..., completion_callback=...)`
with no-underscore kwargs and read `_ingestion`/`_flush`/`all_report_paths` — all preserved by the
HasTraits trait names.

## Files

1. `device_viewer/consts.py` — add `DEVICE_SVG_PATH_KEY` (+ APP_GLOBALS_KEYS).  [D1]
2. `device_viewer/models/main_model.py` — publish full svg path.  [D1]
3. `pluggable_protocol_tree/services/logging/consts.py` — NEW.  [D6]
4. `pluggable_protocol_tree/services/logging/models.py` — LoggingDeviceContext → HasTraits.  [D7]
5. `pluggable_protocol_tree/services/logging/ingestion.py` — LoggingIngestion → HasTraits.  [D7]
6. `pluggable_protocol_tree/services/logging/controller.py` — HasTraits, module app_globals, hoist
   imports, consts, decoupled settling, threading flush default.  [D2-D7]
7. `pluggable_protocol_tree/services/logging/reporting.py` — hoist imports, RUN_TIMESTAMP_FMT.  [D6]
8. `pluggable_protocol_tree/views/dock_pane.py` — hoist import, app_globals reads.  [D1,D2]
9. `pluggable_protocol_tree/views/protocol_tree_pane.py` — inject pref-reading settling_provider.  [D3]
10. `pluggable_protocol_tree/tests/test_logging_controller.py` — monkeypatch `app_globals`.  [D2]
11. `.claude/skills/microdrop-conventions/SKILL.md` — persist conventions.

## Out-of-scope follow-ups (noted, not done)

- Mirror `protocol_grid` `logs_settling_time_s` preference to app_globals so even the pane reads it
  decoupled (then drop the pane's ProtocolPreferences import).
- Promote `MEDIA_CAPTURES_KEY` into `device_viewer.consts`/`APP_GLOBALS_KEYS` and migrate the
  camera-writer + legacy `protocol_data_logger` literal users to it.
