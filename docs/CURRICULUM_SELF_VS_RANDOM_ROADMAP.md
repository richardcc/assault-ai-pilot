# Curriculum Roadmap: Self vs Random

> Scope note: this document remains valid as the single-scenario foundation.
> For the current multi-scenario execution order and capability rollout
> (`2 escenarios`, `vs_past`, `humo`, `refuerzos`, `minas`), use
> `docs/CURRICULUM_2SCENARIOS_CAPABILITIES_ROADMAP.md`.

## Goal

Build a stable curriculum that starts with `self vs random`, then progressively increases difficulty without breaking tactical quality, telemetry quality, or training stability.

Primary success criteria:
- Better `tracked_captured_avg` and `vp_net_avg_by_side` than baseline.
- Lower defeat rates while keeping runtime bounded.
- Stable telemetry coverage (no hidden fallback behavior).

## Why `self vs random` Makes Sense

- It creates an easy-to-learn environment for early policy shaping.
- It accelerates learning of basic movement, capture, and threat-response patterns.
- It reduces early collapse risk compared to immediately training against strong/self mirrors.

Main risk:
- Overfitting to weak opponents (policy learns shortcuts that fail against stronger controllers).

Mitigation:
- Time-box this stage and promote only with explicit gates.

## Curriculum Phases

## Phase 0 - Environment and Contract Readiness

Objective:
- Ensure training/eval/reporting are deterministic enough to compare stages.

Tasks:
- Freeze seed sets for stage gates.
- Keep `train/eval` artifacts and catalog publication automated.
- Validate ELO and side metrics ingestion (including seed-level rows).

Exit gate:
- Two consecutive smoke cycles pass with no missing critical telemetry.

## Phase 1 - Bootstrap (`self` vs `random`)

Objective:
- Learn basic objective-taking and reduce passive/retreat bias.

Suggested setup:
- Opponent mix: `random=100%`.
- Short-to-medium episodes.
- Keep exploration high enough to avoid brittle opening scripts.

Track per block:
- `score`, `wins/draws/losses`
- `tracked_captured_avg`
- `vp_net_avg_by_side`
- `units_lost`, `enemy_units_eliminated`, `damage_dealt`

Promotion gate to Phase 2 (all must hold):
- `score >= 60%` on fixed eval seeds.
- `tracked_captured_avg` positive and stable across 2 blocks.
- No severe telemetry quality alarms (coverage drops, NaN spikes, schema drift).

## Phase 2 - Mixed Opponent Curriculum

Objective:
- Remove dependence on weak-opponent patterns.

Suggested progression:
- Step A: `random 70% / self 30%`
- Step B: `random 50% / self 50%`
- Step C: `random 30% / self 70%`

Rule:
- Move to next step only when gate passes in two independent blocks.

Gate template per step:
- Non-regression in defeat rate.
- `vp_net_avg_by_side` non-regression.
- `enemy_units_eliminated - units_lost` trend non-negative.

## Phase 3 - Self-Play Dominant

Objective:
- Train robustly against own improving policy.

Suggested setup:
- `self >= 80%`, keep a small `random` slice (10-20%) as regularizer.
- Maintain deterministic tie-break and stable MCTS telemetry.

Gate:
- Improvement versus last promoted checkpoint in at least 2/3 KPI groups:
  - outcome (`score`, W/D/L),
  - objective control (`tracked_captured_avg`, `vp_net_avg_by_side`),
  - combat efficiency (`units_lost`, `enemy_units_eliminated`, `damage_dealt`).

## Phase 4 - Hardening and Promotion

Objective:
- Validate that gains generalize across scenarios/profiles/seeds.

Tasks:
- Cross-scenario eval matrix.
- Controller/side split analysis in ELO page.
- Regression check on runtime cost (`selfplay_s`, `iter_s`).

Promotion gate:
- Pass benchmark protocol on fixed seeds + no major observability regressions.

## Operational Cadence

- Use fixed training blocks (example: 120 -> 600 -> 2000 episodes).
- After each block:
  - publish catalog,
  - run gated eval,
  - write a one-page checkpoint note (pass/fail + next action).

## Stop/Backoff Conditions

Rollback or hold stage if any of these occur:
- Defeat rate spikes > 10 points vs previous promoted stage.
- `tracked_captured_avg` collapses for 2 consecutive blocks.
- Runtime explodes (>1.4x) without KPI gain.
- Critical telemetry fields become systematically missing.

## Recommended Immediate Next Actions

1. Start Phase 1 with a fixed 5-seed eval gate pack.
2. Define exact promotion thresholds in config (`score`, `tracked_captured_avg`, defeat cap).
3. Prepare mixed-opponent scheduler for Phase 2 (`70/30 -> 50/50 -> 30/70`).
