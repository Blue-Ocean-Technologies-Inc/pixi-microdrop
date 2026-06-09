## Goal

Add first-class support for **derived columns** in `pluggable_protocol_tree` whose value is a Traits `Property` over other row traits, instead of being computed inside `model.get_value(row)`.

## Why

PPT-7 (force) takes the simpler path: override `BaseColumnModel.get_value(row)` to compute on demand from `row.voltage` + a shared cache. That works, but has two limitations:

1. **No automatic Traits change notifications on the row.** Other handlers / views that `observe("voltage")` on a row are notified when voltage changes; nothing notifies them when the *derived* value (force) changes. Today PPT-7 papers over this by having the view explicitly emit `dataChanged` for the Force cell when its sibling voltage trait fires. Workable for one column; tedious if a second derived column appears.
2. **The DataFrame snapshot in `RowManager.table` works, but it isn't reactive** — pandas users have to re-read `rm.table["force"]` after every change.

A `Property(Float, observe="voltage")` trait declared on the row class would give us:
- Automatic notification chain: voltage change → property recomputes → any observer of `row.force` fires.
- Same get_value path still works; the table snapshot still picks the value up.

## What blocks it today

`build_row_type` in `pluggable_protocol_tree/models/row.py` builds the dynamic row class as:

```python
class_dict = {col.model.col_id: col.model.trait_for_row() for col in columns}
return type(name, (base,), class_dict)
```

That maps `col_id -> TraitType`. For a `Property` trait, Traits also needs a getter method on the class (e.g. `_get_<col_id>`). The model has no clean way to inject one, and `IColumnModel.trait_for_row()` returns only a TraitType.

## Sketch of the fix

Two minimal options, pick one in design:

**(a) Optional `getter_for_row(row)` hook on `IColumnModel`.** When non-None, `build_row_type` injects it into `class_dict` as `_get_<col_id>`. Default: `None` (column has no getter, current behavior).

**(b) Allow `trait_for_row()` to return either a TraitType OR a `(TraitType, getter)` tuple.** Slightly less clean signature; same outcome.

Either way the migration is a few lines in core, plus a one-line opt-in in the new `ForceColumnModel`.

## Acceptance

- [ ] A column whose model returns a `Property` trait + getter participates in row-level Traits notifications.
- [ ] PPT-7's `ForceColumn` migrates from the `get_value` route to the Property route as a sample consumer; manual repaint plumbing is removed from its view.
- [ ] All existing PPT-1/2/3/4/5/6 tests still pass — the Property route is opt-in.
- [ ] One unit test demonstrates: editing voltage triggers a `change_event` on the row's `force` trait.

## Out of scope

- Forcing all derived columns to use Property — `get_value` stays a valid path.
- Vectorised pandas write-back — the snapshot semantics of `RowManager.table` are unchanged.

## References

- Parent: #361 (PPT umbrella).
- Triggered by: PPT-7 (#369) design discussion — `get_value` chosen for now to avoid touching core; this issue captures the deferred upgrade.
