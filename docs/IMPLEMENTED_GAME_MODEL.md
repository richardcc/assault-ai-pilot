# Implemented Game Model (Codebase Status)

This document maps current implementation to the vendor model.

## 1) Runtime Core

- `assault_model/state/game_state.py`
  - canonical map/unit/hex-ownership container,
  - VP/control recalculation,
  - terminal state fields (`done`, `winner`, `end_reason`).

- `assault_model/runtime/game_state_runtime.py`
  - authoritative runtime execution layer,
  - action application,
  - dynamic side extraction and alternating activations,
  - end-of-turn and match-end checks,
  - event emission for runtime/UI integration.

## 2) Actions and Legal Move Generation

- `assault_model/actions/action_catalog.py`
  - legal action generation:
    - movement,
    - assault/ranged,
    - composites (`MoveThenFireAction`, `FireThenMoveAction`),
    - wait action.

- `assault_model/rules/movement_rules.py`
  - path legality with movement budget and terrain/fortification costs,
  - enemy-hex assault outcomes,
  - friendly stacking/vehicle interactions,
  - harsh terrain handling.

## 3) Combat, LOS, and Spotting

- `assault_model/combat/line_of_sight.py`
  - LOS checks with clear/hindered/blocked semantics.

- `assault_model/combat/spotting.py`, `spotting_runtime.py`
  - spotting logic and runtime updates.

- `assault_model/combat/ranged_combat_resolver.py`
  - ranged combat resolution with dice/modifier logic.

- `assault_backend/services/targeting_service.py`
  - UI targeting preview (LOS/path/dice explanation),
  - recently hardened for mixed die-type normalization.

## 4) RL/AI Decision Layer

- `assault_sim/decision/option_executor.py`
  - tactical option resolution with mission-aware guardrails,
  - CAPTURE logic, anti-ping-pong, fallback gates, action tagging.

- `assault_sim/envs/gym_assault_env.py`
  - Gym environment wrapper and trace-compatible decision telemetry.

- `assault_sim/training_env.py`
  - training wrapper, reward integration, observation composition.

- `assault_sim/rewards/progressive_reward.py`
  - shaped reward behavior used by training/evaluation.

## 5) Evaluation and Telemetry

- `assault_sim/evaluation/evaluator.py`
  - per-episode rollout metrics, mission counters, policy alignment.

- `assault_sim/evaluation/results_analyzer.py`
  - aggregate KPI reporting and mission summaries.

- `assault_sim/evaluation/record_sb3_trace.py`
  - deterministic trace recording with capture-debug fields.

Recent metric consistency updates:

- `vp_entry_conversion_rate = vp_entries_taken / vp_entry_opportunities` (if opportunities > 0),
- `vp_entry_missed_rate = 1 - vp_entry_conversion_rate`,
- `capture_conversion_after_contact = contact_to_capture_success / contact_events`.

## 6) Frontend/Backend Integration

- `assault_backend/services/action_service.py`
  - action serialization and side-normalized active-side checks.

- UI stack (`assault_ai_ui/*`)
  - action presentation and execution hooks,
  - compact targeting/roster interaction adjustments.

## 7) Test Coverage Added During This Cycle

- `assault_model/tests/test_hex_utils_contracts.py`
  - distance/neighbor contracts.

- `assault_model/tests/test_neighbors_irregular_map_contracts.py`
  - neighbor validity in sparse/irregular map footprints.

- `assault_sim/tests/test_evaluator_mission_action_consistency.py`
  - mission metric opportunity consistency from legal actions.

- `assault_model/tests/test_runtime_activation_multiside.py`
  - multi-side activation rotation, skip rules, and rollover behavior.

## 8) Known Gaps vs Vendor Canonical Scope

The following are still considered in-progress/conditional:

- full optional module parity for all TAS/OAS and campaign edge cases,
- complete FoW optional rule integration (vendor marks FoW doc as draft/optional),
- ongoing tactical KPI recovery (`true_win_rate`, `loss_rate`, VP-entry behavior) under RL training.

## 9) Governance Rule

For any conflict:

1. Vendor PDFs in `docs/pdfs/` are authoritative.
2. This implementation document reflects current code, not intended future behavior.
3. Roadmap tracks deltas and convergence work.
