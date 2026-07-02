# Benchmark Protocol (VOEC)

Validation state: **Pending Validation**.

## Goal

Compare agents on the same VOEC scenario, seeds, and action budget.

## Contract

- Shared simulator: `voec_sim`.
- Shared scenarios: imported from `assault_sim/assets/scenarios`.
- Shared seeds: default `[42, 43, 44]`.
- Shared decision budget per episode.
- Shared evaluation determinism: benchmark MCTS runs with `dirichlet_epsilon=0.0` (no root exploration noise).
- Timeout resolution is explicit: if max steps is reached, VOEC resolves winner by scenario VP control first, then by material advantage heuristic (alive units, then HP), and benchmark applies signed terminal reward (`+1/-1`) from acting side perspective.
- Scenario turn limit has precedence when defined: benchmark resolves timeout as `scenario_turn_limit` before `max_steps`.

## Current runner

- `assault_bench/runner.py`
- Config file: `assault_bench/configs/benchmark_config.yaml`
- VOEC asset config referenced from benchmark config: `voec_sim/configs/voec_config.yaml`
- Agents included:
  - `muzero_stub`
  - `baseline_random`

## Outputs

- `runs/bench_latest.json`
- Metrics:
  - `avg_return`
  - `avg_steps`
  - `terminal_rate`
  - `timeout_rate`
  - `win_rate`
  - `phase_2_9_eval_kpis` (per-agent reaction-fire and assault/melee KPIs)
  - `phase_2_9_train_eval` (side-by-side MuZero train vs eval KPI table)
  - `phase_2_9_promotion_gate` (`PASS`/`FAIL` with explicit checks)

## Phase 2.9 Gate Contract

- Reaction fire contract:
  - `reaction_window_count`, `reaction_fire_count`, `reaction_fire_skipped_count`
  - activation, kill conversion, and damage induced/prevented proxies.
- Assault/melee contract:
  - explicit `ASSAULT_MELEE` action-family tracking
  - `melee_attempts`, `melee_success_rate`, `melee_kills_per_attempt`, `melee_damage_per_attempt`
  - context tags (`favorable` / `unfavorable`) from local advantage proxy.
- Promotion checks in benchmark output:
  - reaction contract pass,
  - no regression in tracked capture conversion and loss rate vs baseline.

### VP-first promotion mode

- Current benchmark gate uses `promotion_mode: vp_first`.
- Blocking checks are VP/objective-centric:
  - `capture_conversion_after_contact_no_regression`,
  - `loss_rate_no_regression`,
  - `reaction_contract_pass`,
  - `reaction_failfast_block`.
- `capture_conversion_after_contact_no_regression` is direction-aware:
  - if `tracked_side == dominant_winner_side`, higher `tracked_captured_avg` is better;
  - otherwise lower `tracked_captured_avg` is better (opponent-side tracked metric).
- Assault/melee checks are kept as diagnostics in `phase_2_9_promotion_gate.advisory` and do not block promotion by themselves.

## Runner CLI

- Default config:
  - `python -m assault_bench.runner`
- Custom config:
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.test.yaml`
- Evaluate trained MuZero checkpoint:
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.dev_plus.yaml --checkpoint runs/<run_id>/checkpoints/iter_11.pt`
- Auto-pick latest MuZero checkpoint:
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.test.yaml`
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.test.yaml --checkpoint latest`
