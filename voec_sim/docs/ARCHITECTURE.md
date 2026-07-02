# VOEC Architecture

VOEC is a clean simulation core designed for fair algorithm benchmarking and UI interoperability.

## Modules

- `voec_sim/core`: simulator lifecycle (`new_episode`, `legal_actions`, `step`, `snapshot`).
- `voec_sim/assets_bridge`: imports units and scenarios from existing project assets.
- `voec_sim/contracts`: neutral data contracts (`StateSnapshot`, `TransitionRecord`).
- `voec_sim/ui_contract`: serialized events for UI/replay.
- `voec_sim/tests`: contract and regression tests.

## Design intent

- Keep algorithm-specific logic outside VOEC.
- Reuse existing scenario and unit assets.
- Preserve deterministic behavior suitable for benchmarking.
