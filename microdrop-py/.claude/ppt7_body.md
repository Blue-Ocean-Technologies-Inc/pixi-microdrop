## Goal

Migrate the per-step **Force** display from the legacy `protocol_grid` plugin into a contributed column in the pluggable protocol tree. Force is a *derived* read-only value computed from per-step voltage + a global calibration pair — every time either input changes, every visible Force cell should reflect the new value immediately, with no manual "recompute all forces" pass.

## Force formula (unchanged from legacy)

`F = (C/A) × V² / 2` reported in **mN/m**, where:
- `V` is the per-step voltage (Volts) — owned by the **Voltage** column shipped in PPT-4 (`dropbot_protocol_controls`).
- `C/A` is `liquid_capacitance_over_area − filler_capacitance_over_area` (pF/mm²) — owned by `device_viewer`'s "Update Calibration" button, which republishes on the **`CALIBRATION_DATA`** topic (`ui/calibration_data`) any time its model's calibration traits change (`device_view_dock_pane.py:1128-1136`).

Returns `None` when calibration is incomplete, `voltage <= 0`, or `C/A <= 0` — same guards as today.

Reference implementation: [`src/protocol_grid/services/force_calculation_service.py`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/blob/main/src/protocol_grid/services/force_calculation_service.py) (the math we are lifting).

## Architecture — derived column, not stored

Force is **not** persisted on the row and **not** stored as a row trait. It is computed on demand by `ForceColumnModel.get_value(row)`, which reads `row.voltage` + the shared calibration cache. Rationale:

- A persisted force can drift out of sync with calibration on file reload.
- A computed `get_value` falls into `RowManager.table` automatically, so pandas slicing like `rm.table[rm.table.force > 5.0]` works for free with no extra wiring.
- `format_display(value, row)` formats `value` as `f"{value:.2f}"` (or `""` when `None`). Cell is read-only (matches legacy — see `protocol_grid_helpers.py:335-337`).

A deeper Traits integration — having `row.force` be a `Property` trait that fires change events automatically — is captured as a follow-up in **#399**. PPT-7 stays on the simpler `get_value` path; the view does the cell-repaint plumbing manually for now.

### Reactive update triggers (the "dynamic and fast" requirement)

| Input changes | What fires the repaint |
|---|---|
| Voltage cell on row N edited | Traits `observe("voltage")` on row N → Qt model emits `dataChanged` for the Force cell on row N. (Single cell, sub-millisecond.) |
| `CALIBRATION_DATA` message arrives | The `calibration_data_listener` Dramatiq actor updates the shared `CalibrationCache` HasTraits singleton; its `cache_changed` Event fires; the column view's listener emits `dataChanged` on the Force column for every row. (One pass over visible rows; no DataFrame rebuild.) |
| New step added / step deleted | Qt model already invalidates affected rows; `get_value` recomputes naturally. |

No polling, no per-tick scan, no `update_all_step_forces_in_model` walk. Each input has exactly one observer → one repaint signal.

### Calibration cache + listener wiring

The calibration cache lives in `dropbot_protocol_controls.services.calibration_cache` — colocated with the Force column that consumes it. The Dramatiq actor is registered at module-import time:

```python
# dropbot_protocol_controls/services/calibration_cache.py
class CalibrationCache(HasTraits):
    liquid_capacitance_over_area = Float(0.0)   # pF/mm^2
    filler_capacitance_over_area = Float(0.0)
    cache_changed = Event

    def capacitance_per_unit_area(self):
        d = self.liquid_capacitance_over_area - self.filler_capacitance_over_area
        return d if d > 0 else None

cache = CalibrationCache()  # module-level singleton

@dramatiq.actor(actor_name=CALIBRATION_LISTENER_ACTOR_NAME, queue_name="default")
def _on_calibration(message: str, topic: str, timestamp: float = None):
    payload = json.loads(message)
    cache.trait_set(
        liquid_capacitance_over_area=float(payload["liquid_capacitance_over_area"]),
        filler_capacitance_over_area=float(payload["filler_capacitance_over_area"]),
    )
    cache.cache_changed = True
```

