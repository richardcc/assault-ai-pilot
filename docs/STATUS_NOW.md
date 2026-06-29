# STATUS NOW (Single-Page Operational View)

Last update: 2026-06-28

## Current Decision

- Baseline: **R2.1-i = GO** (frozen reference)
- R4 line: **R4 / R4.1 = KILL** (closed)
- Planner advanced line: **P4.3+ = PAUSED**
- Reaction Fire contract: **PASS** (policy matrix gate)
- Current cycle status: **R2.a FAILED -> SINGLE-LEVER RETUNE ACTIVE**

## What Is Active (Only Pending Queue)

1. Single-lever retune active (reward only, no planner/guardrail changes):
   - `assault_sim/config/reward_config.json`: `vp_stepin_selected_bonus` `1.25 -> 1.80`
2. Retrain + re-run anti-regression gate:
   - `python -m assault_sim.train.train_sb3`
   - `powershell -ExecutionPolicy Bypass -File .\scripts\gate_r2a_no_regression_vs_r21i.ps1 -RunEval`
3. Keep `P4.3+` paused until new learning-side GO.
4. Reopen R4.x only with a new single-lever hypothesis.

## Latest Validated Snapshot

- Gate: `Reaction Fire policy matrix`
- Result: **PASS**
- Command:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_reaction_policy_matrix.ps1 -Episodes 50 -Seed 42 -EnforceGate`
- Report folder:
  - `assault_sim/session/reports/sb3_eval/reaction_policy_matrix_20260628_172042`
- Evidence:
  - `always`: fire=464, skipped=0
  - `balanced`: fire=403, skipped=44
  - `never`: fire=0, skipped=536

## Latest Learning Gate Snapshot

- Gate: `R2.a no-regression vs R2.1-i baseline`
- Result: **FAIL** (`metrics_sb3_report_20260628T152937Z.json`)
- Key deltas vs baseline:
  - `true_win_rate`: `0.1333 -> 0.0000` (FAIL)
  - `loss_rate`: `0.6667 -> 0.8000` (FAIL)
  - `vp_entry_conversion_rate`: `0.6312 -> 0.0000` (FAIL)
  - `capture_conversion_after_contact`: `0.5139 -> 0.3719` (FAIL)

## Fast Commands

- Reaction Fire strict gate:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_reaction_policy_matrix.ps1 -Episodes 50 -Seed 42 -EnforceGate`
- R2.a no-regression gate (with eval):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\gate_r2a_no_regression_vs_r21i.ps1 -RunEval`
- Full cycle (train + gate):
  - `python -m assault_sim.train.train_sb3`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\gate_r2a_no_regression_vs_r21i.ps1 -RunEval`
- R2.a no-regression gate (latest report only):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\gate_r2a_no_regression_vs_r21i.ps1`

## Not Active

- Do **not** open `R2.1-j` while baseline remains GO.
- Do **not** escalate R4 to 120 episodes after KILL.
- Do **not** mix planner + reward + guardrail changes in one cycle.

## Next Levers (Backlog, Not Active Yet)

Architecture candidates:

- Add explicit policy-vs-finalizer split telemetry (proposal vs executed) to isolate learning defects from safety corrections.
- Add mission critic signal (VP progression) alongside combat quality signal to reduce "good trade / bad mission" collapse.
- Add short team-shared intent memory per turn (focus VP, committed units, opened lanes) to reduce per-unit myopia.

Heuristic candidates:

- Hard priority for legal VP-entry paths in 1-2 steps over non-VP-relevant attacks.
- Unit selector score: `stepin_legal + nearest_vp + ally_blocking + enemy_pressure`.
- Anti-stagnation rules: penalize repeated reversal (`A->B->A`), lateral near-VP staging loops, and HOLD near VP without pressure.

Planner candidates (P4 backlog, not active):

- Temporal objective windows (early contact -> entry -> hold) to bias intent by turn phase and improve conversion timing.
- Tactical budget by intent (cap ATTRIT activations near VP before forcing CAPTURE lines).
- Minimum role coverage per team turn (at least one lane opener + one step-in/holder).
- Two-step lookahead score ("opens legal VP-entry next activation") instead of purely immediate local gain.
- Ally congestion penalty on same objective (spread pressure across VP lanes when local crowding is high).
- Explicit lane-opening priority for support fire that unlocks VP approach paths.
- Per-unit anti-oscillation TTL memory to block repeated `A->B->A` and lateral near-VP loops unless emergency.

RAG-for-training candidates (diagnostic copilot, not active):

- Build a run-ingestion indexer for eval reports + traces + gate outputs (read-only analysis layer).
- Add failure pattern detector for mission collapse (`vp_entry_conversion_rate=0`, high loss with acceptable damage ratio, CAPTURE drift).
- Add single-lever recommender with evidence citations from prior runs (why this lever, why not others).
- Add run-to-run comparator ("what changed and why") focused on mission KPIs over cosmetic combat stats.
- Add architecture regression watcher for policy/planner/finalizer splits after refactor (contract drift alerts).

Automation candidates (parallel lane, not active):

- Auto-experiment orchestrator for single-lever queue execution (`hypothesis -> change -> train -> gate -> keep/revert`).
- Lever knowledge graph (`lever -> KPI impact`) with confidence from historical runs to avoid repeating failed patterns.
- "Do-not-mix" guardrail checker (blocks experiments that combine planner + reward + guardrail in one iteration).
- Auto-postmortem generator per run (`pass/fail`, root causes, next lever recommendation).
- Experiment manifest schema (`experiment.json`) with reproducible seed/episodes/config deltas.

## Source of Truth Links

- Gap analysis (detailed + archive): `docs/GAP_ANALYSIS.md`
- Scripts index: `docs/SCRIPTS_INDEX.md`
- Train roadmap: `assault_sim/roadmap/ROADMAP_TRAINING_GYM_SB3_RLLIB.md`
- R4.1 checklist: `assault_sim/roadmap/R4_1_STEPIN_HEAD_CHECKLIST.md`
- Rules coverage roadmap: `docs/game_rules/ROADMAP_RULES_COVERAGE.md`
