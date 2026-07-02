# VOEC Simulator Spec (v1)

## Scope

VOEC v1 provides a simulator API that reuses current scenario/unit assets and exposes a stable interface for training and UI.

Baseline scenario for smoke tests: `battaglia_cittadina_2_1`.

## Public API

- `new_episode(scenario_id, seed=0)`
- `clone_state()`
- `legal_actions() -> list[str]`
- `step(action_id) -> TransitionRecord`
- `is_terminal() -> bool`
- `snapshot() -> StateSnapshot`

## Reward contract (v1)

- Non-terminal: `0.0`
- Terminal draw: `0.0`
- Terminal with winner: `1.0`

Note: side-aware rewards are planned for the agent adapter layer.

## Traceability map

- `new_episode` / reset path -> `voec_sim/core/simulator.py` -> `voec_sim/tests/test_sim_determinism.py`
- legal actions contract -> `voec_sim/core/simulator.py` -> `voec_sim/tests/test_legal_actions_contract.py`
- terminal and reward contract -> `voec_sim/core/simulator.py` -> `voec_sim/tests/test_terminal_conditions_v1.py`, `voec_sim/tests/test_reward_contract_v1.py`
- asset parity import -> `voec_sim/assets_bridge/importers.py` -> `voec_sim/tests/test_asset_parity_units.py`, `voec_sim/tests/test_asset_parity_scenarios.py`
