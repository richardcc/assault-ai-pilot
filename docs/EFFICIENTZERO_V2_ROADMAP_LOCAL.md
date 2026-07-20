# EfficientZero v2 Local Roadmap

## Goal

Reach a fully independent, production-usable EfficientZero v2 agent for Assault, with measurable gains vs current MuZero baseline and without regressions in reporting/benchmark workflows.

Success target ("100% done"):
- Independent training/eval stack under `agents/efficientzero_v2/**`.
- EfficientZero-specific algorithmic components implemented (not only MuZero-compatible loop).
- Stable throughput and reproducible metrics.
- Better KPI profile than MuZero baseline on agreed scenarios/seeds.

---

## Current State (Pending Only)

Open items:
- EfficientZero target/reanalysis pipeline is not fully implemented.
- Promotion gating automation needs robust candidate-vs-baseline runbook adoption in regular ops.
- P0 implementation is complete, but runtime smoke + bench/report validation is still pending.
- Unit-first iterative replanning is implemented as experimental and pending A/B validation.

## P0 Independence Status

Status: **Done (implementation)** / **Pending Validation (runtime smoke + bench/report)**.
Validation focus:
- Contract/boundary tests pass in CI/local.
- Downstream import migration confirmed after `legacy_compat` removal.

---

## Phase Plan

## Phase 1 - Stabilize Current Independent Engine (Short)

Objective:
- Ensure current Efficient engine runs reliably for long jobs (120-600 episodes) with clean artifacts.

Tasks:
- Add robust checkpoint save (tmp + atomic rename + retry) to avoid Windows file write flakiness.
- Add train config knobs:
  - `train_updates_per_iter`
  - optional `save_only_final`
- Add clear run metadata in manifest:
  - `engine_mode`, consistency enabled, checkpoint policy.
- Keep benchmark/reporting compatibility green.

Exit criteria:
- 3 consecutive runs complete without I/O failures.
- Catalog/viewer show Efficient runs with no manual fixes.

---

## Phase 2 - EfficientZero Core Algorithm (Medium)

Objective:
- Replace MuZero-compatible training semantics with EfficientZero-like learning behavior.

Tasks:
- Implement EZ-style target/reanalysis pipeline:
  - value target refinement using latest network.
  - configurable reanalysis ratio.
- Extend consistency objective:
  - K-step latent consistency over unrolled transitions (not only one-step).
- Add loss schedule/weights in config:
  - policy/value/reward/objective/consistency weights.
- Add training diagnostics:
  - consistency stats, target drift, reanalysis coverage.

Exit criteria:
- Efficient-specific losses are active and non-trivial in metrics.
- Training remains stable across 5-seed smoke runs.

---

## Phase 3 - Selfplay Throughput Without Quality Loss (Medium)

Objective:
- Lower `selfplay_s` while preserving policy quality.

Tasks:
- Keep deterministic decision behavior; optimize only implementation:
  - inference-mode paths everywhere in selfplay.
  - reduce Python overhead in rollout postprocessing.
  - stronger inference cache hit-rate instrumentation and tuning.
- Optional advanced architecture:
  - CPU actor workers + centralized GPU inference service + GPU learner.
  - (recommended only in WSL/Linux first).

Exit criteria:
- >=20% reduction in `selfplay_s` at same `mcts_simulations` and `max_steps`.
- No KPI regression on fixed benchmark seeds.

### Unit-First Iterative Replanning (Experimental)

Status: **Implemented (experimental)** / **Pending A/B Validation**.

Concept:
- At each turn, rank the best-positioned unit first.
- Run MCTS constrained to that unit's legal actions.
- Apply the chosen action, then re-run planning for the next unit.
- Repeat until the turn's actionable units are exhausted.

Rationale:
- Current single-pass turn-level planning may dilute tactical focus when many units compete for search budget.
- Sequential unit-scoped planning can improve local tactical quality while still adapting after each applied action.

Expected benefits:
- Better action quality for high-leverage units (capture windows, VP contests, threat response).
- More interpretable decision traces (per-unit ranking plus per-unit MCTS choice).
- Potentially improved search efficiency by reducing per-decision branching complexity.

Risks and trade-offs:
- Greedy ordering bias: early unit choices may over-constrain later unit opportunities.
- Extra planning overhead from repeated MCTS invocations per turn.
- Sensitivity to unit-ranking heuristic; weak ranking can hurt global turn outcomes.
- Integration complexity with existing objective shaping and root-level tie-break logic.

