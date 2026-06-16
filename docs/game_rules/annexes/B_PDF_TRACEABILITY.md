# Annex B - PDF Traceability (Rule -> Implementation Mapping)

## 1. Canonical Sources

- Core Rulebook: `2024_09_18_Rulebook_rev6_web.pdf`
- LOS Examples: `2024_10_LOS_Examples_v1.pdf`
- Terrain/Support Aid: `PN007_GameAid_Back_rev3_web.pdf`
- Terrain Clarification: `TEC_Clarification.pdf`
- Campaign: `ITA_Assault_Libro_Campagna_v1.0.pdf`
- Optional FoW: `2025_09_10_FoW_v01.pdf`

## 2. Mapping Matrix

| PDF section family | Documentation chapter | Engine concern |
| --- | --- | --- |
| Ch. 6-8 phase and action flow | `02_TURN_SEQUENCE_AND_ACTIONS.md` | phase machine, legal actions, activation |
| Ch. 9 movement and terrain | `03_MOVEMENT_AND_TERRAIN.md` | pathing, terrain costs, objective entry |
| Ch. 10 LOS/spotting/fire | `04_LOS_SPOTTING_AND_RANGED_FIRE.md` | LOS states, spotting gates, ranged dice |
| Ch. 11 close combat | `05_CLOSE_COMBAT_AND_CRITICALS.md` | close-combat rounds, critical routing |
| Ch. 12 TAS/OAS | `06_TAS_OAS_AND_TERRAIN_DAMAGE.md` | support sequence, blast, crater mutation |
| Campaign book | `07_GELA_CAMPAIGN.md` | persistent progression and branching |
| FoW module | `08_OPTIONAL_FOW_RULES.md` | contact markers, reveal, recon |

## 3. Review Procedure

When any PDF changes:

1. identify impacted chapter(s),
2. update corresponding markdown chapter(s),
3. validate code-path alignment,
4. log update date in roadmap backlog.

## 4. Coverage Status Semantics

Use this status vocabulary in roadmap/backlog:

- `implemented`: behavior exists and is test-covered,
- `implemented-partial`: behavior exists with known gaps,
- `documented-only`: behavior specified but not coded,
- `unknown`: not yet assessed.

## 5. Known Work Item

Create and maintain `docs/GAP_ANALYSIS.md` with:

- vendor requirement,
- current implementation status,
- gap severity (high/medium/low),
- owner and target milestone.

## 6. Runtime Reproducibility Mapping (Non-PDF)

Validation state: **Pending Validation**.

| Operational rule | File/function | Test/status |
| --- | --- | --- |
| Start each SB3 run from a clean transient model workspace | `assault_sim/train/train_sb3.py` -> `_cleanup_model_workspace()` and `main()` cleanup gate | Pending dedicated regression test (`train startup cleanup`) |
| Run multi-seed eval in parallel with isolated per-seed outputs | `run_train_eval.ps1` -> `-ParallelEvalSeeds` and `-EvalParallelJobs` | Pending operational validation on `42/43/44` |
| CAPTURE guardrail overrides are explicitly traceable | `assault_sim/decision/option_executor.py` -> `_tag_action()` override fields | Covered by trace backward-compat tests; pending full episode validation |
| CAPTURE progress-vs-staging diagnostics and anti-lateralization guardrails are explicitly traceable | `assault_sim/decision/option_executor.py` -> `_best_capture_staging_move()` now includes VP-adjacent-ring distance shaping + enemy-pressure-aware scoring + stronger near-VP lateral-loop penalties, `_move_closer(capture_strict=True)`, near-VP fallbacks (`forced_attack_near_vp_staging`, `forced_attack_open_vp_window` now `<=3` and lane-opening targets adjacent to uncaptured VP), VP-relevant-only relaxed fallback, per-unit CAPTURE focus lock (`_capture_focus_lock_by_unit`), per-unit near-VP no-step-in streak, opening-window anti-spam throttle (per-unit decision spacing), aggressive L3 CAPTURE force (`aggressive_l3_capture_force`), and `_tag_action()` fields; all gated by `capture_guardrails_enabled` from `assault_sim/config/train_config.json`; propagated via `training_env/evaluator/results_analyzer` | Pending validation on smoke eval (`capture_suspected_progress_miss_rate`, `objective_progress_move` share, fallback reason mix, VP focus stability) |
| SB3 eval strategy sampling parity with runtime | `assault_sim/evaluation/eval_sb3.py` -> `SB3EvalController.act` evaluates `StrategicIntent` per activation (turn lock removed) | Pending validation on smoke eval (`L3 policy distribution` shift, VP entry metrics) |
| CAPTURE-only diagnostic mode for L3 isolation | `assault_sim/config/train_config.json` -> `diagnostic_force_capture_only`; wired through `assault_sim/evaluation/eval_sb3.py`, `assault_sim/envs/gym_assault_env.py`, and `assault_sim/decision/option_executor.py` | Pending validation on smoke eval (`L3 CAPTURE share`, `vp_entries_taken`) |
| VP-entry funnel observability (legal -> selected -> sustained control) | `assault_sim/decision/option_executor.py` step-in flags/reasons + `assault_sim/training_env.py` info propagation + `assault_sim/evaluation/evaluator.py` mission counters + `assault_sim/evaluation/results_analyzer.py` aggregates/percentiles + `assault_sim/evaluation/record_sb3_trace.py` trace fields | Pending validation on smoke eval (`vp_stepin_selection_rate`, `vp_stepin_block_reason_counts`, `vp_no_legal_stepin_near_count`, `vp_control_after_entry_turns_p50/p90`, per-unit entry success) |
| Gym controller avoids turn-wide intent lock | `assault_sim/envs/gym_assault_env.py` -> `_GymActionController.act` | Pending smoke validation (`seed=42`, `episodes=30`) |
