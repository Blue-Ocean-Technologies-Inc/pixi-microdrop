## Summary

Closes #369. Migrates the per-step **Force** display from the legacy `protocol_grid` plugin into a derived contributed column in the pluggable protocol tree.

Force is computed on demand from `row.voltage` (PPT-4) + a process-wide `CalibrationCache` populated by a Dramatiq listener on the existing `CALIBRATION_DATA` topic. The Qt model gains a small reactive-wiring extension that observes any column-declared row-trait dependencies and event sources, so the Force cell repaints automatically whenever voltage edits fire or the calibration cache updates — no `update_all_step_forces` walk, no manual refresh button.

## Design (locked in #369 issue body)

- **Compute path:** `ForceColumnModel.get_value(row)` reads `row.voltage` + `cache.capacitance_per_unit_area()`. Force is **not** stored on rows or persisted to JSON. The column entry still appears in `payload["columns"]` so files identify the contributing plugin.
- **Reactivity:** voltage edit → row-scoped `dataChanged`; `cache_changed` Event → column-wide `layoutChanged`. Generic infrastructure in `MvcTreeModel`, opt-in via `view.depends_on_row_traits` + `view.depends_on_event_source` / `_trait_name` declarations.
- **Subscription wiring:** production uses `ACTOR_TOPIC_DICT` + `actor_topic_routing` extension-point contribution — `MessageRouterPlugin.start()` does the subscription. No manual `add_subscriber_to_topic` in production code. Demos/tests use direct router calls (no `MessageRouterPlugin` in those lifecycles).
- **Naming policy:** actor named `calibration_data_listener` (no `pptN_` prefix). Convention going forward for all PPT plugins.
- **Persistence policy:** calibration is a current-device measurement, not protocol data — deliberately NOT persisted (a deviation from legacy `protocol_state.py:169-170`).
- **`force_math` helper extraction**: shared between the new column and `dropbot_status_and_controls.model._recalculate_force` — removes the only outbound dependency from `dropbot_status_and_controls` to `protocol_grid`, paving the way for PPT-9.

## What changed

| Layer | File(s) | Why |
|---|---|---|
| Topic constant | `device_viewer/consts.py`, `protocol_grid/consts.py`, `microdrop_utils/api.py` | Promote `CALIBRATION_DATA` to its canonical home (mirrors PPT-6 migration of the four `DEVICE_VIEWER_*` topics); back-compat re-export from `protocol_grid` until PPT-9. |
| Plugin scaffold | `dropbot_protocol_controls/consts.py`, `dropbot_protocol_controls/plugin.py` | Add `ACTOR_TOPIC_DICT` + `actor_topic_routing` extension contribution. First production listener in any `*_protocol_controls` plugin. |
| Math helpers | `dropbot_protocol_controls/services/force_math.py` | Pure functions `capacitance_per_unit_area` + `force_for_step`. Legacy parity verified to 1e-6 across a spread of (V, C/A) inputs. |
| Cache + actor | `dropbot_protocol_controls/services/calibration_cache.py` | `CalibrationCache(HasTraits)` singleton + `_on_calibration` Dramatiq actor (`calibration_data_listener`). Actor wraps JSON parse in `try/except` so malformed messages don't crash workers (lesson from #394). |
| Force column | `dropbot_protocol_controls/protocol_columns/force_column.py` | Read-only derived column. Declares `depends_on_row_traits = ["voltage"]` and `depends_on_event_*` for the Qt model to consume. |
| Reactive wiring | `pluggable_protocol_tree/views/qt_tree_model.py` | Observes column-declared dependencies on rows + cache events, emits `dataChanged` (per-row) and `layoutChanged` (column-wide cache events). Generic — reusable by any future derived column. |
| Plugin contribution | `dropbot_protocol_controls/plugin.py` | Add `make_force_column()` to `_contributed_protocol_columns_default`. |
| Status panel decoupling | `dropbot_status_and_controls/model.py` | Re-point `ForceCalculationService` import to new `force_math` helper. Removes the only outbound arrow from `dropbot_status_and_controls` to `protocol_grid`. |
| Demo | `dropbot_protocol_controls/demos/run_force_demo.py` | Opens 3 steps (75/100/120 V), publishes a fake `CALIBRATION_DATA` 500ms after window appears via `QTimer.singleShot`. All Force cells transition from blank to numeric values. |

**Not touched** (deferred to PPT-9): `protocol_grid/services/force_calculation_service.py` and `protocol_grid/services/volume_threshold_service.py` — the legacy service stays for now since `volume_threshold_service` still consumes it.

## Tests

- **Unit (newly added):** 22 `test_force_math` (legacy parity to 1e-6) + 8 `test_calibration_cache` (incl. malformed-input safety) + 9 `test_force_column` + 6 `test_qt_model_reactive_wiring` + 2 `test_force_reactivity` (integration) + 6 `test_persistence` (incl. round-trip recompute, calibration-not-in-JSON, cache-set-after-load).
- **Redis-backed integration:** `test_calibration_round_trip.py` — real publish → router → actor → cache mutation + `cache_changed` event; covers happy path + malformed-payload negative case.
- **Full regression sweep**: 210 tests pass across PPT-3/4/5/6 + PPT-7. One pre-existing flaky test (`test_run_hooks_fans_same_priority_in_parallel` — timing-sensitive) confirmed not a regression by stash-and-rerun on master.

## Follow-ups (filed as separate issues)

- **#399** — Property-trait support for derived columns. Would let `row.force` fire Traits change events automatically and let the view drop its manual dependency-declaration plumbing. Out of scope for PPT-7 to keep core changes minimal.
- **#400** — Drop `pptN_` prefixes from demo + test actor names (load-bearing in `_DEMO_PREFIXES` allowlist; needs coordinated rename).

## Test plan

- [ ] CI: 210 unit + 1 Redis integration test pass.
- [ ] Manual demo: `pixi run python -m dropbot_protocol_controls.demos.run_force_demo` opens window with 3 blank Force cells; ~500ms later all three populate (~4.2 / 7.5 / 10.8 mN/m for V=75/100/120 with C/A=1.5 pF/mm²).
- [ ] Voltage edit reactivity: change a voltage cell; the Force cell on the same row repaints to the new value within one frame.
- [ ] Save/load: save a 3-step protocol → reopen → Force cells recompute (calibration must still be set in cache, or values stay blank).
- [ ] No regression in PPT-4 voltage/frequency demo or PPT-6 video/capture/record demo.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
