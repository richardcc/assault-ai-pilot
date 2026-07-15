# EfficientZero v2 Local Roadmap

## Goal

Reach a fully independent, production-usable EfficientZero v2 agent for Assault, with measurable gains vs current MuZero baseline and without regressions in reporting/benchmark workflows.

Success target ("100% done"):
- Independent training/eval stack under `agents/efficientzero_v2/**`.
- EfficientZero-specific algorithmic components implemented (not only MuZero-compatible loop).
- Stable throughput and reproducible metrics.
- Better KPI profile than MuZero baseline on agreed scenarios/seeds.

---

## Current State (Today)

Implemented:
- Separate agent package: `agents/efficientzero_v2`.
- Independent train entry + local train engine:
  - `agents/efficientzero_v2/train/train_efficientzero_v2.py`
  - `agents/efficientzero_v2/train/train_engine.py`
- EfficientZero-specific network/trainer scaffolding:
  - `agents/efficientzero_v2/core/network.py`
  - `agents/efficientzero_v2/train/trainer.py`
- Consistency signal wired with temporal `next_observation`.
- Benchmark can load EfficientZero checkpoints.
- Reporting catalog supports `engine=efficientzero_v2`.
- Checkpoint I/O reduced (`checkpoint_every`, keep `final.pt`, remove `iter_*.pt` at end).

Still partial:
- EfficientZero target/reanalysis pipeline is not fully implemented.
- Promotion gating automation still requires robust candidate-vs-baseline runbook adoption in regular ops.

Recent implementation delta (2026-07-15, this iteration):
- `collect_xai` is now configurable in EfficientZero selfplay (`selfplay.collect_xai` / `train.collect_xai` fallback) and no longer hardcoded off.
- EfficientZero now emits a full `metrics/units_sides.json` contract (`units_sides_v1`) plus backward-compatible fallback handling in viewers.
- Short-episode diagnostics added to train summary/artifacts (`short_episode_diagnostics`, per-iteration distribution, thresholded short rate).
- Inference service now exports KPIs (`inference_latency_p50_ms`, `inference_latency_p95_ms`, queue depth, staleness proxy) into training metrics.
- Promotion gate operational pipeline added (`scripts/run_efficientzero_v2_promotion_gate.ps1` + `mlops.efficientzero_promotion_gate`).
- EZv2 network base is now local (`agents/efficientzero_v2/core/network_base.py`), removing direct inheritance from `agents.muzero.core.network` in the core path.
- EZv2 trainer base is now local (`agents/efficientzero_v2/train/trainer_base.py`), removing direct inheritance from `agents.muzero.train.trainer` while preserving objective-mask behavior.
- EZv2 config loading is now local (`agents/efficientzero_v2/core/interop.py::load_efficientzero_config`) and no longer routes through MuZero config loader.
- Selfplay path now uses an explicit EZv2 backend boundary (`agents/efficientzero_v2/core/selfplay.py`) with compatibility backend + swappable interface for full native migration.
- P0 independence closeout: selfplay default backend is now native EZv2 (`_NativeEZV2SelfplayBackend`), runtime interop/observability is local (`adapter_voec.py`, `observability.py`), and MuZero selfplay remains optional only via `ASSAULT_EZV2_SELFPLAY_BACKEND=legacy_muzero`.

Validation state for this delta: **Pending Validation** (requires EZv2 quick train+bench smoke and medium profile candidate-vs-baseline benchmark/gate review).

## P0 Independence Status

Status: **Done (implementation)** / **Pending Validation (runtime smoke + bench/report)**.

Closed scope:
- Default selfplay/MCTS runtime path is EZv2-native (no MuZero imports in normal train path).
- EZv2 train engine interop/observability uses local modules and no longer depends on MuZero obs/adapter modules.
- Daily train -> bench -> report route remains EZv2-first, with legacy artifact reading preserved at reporting layer.

Compatibility scope kept intentionally:
- Legacy MuZero selfplay fallback remains available through env flag only (`ASSAULT_EZV2_SELFPLAY_BACKEND=legacy_muzero`), not default.

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
- Produce full `metrics/units_sides.json` contract in Efficient engine (not minimal).
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
3. Implement full `units_sides.json` emission in Efficient engine.

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