Subscription uses the **`ACTOR_TOPIC_DICT` + `actor_topic_routing` extension-point convention** used by the rest of the codebase (no manual `add_subscriber_to_topic` calls in production). Two-line addition:

```python
# dropbot_protocol_controls/consts.py
from device_viewer.consts import CALIBRATION_DATA

CALIBRATION_LISTENER_ACTOR_NAME = "calibration_data_listener"

ACTOR_TOPIC_DICT = {
    CALIBRATION_LISTENER_ACTOR_NAME: [CALIBRATION_DATA],
}
```

```python
# dropbot_protocol_controls/plugin.py — add the contribution line
class DropbotProtocolControlsPlugin(Plugin):
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)
```

`MessageRouterPlugin.start()` then walks all contributed dicts and wires the subscription — no per-plugin `start()` method needed. Demos and test fixtures (which run without `MessageRouterPlugin`) still call `router.message_router_data.add_subscriber_to_topic(...)` directly, mirroring `subscribe_demo_responder` from PPT-4.

**Actor naming policy:** production actor names describe behaviour, not provenance. `calibration_data_listener` — not `ppt7_*`. (The PPT-6 demo's `ppt6_demo_camera_responder` is grandfathered in as demo-only code; should be renamed if/when those demos are touched again.)

## Plugin placement

**Extend `dropbot_protocol_controls`** (the same plugin that owns the Voltage column). Force is meaningless without Voltage — bundling them avoids cross-plugin coupling and matches the precedent from PPT-4.

A small **`force_math` helper module** is extracted from `ForceCalculationService` so it can be shared between:
1. The new `ForceColumn` (this issue).
2. `dropbot_status_and_controls/model.py:_recalculate_force` — currently reaches into `protocol_grid.services.force_calculation_service`. Switching it to the new helper removes the only outbound dependency from `dropbot_status_and_controls` to `protocol_grid`, paving the way for PPT-9.

## Files to add

```
src/dropbot_protocol_controls/
├── protocol_columns/
│   └── force_column.py            # ForceColumnModel.get_value + read-only view
├── services/
│   ├── force_math.py              # pure functions: capacitance_per_unit_area, force_for_step
│   └── calibration_cache.py       # HasTraits singleton + dramatiq actor (calibration_data_listener)
├── demos/
│   └── run_force_demo.py          # visual demo: edit voltage / publish fake calibration → watch Force update
└── tests/
    ├── test_force_math.py                      # pure-math unit tests (incl. legacy parity)
    ├── test_calibration_cache.py               # actor subscription + observable change events
    ├── test_force_column.py                    # get_value, format_display, voltage-observer wiring
    ├── test_persistence.py                     # confirm Force is NOT in serialised JSON
    └── tests_with_redis_server_need/
        └── test_calibration_round_trip.py      # publish CALIBRATION_DATA → cache updates → all rows repaint
```

## Files to touch (non-destructive — destructive removals deferred to PPT-9)

- `dropbot_protocol_controls/consts.py` — add `ACTOR_TOPIC_DICT` (first time this plugin needs one).
- `dropbot_protocol_controls/plugin.py` — register `make_force_column` in `PROTOCOL_COLUMNS`; add `actor_topic_routing` contribution line.
- `dropbot_status_and_controls/model.py` — re-point the `ForceCalculationService` import at the new `dropbot_protocol_controls.services.force_math` helpers. (One-line dependency cleanup.)

**Not touched in this PR** (still in use by legacy `protocol_grid`):
- `protocol_grid/services/force_calculation_service.py` — kept until PPT-9.
- `protocol_grid/services/volume_threshold_service.py` — also imports `ForceCalculationService`; stays on the legacy path until PPT-9.

## Persistence policy

Calibration values are **not** written into the protocol JSON. Calibration is a current-device measurement, not protocol data — re-running a saved protocol later should reflect the *current* calibration, not a stale historical value. The data logger still captures per-step calibration for archival.

This is a deliberate divergence from the legacy `protocol_grid` behaviour, which persisted `_liquid_capacitance_over_area` / `_filler_capacitance_over_area` into the saved protocol file (`protocol_state.py:169-170`).

## Acceptance criteria

- [ ] `make_force_column()` returns a `Column` whose model computes F = C/A × V²/2 mN/m and whose view is read-only.
- [ ] Editing a Voltage cell repaints **only** the Force cell on the same row (verified by spying on `dataChanged` emissions).
- [ ] Publishing `CALIBRATION_DATA` updates `CalibrationCache.liquid_*` / `.filler_*` and triggers a single column-wide Force repaint.
- [ ] `rm.table["force"]` returns the same numeric values that `format_display` shows (proves the pandas facade and the view see one source of truth).
- [ ] `rm.to_json()` does **not** include the force column's per-row values (computed, not stored). The Force column entry still appears in `payload["columns"]` so the file identifies its plugin origin.
- [ ] Calibration values do **not** appear anywhere in `rm.to_json()` either (per the persistence-policy section above).
- [ ] Legacy parity: a hand-picked spread of (V, C/A) pairs produces identical magnitudes to `ForceCalculationService.calculate_force_for_step` to 6 decimal places.
- [ ] `dropbot_status_and_controls` still shows the live force readout after the import-path swap.
- [ ] Redis-backed integration test passes — real `publish_message(CALIBRATION_DATA, ...)` round-trips into the cache via the `actor_topic_routing` extension-point wiring (no manual `add_subscriber_to_topic` in production code).
- [ ] All PPT-1/2/3/4/5/6 regression tests still pass.
- [ ] Demo `run_force_demo.py` runs end-to-end: opens a 3-step protocol with voltages 75/100/120 V, fakes a calibration publish, all three Force cells update without any user interaction beyond the publish.

## Open questions / decisions to make in design phase

1. **Initial calibration at plugin start.** `CALIBRATION_DATA` is republished any time the user edits calibration in device-viewer (`device_view_dock_pane.py:1128-1136`). On a cold protocol-tree open with no calibration ever published, `force` will be `None` and the cell will be blank. That matches today's behaviour — acceptable.

2. **Units in column header.** Legacy header is `"Force"` with values implicitly in mN/m. Proposed: rename header to `"Force (mN/m)"` to match Voltage's `"Voltage (V)"` from PPT-4.

3. **Group rows.** Force on a group row is undefined (no voltage). Set `view.renders_on_group = False`, matching how the legacy code skipped force on group rows.

## Out of scope (deferred)

- **Property-trait support for derived columns** — captured as **#399**. Will let `row.force` fire Traits change events automatically and let the view drop its manual `dataChanged` plumbing.
- Removing `protocol_grid/services/force_calculation_service.py` — happens in PPT-9 once `volume_threshold_service.py` and the legacy widget are gone.
- Per-row capacitance-per-unit-area override (currently a single global) — open follow-up if/when calibration becomes per-region.
- Pluggable force formula (e.g. for non-DMF actuators) — speculation; revisit when a real second use case appears.

## References

- Parent: #361 (PPT umbrella)
- Depends on: PPT-4 (#366) — Voltage column must exist for Force to read from it. ✅ merged.
- Will unblock: PPT-9 (#371) — once this is done, the only remaining `ForceCalculationService` consumer is `volume_threshold_service.py`, which also gets ported in PPT-9 cleanup.
- Deferred follow-up: #399 — Property-trait support for derived columns.
- Design doc: [`2026-04-21-pluggable-protocol-tree-design.md`](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/blob/main/docs/superpowers/specs/2026-04-21-pluggable-protocol-tree-design.md) §16 step 5 (PPT-7 line: "Migrate force calculation").
