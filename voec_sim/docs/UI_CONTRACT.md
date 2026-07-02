# VOEC UI Contract (v1)

VOEC emits schema-versioned payloads that can be consumed by a viewer without accessing internal runtime objects.

## Transition event fields

- `schema_version`
- `turn`
- `to_play`
- `action_id`
- `reward`
- `done`
- `units[]` with:
  - `unit_id`
  - `unit_key`
  - `unit_label`
  - `art_ref`
  - `side`
  - `q`, `r`
  - `hp`
  - `alive`

## Asset linkage

UI resolution is done through `unit_key` and existing UI catalogs (for example `unitImages.ts`).

## Episode timeline generation

VOEC provides a helper to build replay-ready timelines:

- `voec_sim.ui_contract.timeline.build_episode_timeline(sim, scenario_id, seed, policy_fn, max_steps)`

This emits `EpisodeTimeline` with ordered `TransitionEvent` payloads and stable `schema_version`.

## CLI timeline export

You can export a replay timeline directly from CLI:

- `python -m voec_sim.ui_contract.export_timeline --voec-config voec_sim/configs/voec_config.yaml --scenario battaglia_cittadina_2_1 --seed 42 --policy first --max-steps 200 --out runs/ui_timeline_latest.json`