Minimal validation plan:
- A/B compare against current planner on fixed seeds and equal simulation budget envelopes.
- Track turn-level KPIs (`tracked_captured_avg`, `vp_net_avg_by_side`, outcome rates) plus runtime (`selfplay_s`).
- Add telemetry for unit order, per-unit legal-action count, and per-unit selected-action quality deltas.
- Keep as experimental until two independent benchmark blocks show non-regression with measurable tactical gain.

### Target Scalable Architecture (Widely Used Pattern)

Idea:
- CPU workers generate selfplay episodes in parallel.
- Each worker queries a GPU model service for priors/values.
- A GPU learner trains from a central replay buffer.
- Weights are synchronized periodically from learner to workers.

Expected advantage:
- Higher selfplay throughput without saturating GPU with full game processes.

Cost/complexity:
- Must separate roles/processes:
  - CPU actor workers
  - GPU inference service (policy server)
  - GPU learner
  - central replay
- Must control:
  - inference latency
  - weight staleness/coherency

Applicability to current state:
- For the current simple pipeline this is a significant complexity jump.
- It is the correct path if we need serious scaling without quality loss.

MVP rollout recommendation (single node, staged):
1. Add local inference queue/server for actor requests.
2. Route selfplay workers to server (no local model forward in actors).
3. Keep single learner on GPU writing periodic weight snapshots.
4. Add bounded replay queue + sync interval controls.
5. Add health metrics (queue depth, inference p50/p95, weight age).

---

## Phase 4 - Full Data Contracts & Observability (Short)

Objective:
- Make Efficient engine first-class in all reporting contracts.

Tasks:
- Ensure parity of artifacts expected by reporting and benchmark docs.
- Add clear viewer labels for Efficient-specific metrics.

Exit criteria:
- No "unknown/missing" contract fallbacks in standard reports.
- Reporting pipeline runs unchanged for Efficient and MuZero.

---

## Phase 5 - Validation, Gating, and Promotion (Medium)

Objective:
- Decide rollout based on evidence, not anecdotes.

Benchmark protocol:
- Train blocks: 120 -> 600 -> 2000 episodes.
- Eval: fixed 5+ seeds, fixed `max_steps`.
- Compare against MuZero baseline with same budget.

Primary KPIs:
- `tracked_captured_avg`
- `winner_side_rates`
- `scenario_outcome_class_rates`
- `vp_net_avg_by_side`
- `selfplay_s`, `iter_s`

Promotion gate (suggested):
- Improve `tracked_captured_avg` by >=15% vs baseline,
- no regression in defeat rate,
- runtime cost <=1.4x per iteration.

Exit criteria:
- Gate passes twice on independent run blocks.

---

## Suggested Immediate Next 3 Actions

1. Add `train_updates_per_iter` to Efficient engine (start at 3).
2. Implement robust checkpoint atomic save with retries.
3. Run A/B validation for unit-first iterative replanning (fixed seeds, equal budget).

---

## Anomaly To Investigate (High Priority)

Observed in training logs:
- Some episodes in the same iteration are much shorter than expected
  (example: `episode 2/4 samples=42` while neighbors are around 100+).

Why this matters:
- Large variance in episode length may indicate early terminal conditions,
  policy collapse patterns, scenario/activation edge cases, or sampling bias.
- Throughput can look "better" while training signal quality worsens.

Investigation tasks:
1. Add per-episode terminal diagnostics summary to Efficient logs:
   - terminal reason
   - winner side
   - turn reached
   - alive units by side at terminal.
2. Track episode-length distribution per iteration:
   - min / p25 / p50 / p75 / max samples.
3. Correlate short episodes with outcome class and tracked-side captures.
4. Add guardrail alert when episode length falls below threshold (e.g. <50)
   for more than X% of episodes in a run.
5. Decide if short episodes are valid tactical wins/losses or pathological exits.

---

## Out of Scope for Now

- Full distributed cluster training.
- Multi-node actor/learner deployment.
- Cross-platform orchestration beyond local/WSL.

---

## Closed Worklog (Condensed)

- EZv2 runtime decoupled from MuZero in core training/selfplay path.
- Local config loader, local network/trainer bases, local observability/adapter path.
- Legacy alias export removed from interop; `legacy_compat` module removed.
- VP-progress and decision telemetry expanded in benchmark/viewer contracts.
- Optional aux objectives, success-probability term, global strategy soft signals wired.
- Unit-first iterative replanning implemented behind config (experimental).

