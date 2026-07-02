# Observability Spec (VOEC + MuZero)

Validation state: **Pending Validation**.

## Event families

- `DecisionEvent`: self-play and policy choice diagnostics.
- `SearchEvent`: search envelope metadata (node count and depth proxy).
- `TrainStepEvent`: optimization metrics per iteration.
- `TransitionEvent`: environment step-level transitions for replay.

## Storage

- JSONL files under `runs/<run_id>/events/`.
- Manifest under `runs/<run_id>/run_manifest.json`.
- Integrity checks under `runs/<run_id>/events/integrity.json`.
- Units/sides aggregate under `runs/<run_id>/metrics/units_sides.json`.
- Resume source checkpoint (when used) is captured in run manifest `config.resume_checkpoint`.

## Minimum fields

- `type`
- `payload.iteration` when applicable
- `payload.scenario_id` for environment-bound events
- `TransitionEvent` requires: `action_id`, `to_play`, `reward_target`, `done`, `terminal_reason`, `timeout`.
- `TransitionEvent` MuZero phase-2.9 additions:
  - `legal_reaction_options` (reaction-window observability),
  - `legal_attack_options` and `action_kind` are used to derive assault context tags.
- Benchmark payload requires `terminal_reasons` (normalized distribution by end reason).
- Benchmark payload phase-2.9 sections:
  - per-agent `phase_2_9_eval_kpis`,
  - global `phase_2_9_train_eval`,
  - global `phase_2_9_promotion_gate`.
- `metrics/units_sides.json` requires:
  - `transition_events`
  - `side_turn_counts`
  - `side_turn_rates`
  - `top_action_units` (`unit_id`, `count`, `rate`)

## MCTS planning parameters (current runner)

MuZero self-play planning behavior is configured in
`agents/muzero/configs/muzero_config.yaml`:

- `selfplay.mcts_simulations`
- `selfplay.mcts_c_puct`
- `selfplay.mcts_unroll_steps`
- `selfplay.mcts_discount`
- `selfplay.mcts_temperature`
- `selfplay.mcts_dirichlet_alpha`
- `selfplay.mcts_dirichlet_epsilon`
- `selfplay.timeout_penalty`
