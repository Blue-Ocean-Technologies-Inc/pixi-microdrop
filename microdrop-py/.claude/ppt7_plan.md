# PPT-7 Implementation Plan — Force Column

**Issue:** [#369](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/369)
**Branch:** `feat/ppt-7-force-column`
**Reference:** PPT-7 issue body (locked design) + PPT-4 (`dropbot_protocol_controls`) as the parent plugin we extend.

## Design (locked — see issue body for full reasoning)

- **Compute path:** `ForceColumnModel.get_value(row)` reads `row.voltage` + a shared `CalibrationCache` singleton; returns force in mN/m or `None`.
- **Reactivity:** voltage edit → row-scoped Qt `dataChanged`; `cache_changed` Event → column-wide Qt `dataChanged`.
- **Cache lifecycle:** Dramatiq actor `calibration_data_listener` updates the cache on `CALIBRATION_DATA` arrival.
- **Subscription wiring:** `ACTOR_TOPIC_DICT` in `dropbot_protocol_controls/consts.py` + `actor_topic_routing` contribution in `plugin.py` — production. Demos/tests use direct `add_subscriber_to_topic` on the bare router.
- **Persistence:** Force values NOT in `payload["rows"]`; Force column entry IS in `payload["columns"]`. Calibration NOT persisted anywhere in the tree.
- **Naming policy:** behaviour-not-provenance — actor named `calibration_data_listener`, demo named `run_force_demo.py`, no `ppt7_*` prefixes.

## Task breakdown

Each task is a single commit with its own subagent-driven cycle: implementer → code reviewer → fix → next task.

### Task 1 — Plugin scaffold: `ACTOR_TOPIC_DICT` + `actor_topic_routing` wiring

**Files:** `dropbot_protocol_controls/consts.py`, `dropbot_protocol_controls/plugin.py`.

- Add to `consts.py`:
  ```python
  from device_viewer.consts import CALIBRATION_DATA

  CALIBRATION_LISTENER_ACTOR_NAME = "calibration_data_listener"

  ACTOR_TOPIC_DICT = {
      CALIBRATION_LISTENER_ACTOR_NAME: [CALIBRATION_DATA],
  }
  ```
- Add to `plugin.py`:
  ```python
  from message_router.consts import ACTOR_TOPIC_ROUTES
  from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name

  class DropbotProtocolControlsPlugin(Plugin):
      ...
      actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)
  ```
- **Test:** `tests/test_plugin_shell.py` — assert plugin still instantiates; `actor_topic_routing` returns the expected dict.

**Commit:** `[PPT-7] Task 1 — wire calibration_data_listener via ACTOR_TOPIC_DICT`

### Task 2 — `services/force_math.py` (pure functions, legacy parity)

**Files:** `dropbot_protocol_controls/services/__init__.py` (empty), `dropbot_protocol_controls/services/force_math.py`.

Lift the math from `protocol_grid/services/force_calculation_service.py`:
```python
def capacitance_per_unit_area(liquid_pf_per_mm2: float, filler_pf_per_mm2: float) -> Optional[float]:
    """C/A = liquid - filler, returning None if invalid."""
    if (liquid_pf_per_mm2 is None or filler_pf_per_mm2 is None
            or liquid_pf_per_mm2 < 0 or filler_pf_per_mm2 < 0
            or liquid_pf_per_mm2 <= filler_pf_per_mm2):
        return None
    return liquid_pf_per_mm2 - filler_pf_per_mm2

def force_for_step(voltage_v: float, c_per_a_pf_per_mm2: float) -> Optional[float]:
    """F = (C/A × V²) / 2 in mN/m. Uses pint for unit conversion."""
    if voltage_v <= 0 or c_per_a_pf_per_mm2 <= 0:
        return None
    cap = ureg.Quantity(c_per_a_pf_per_mm2, 'pF/mm**2')
    v = ureg.Quantity(voltage_v, 'V')
    force = (cap * v**2 / 2).to('mN/m').magnitude
    return force if force > 0 else None
```
- **Tests:** `tests/test_force_math.py` — guards (`None`, negative, equal cases), legacy parity (a spread of (V, C/A) pairs producing identical magnitudes to `ForceCalculationService.calculate_force_for_step` to 6 decimal places).

**Commit:** `[PPT-7] Task 2 — extract force_math helpers from legacy service`

### Task 3 — `services/calibration_cache.py`

**Files:** `dropbot_protocol_controls/services/calibration_cache.py`.

```python
import json
import dramatiq
from traits.api import Event, Float, HasTraits

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message  # not used here, but consistent
from ..consts import CALIBRATION_LISTENER_ACTOR_NAME
from .force_math import capacitance_per_unit_area


class CalibrationCache(HasTraits):
    liquid_capacitance_over_area = Float(0.0)   # pF/mm^2
    filler_capacitance_over_area = Float(0.0)
    cache_changed = Event

    def capacitance_per_unit_area(self):
        return capacitance_per_unit_area(
            self.liquid_capacitance_over_area,
            self.filler_capacitance_over_area,
        )


cache = CalibrationCache()


@dramatiq.actor(actor_name=CALIBRATION_LISTENER_ACTOR_NAME, queue_name="default")
def _on_calibration(message: str, topic: str, timestamp: float = None):
    payload = json.loads(message)
    cache.trait_set(
        liquid_capacitance_over_area=float(payload["liquid_capacitance_over_area"]),
        filler_capacitance_over_area=float(payload["filler_capacitance_over_area"]),
    )
    cache.cache_changed = True
```

- **Tests:** `tests/test_calibration_cache.py` — direct cache mutation fires `cache_changed`; `capacitance_per_unit_area()` returns expected; actor invocation parses JSON and updates cache; malformed JSON does not crash dramatiq worker (use try/except around `json.loads`).

**Commit:** `[PPT-7] Task 3 — CalibrationCache + calibration_data_listener actor`

### Task 4 — `protocol_columns/force_column.py` (model + view + factory)

**Files:** `dropbot_protocol_controls/protocol_columns/force_column.py`.

```python
from traits.api import Float

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.text import TextColumnView  # check exact view name

from ..services.calibration_cache import cache
from ..services.force_math import force_for_step


class ForceColumnModel(BaseColumnModel):
    """Derived per-step force display. Not stored on rows; computed from
    row.voltage + the global CalibrationCache. Read-only."""

    def trait_for_row(self):
        # Force is not stored as a row trait — return a Float just to
        # satisfy build_row_type's `class_dict[col_id] = trait`. The
        # placeholder value is never read; get_value overrides it.
        return Float(0.0)

    def get_value(self, row):
        c_per_a = cache.full_electrode_capacitance_per_unit_area()
        if c_per_a is None:
            return None
        return force_for_step(float(row.voltage), c_per_a)

    def serialize(self, value):
        # Force is computed, not persisted. Returning None makes the
        # round-trip test trivial: no per-row force survives in JSON.
        return None

    def deserialize(self, raw):
        return None  # ignored; get_value recomputes


class ForceColumnView(TextColumnView):
    renders_on_group = False
    hidden_by_default = False

    def format_display(self, value, row):
        return f"{value:.2f}" if value is not None else ""

    def get_flags(self, row):
        # Read-only: drop ItemIsEditable.
        from pyface.qt.QtCore import Qt
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


def make_force_column():
    return Column(
        model=ForceColumnModel(
            col_id="force",
            col_name="Force (mN/m)",
            default_value=0.0,
        ),
        view=ForceColumnView(),
        handler=BaseColumnHandler(),
    )
```

**Open at task time:** confirm exact base view class name (`TextColumnView` vs another) by reading existing column views; pick the one that gives a label-only (non-editable) cell with a custom `format_display`.

- **Tests:** `tests/test_force_column.py`
  - `make_force_column()` returns a Column with the right model/view.
  - `model.get_value(row_with_voltage_100, cache_with_calibration)` returns expected Float.
  - `model.get_value(row_with_voltage_0)` returns `None`.
  - `model.get_value(row, cache_with_no_calibration)` returns `None`.
  - `view.format_display(5.43, row)` returns `"5.43"`.
  - `view.format_display(None, row)` returns `""`.
  - `view.renders_on_group is False`.
  - `model.serialize(any) is None` and `model.deserialize(any) is None` (force is never persisted).

**Commit:** `[PPT-7] Task 4 — ForceColumn model + read-only view + factory`

### Task 5 — Voltage observer wiring (per-row repaint)

This is the trickiest part — the view must emit `dataChanged` for the Force cell on row N when row N's `voltage` trait changes. Look at how PPT-1's existing column views observe row traits to drive `dataChanged` (the executor or row manager probably has hooks).

**Files:** `dropbot_protocol_controls/protocol_columns/force_column.py` — extend the view with row-observer wiring; possibly also a small helper if no existing pattern exists.

- Inspect `pluggable_protocol_tree/views/columns/*.py` and the Qt model adapter to see the existing pattern. If a built-in column already observes a sibling trait for repaint (e.g. routes column reacting to electrodes), mirror it.
- If no pattern exists, expose a hook on the column view: `view.observed_row_traits = ["voltage"]` and have the Qt model wire `observe("voltage")` on each row to emit `dataChanged` for the Force column on that row's index.
- **Test:** `tests/test_force_column.py` — set up a tiny Qt model + a row with `voltage=100`, mock the Qt model's `dataChanged` signal, edit `row.voltage = 120`, assert `dataChanged` fired for the Force column index on that row only.

**Commit:** `[PPT-7] Task 5 — repaint Force cell on row voltage change`

### Task 6 — `cache_changed` observer wiring (column-wide repaint)

**Files:** `dropbot_protocol_controls/protocol_columns/force_column.py` (or a small adjacent helper).

- The view subscribes to `cache.cache_changed` and on fire, emits `dataChanged` over the entire Force column (top-left to bottom-right) on the Qt model.
- **Test:** mock Qt model, fire `cache.cache_changed = True`, assert `dataChanged` was emitted with the Force column index range.

**Commit:** `[PPT-7] Task 6 — repaint Force column on cache_changed`

### Task 7 — Persistence test

**Files:** `dropbot_protocol_controls/tests/test_persistence.py`.

- Build a 7-column protocol (the PPT-3 builtins + voltage + frequency + force).
- Add 3 steps with varying voltages.
- Set the calibration cache to a known value.
- Assert `rm.to_json()` payload satisfies:
  - `payload["columns"]` contains an entry for `force` with `cls = "...ForceColumnModel"`.
  - `payload["rows"]` contains the three rows but each row's serialised force value is `None` (because `serialize()` returns `None`).
  - No mention of `liquid_capacitance_over_area` or `filler_capacitance_over_area` anywhere in the JSON.
- Round-trip via `from_json` and confirm `get_value` recomputes correctly post-load (calibration cache is still set, voltages restored from JSON).

**Commit:** `[PPT-7] Task 7 — persistence: Force not stored, calibration not in JSON`

### Task 8 — Plugin contribution + smoke

**Files:** `dropbot_protocol_controls/plugin.py`.

- Add `make_force_column()` to `_contributed_protocol_columns_default`.
- **Test:** plugin shell test asserts contributed columns now contains `[voltage, frequency, force]` (in some order).

**Commit:** `[PPT-7] Task 8 — contribute Force column via PROTOCOL_COLUMNS`

### Task 9 — `dropbot_status_and_controls` dependency swap

**Files:** `dropbot_status_and_controls/model.py`.

- Re-point the `from protocol_grid.services.force_calculation_service import ForceCalculationService` import to `from dropbot_protocol_controls.services.force_math import force_for_step`.
- Update the call site at `_recalculate_force` to call `force_for_step(voltage, c_device)` directly.
- **Test:** any existing tests for `_recalculate_force` should still pass; if there are none, add one with mocked traits.

**Commit:** `[PPT-7] Task 9 — re-point dropbot_status_and_controls to new force_math`

### Task 10 — Demo: `demos/run_force_demo.py`

**Files:** `dropbot_protocol_controls/demos/run_force_demo.py` (+ `demos/__init__.py` if not already).

- Use the same `BasePluggableProtocolDemoWindow` pattern as PPT-6.
- 3 steps with voltages 75/100/120 V.
- Subscribe `calibration_data_listener` to `CALIBRATION_DATA` in `routing_setup` (since demos run without `MessageRouterPlugin`):
  ```python
  router.message_router_data.add_subscriber_to_topic(
      topic=CALIBRATION_DATA,
      subscribing_actor_name=CALIBRATION_LISTENER_ACTOR_NAME,
  )
  ```
- After window opens, publish a fake `CALIBRATION_DATA` message (`liquid=2.0, filler=0.5`), then verify all 3 Force cells show non-empty values.
- Optional: add a small Qt button "Publish Calibration" that re-publishes with random values to demo reactivity.

**Commit:** `[PPT-7] Task 10 — run_force_demo.py: 3 steps + calibration publish`

### Task 11 — Redis-backed integration test

**Files:** `dropbot_protocol_controls/tests/tests_with_redis_server_need/test_calibration_round_trip.py`.

- Spin up a real `MessageRouterActor` + `dramatiq_workers_context()` (mirror the PPT-4 pattern).
- Manually subscribe `calibration_data_listener` to `CALIBRATION_DATA` (since `MessageRouterPlugin` is not loaded in tests).
- Publish a `CALIBRATION_DATA` JSON via `publish_message`.
- Assert (with a short retry loop) that `cache.liquid_capacitance_over_area` is updated.
- Hook a spy onto `cache.cache_changed` and assert it fired exactly once.

**Commit:** `[PPT-7] Task 11 — Redis-backed CALIBRATION_DATA → cache round-trip`

### Task 12 — Final verification

- Run all `dropbot_protocol_controls/tests/` (`pixi run pytest dropbot_protocol_controls/tests/ -v`).
- Run all `pluggable_protocol_tree/tests/` to confirm no regression.
- Run PPT-5 `peripheral_protocol_controls/tests/` and PPT-6 `video_protocol_controls/tests/` for safety.
- Manual smoke: `pixi run python -m dropbot_protocol_controls.demos.run_force_demo`.

**Commit:** `[PPT-7] Task 12 — final verification + summary`

## Naming + wiring policy applied throughout

- Production actor name: `calibration_data_listener` (no PPT prefix).
- Production wiring: `ACTOR_TOPIC_DICT` + `actor_topic_routing` extension point.
- Demo wiring: explicit `add_subscriber_to_topic` on the bare router (no `MessageRouterPlugin` available in demo lifecycle).
- Demo file naming: `run_force_demo.py` (not `run_ppt7_demo.py`).
- Test spy names: descriptive (`force_round_trip_spy` style), no PPT prefix.

## When in doubt

- Refer to the locked design in #369.
- For wiring patterns: `dropbot_protocol_controls/plugin.py` (PPT-4 plugin), `device_viewer/plugin.py` (mature `ACTOR_TOPIC_DICT` consumer).
- For demo lifecycle: `dropbot_protocol_controls/demos/run_voltage_frequency_demo.py` (PPT-4 demo), `video_protocol_controls/demos/run_widget_video_demo.py` (PPT-6 demo).
- For row-trait observe → Qt repaint patterns: read existing built-in column views in `pluggable_protocol_tree/views/columns/`.
