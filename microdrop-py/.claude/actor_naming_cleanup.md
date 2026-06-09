## Goal

Apply the **"actor names describe behaviour, not provenance"** policy retroactively to demo and test code, so naming is consistent with the production convention being established by PPT-7 (#369).

## Background

Production code already follows the policy — no `pptN_` prefixed actor names exist in any production plugin (PPT-2/4/5/6). The first production listener in a `*_protocol_controls` plugin (the `calibration_data_listener` introduced by PPT-7) is named after its behaviour. The cleanup pass below brings demo + test code in line.

## What needs renaming

### Demo actor names (load-bearing)

These appear in `pluggable_protocol_tree/demos/base_demo_window.py`'s `_DEMO_PREFIXES` allowlist, which is used to safely purge stale demo actors from Redis on startup. Renaming requires updating the allowlist mechanism in lockstep.

| Current name | Where | Proposed |
|---|---|---|
| `ppt4_demo_actuation_overlay_listener` | `dropbot_protocol_controls/demos/run_widget_with_vf.py:59,113` | `vf_demo_actuation_overlay_listener` |
| `ppt6_demo_camera_responder` (`DEMO_CAMERA_RESPONDER_ACTOR_NAME`) | `video_protocol_controls/demos/camera_responder.py:28` | `video_demo_camera_responder` |
| `ppt12_demo_<slug>_listener` (dynamic) | `pluggable_protocol_tree/demos/base_demo_window.py:175,420` | `status_readout_<slug>_listener` |
| `ppt12_demo_phase_ack_listener` | `pluggable_protocol_tree/demos/base_demo_window.py:158,413` | `phase_ack_listener` |
| `ppt5_demo_magnet_responder` (referenced) | demos | drop the prefix |
| `ppt_vf_demo_*`, `ppt_demo_*`, `ppt11_demo_*` (allowlist entries) | base_demo_window.py:128 | drop the `pptN_` prefixes |

### Demo prefix allowlist (`_DEMO_PREFIXES`)

The allowlist needs to switch from "any `pptN_demo_` prefix" to a behaviour-based scheme — e.g. `demo_`, `*_demo_*` substring, or an explicit per-prefix list that drops the version numbers. Pick whichever stays safest (the goal of the allowlist is to avoid purging non-demo actors belonging to other processes).

### Test spy names (cosmetic)

| Current | Where |
|---|---|
| `test_ppt4_round_trip_spy` | `dropbot_protocol_controls/tests/tests_with_redis_server_need/test_voltage_frequency_protocol_round_trip.py:55` |
| `test_ppt5_magnet_round_trip_spy` | `peripheral_protocol_controls/tests/tests_with_redis_server_need/test_magnet_protocol_round_trip.py:51` |
| `test_ppt6_round_trip_spy` | `video_protocol_controls/tests/tests_with_redis_server_need/test_video_protocol_round_trip.py:50` |

Proposed: `test_voltage_frequency_round_trip_spy`, `test_magnet_round_trip_spy`, `test_video_protocol_round_trip_spy`.

## Out of scope

- Production actor names — already conform.
- Topic constants / file names / log messages that mention "PPT" — those are commit-history / documentation context and are fine to retain.

## Acceptance

- [ ] No `pptN_` prefix anywhere in `src/` outside of `docs/` and historical plan files.
- [ ] `_DEMO_PREFIXES` allowlist updated; stale-actor purge still works on a real demo run.
- [ ] All demo + test suites pass after the rename.

## References

- Policy origin: PPT-7 (#369) discussion thread.
- Allowlist mechanism: `pluggable_protocol_tree/demos/base_demo_window.py:120-130`.
