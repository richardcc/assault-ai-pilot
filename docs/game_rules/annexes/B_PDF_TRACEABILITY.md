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
| `train_sb3` CLI help is side-effect free | `assault_sim/train/train_sb3.py` -> `argparse` gate in `main()` before SB3/env setup | Pending dedicated CLI regression test (`--help` must exit without starting train) |
| Run multi-seed eval in parallel with isolated per-seed outputs | `run_train_eval.ps1` -> `-ParallelEvalSeeds` and `-EvalParallelJobs` | Pending operational validation on `42/43/44` |
| CAPTURE guardrail overrides are explicitly traceable | `assault_sim/decision/option_executor.py` -> `_tag_action()` override fields | Covered by trace backward-compat tests; pending full episode validation |
| CAPTURE progress-vs-staging diagnostics and anti-lateralization guardrails are explicitly traceable | `assault_sim/decision/option_executor.py` -> `_best_capture_staging_move()` now includes VP-adjacent-ring distance shaping + enemy-pressure-aware scoring + stronger near-VP lateral-loop penalties, `_move_closer(capture_strict=True)`, near-VP fallbacks (`forced_attack_near_vp_staging`, `forced_attack_open_vp_window` now `<=3` and lane-opening targets adjacent to uncaptured VP), support-fire coupling (`attack_gate_support_open_lane`) and suppression of low-value non-lane high-adv CAPTURE attacks, post-opening follow-up advance + cooldown guardrail, VP-relevant-only relaxed fallback, per-unit CAPTURE focus lock (`_capture_focus_lock_by_unit`), per-unit near-VP no-step-in streak, opening-window anti-spam throttle (per-unit decision spacing), aggressive L3 CAPTURE force (`aggressive_l3_capture_force`), minimum L3 CAPTURE quota (`minimum_capture_intent_quota`), and `_tag_action()` fields; all gated by `capture_guardrails_enabled` from `assault_sim/config/train_config.json`; propagated via `training_env/evaluator/results_analyzer` | Pending validation on smoke eval (`l3_capture_forced_rate`, `l3_capture_force_reason_counts`, `post_open_window_followup_success_rate`, `capture_suspected_progress_miss_rate`, `objective_progress_move` share, fallback reason mix, VP focus stability) |
| SB3 eval strategy sampling parity with runtime | `assault_sim/evaluation/eval_sb3.py` -> `SB3EvalController.act` evaluates `StrategicIntent` per activation (turn lock removed) | Pending validation on smoke eval (`L3 policy distribution` shift, VP entry metrics) |
| CAPTURE-only diagnostic mode for L3 isolation | `assault_sim/config/train_config.json` -> `diagnostic_force_capture_only`; wired through `assault_sim/evaluation/eval_sb3.py`, `assault_sim/envs/gym_assault_env.py`, and `assault_sim/decision/option_executor.py` | Pending validation on smoke eval (`L3 CAPTURE share`, `vp_entries_taken`) |
| R4 step-in policy skeleton telemetry | `assault_sim/envs/gym_assault_env.py` (`_GymActionController.act`) + `assault_sim/evaluation/eval_sb3.py` (`SB3EvalController.act`) expose `stepin_legal_mask` / `stepin_forced_option`; propagated via `assault_sim/training_env.py` and aggregated in `assault_sim/evaluation/evaluator.py` / `assault_sim/evaluation/results_analyzer.py` | Pending validation on micro-benchmark (`vp_stepin_selection_rate`, `stepin_forced_option_count`) |
| VP-entry funnel observability (legal -> selected -> sustained control) | `assault_sim/decision/option_executor.py` step-in flags/reasons + `assault_sim/training_env.py` info propagation + `assault_sim/evaluation/evaluator.py` mission counters + `assault_sim/evaluation/results_analyzer.py` aggregates/percentiles + `assault_sim/evaluation/record_sb3_trace.py` trace fields | Pending validation on smoke eval (`vp_stepin_selection_rate`, `vp_stepin_block_reason_counts`, `vp_no_legal_stepin_near_count`, `vp_control_after_entry_turns_p50/p90`, per-unit entry success) |
| Gym controller avoids turn-wide intent lock | `assault_sim/envs/gym_assault_env.py` -> `_GymActionController.act` | Pending smoke validation (`seed=42`, `episodes=30`) |
| Policy-side CAPTURE priority under pending objectives | `assault_sim/envs/gym_assault_env.py` (`_GymActionController.act`) and `assault_sim/evaluation/eval_sb3.py` (`SB3EvalController.act`) force `StrategicIntent.CAPTURE` when objectives remain and no emergency | Pending smoke validation (`L3 CAPTURE share`, `vp_entry_missed_rate`, `capture_conversion_after_contact`) |
| CAPTURE near-VP anti-passivity fallback | `assault_sim/decision/option_executor_capture.py` -> `OptionExecutorCaptureMixin._capture_priority_action`: near VP (`<=3`) only accepts `objective_progress_move` (not lateral staging), and before final hold tries movement fallbacks (`forced_near_vp_no_hold_advance` / `forced_near_vp_no_hold_flank`) | Pending smoke validation (`fallback reason mix`, `vp_entry_missed_rate`, `capture_conversion_after_contact`) |
| CAPTURE near-VP attack gating by VP relevance | `assault_sim/decision/option_executor_capture.py` -> `OptionExecutorCaptureMixin._capture_priority_action`: when near VP and movement exists, suppress non-VP-relevant opportunistic attack fallbacks (`forced_attack_after_staging_loop`, `attack_gate_high_adv`/`attack_gate_near_vp_pressure`) and preserve VP-relevant attacks (`attack_gate_vp_target`, `attack_gate_defend_owned_vp`, `attack_gate_support_open_lane`) | Pending smoke validation (`attack_near_vp_instead_of_capture_rate`, fallback reason mix, `vp_entry_conversion_rate`) |
| CAPTURE step-in setup fallback near VP | `assault_sim/decision/option_executor_capture.py` -> `OptionExecutorCaptureMixin._best_stepin_setup_move` and `_capture_priority_action`: if no legal step-in and VP is near (`<=3`), prefer movement that lands in step-in setup geometry (`forced_stepin_setup_move`) before attack fallback; unconditional near-VP `forced_attack_near_vp_staging` path suppressed | Pending smoke validation (`vp_stepin_block_reason_counts.no_legal_stepin_near_vp`, `vp_entries_taken`, fallback reason mix) |
| CAPTURE setup validity gate (adjacent-only) | `assault_sim/decision/option_executor_capture.py` -> `OptionExecutorCaptureMixin._best_stepin_setup_move`: setup fallback is accepted only when resulting nearest-uncaptured-VP distance is `<=1`; rejects lateral false positives (`2->2`) | Pending smoke validation (trace quality of `forced_stepin_setup_move`, `no_legal_stepin_near_vp` trend) |
| CAPTURE unit selection bias by VP-entry potential | `assault_sim/envs/gym_assault_env.py` (`_GymActionController.select_best_unit`) and `assault_sim/evaluation/eval_sb3.py` (`SB3EvalController.select_best_unit`): when sampled strategy is CAPTURE, rank candidates by immediate step-in legality and nearest uncaptured VP distance, then pick within top-3 by unit slot; adaptive reliability penalty variant disabled after regression | Pending smoke validation (`unit_concentration_index`, `per_unit_vp_entry_attempts`, `vp_entry_conversion_rate`) |
| CAPTURE local interception unit bias for threatened owned VP | `assault_sim/envs/gym_assault_env.py` and `assault_sim/evaluation/eval_sb3.py`: `select_best_unit()` invokes `_defense_intercept_unit()` to pick closest local unit (<=3 hexes) when an owned VP is threatened at enemy distance <=1; no global strategy override | Pending smoke validation (`first_us_vp_loss_turn`, `unit_concentration_index`, global win/loss impact) |
| CAPTURE recently-lost VP retake priority (unit selection, disabled) | Retake-priority variant was tested in `assault_sim/envs/gym_assault_env.py` and `assault_sim/evaluation/eval_sb3.py` and then disabled after regression; CAPTURE unit selection uses baseline path | Pending redesign/validation before re-enabling (`time_to_retake_after_loss`, `captured_final_counts`, global win/loss impact) |
| CAPTURE anti-crowding objective focus | `assault_sim/decision/option_executor_capture.py` (`OptionExecutorCaptureMixin._objective_target_hex`): stronger ally-pressure penalty near VP target + extra crowding penalty when multiple allies are already near the same VP, to reduce single-objective jams | Pending smoke validation (`unit_concentration_index`, `per_unit_vp_entry_attempts`, `vp_stepin_block_reason_counts.no_legal_stepin_near_vp`) |
| Policy-side CAPTURE override only on concrete entry opportunities | `assault_sim/envs/gym_assault_env.py` (`_GymActionController.act`) and `assault_sim/evaluation/eval_sb3.py` (`SB3EvalController.act`) force CAPTURE only when objectives are pending, no emergency, and `stepin_legal` is true | Pending smoke validation (`forced_ratio`, VP-entry metrics, policy/executor alignment) |
| Reward shaping for VP step-in + retention | `assault_sim/rewards/progressive_reward.py` + `assault_sim/config/reward_config.py`/`reward_config.json`: add `vp_stepin_selected_bonus`, `vp_stepin_missed_near_penalty`, `vp_control_after_entry_bonus` to reinforce entry/hold behavior | Pending train/eval validation (`vp_stepin_selection_rate`, `vp_no_legal_stepin_near_count`, `vp_control_turns_share`) |
| Anti-retreat loop with pending objectives | `assault_sim/decision/option_executor.py`: under `PRESERVE`, fallback and assault role-bias prefer `ADVANCE` when uncaptured objectives remain; `assault_sim/envs/gym_assault_env.py` and `assault_sim/evaluation/eval_sb3.py`: CAPTURE override also activates under near-objective pressure (`nearest_vp_d <= 2`) | Pending train/eval validation (`RETREAT` share under objectives pending, `vp_contact_rate`, `first_vp_entry_turn`) |
| System pass advances activation order | `assault_model/runtime/game_state_runtime.py` (`RuntimeGameState.apply_action`): `WaitAction` triggers `next_activation()` even without attacker (`WAIT:SYSTEM`), preventing side lock and stale activation state in UI | Pending UI validation on Human-vs-AI turn transitions (marker reset and active-side alternation) |
| CAPTURE anti-deadlock rebalance (movement vs attack) | `assault_sim/decision/option_executor_capture.py` -> `_capture_priority_action`: constrain `forced_stepin_setup_move` to VP ring `2..3`; when near VP and staging streak persists, re-open VP-relevant/gated attacks (`forced_attack_near_vp_staging` + gated attack path) to prevent zero-damage collapse | Pending smoke validation (`fallback_to_attack_rate_in_capture`, `damage_ratio`, `capture_fallback_reason_counts`, VP-entry metrics) |
| Side-to-ownership mapping excludes neutral sentinel | `assault_model/state/game_state.py` -> `_build_side_ownership()` now maps sides only to controlled `HexOwnership` values (`SIDE_A`, `SIDE_B`), never `NONE`; prevents assigning a real side to neutral ownership and corrupting VP capture/winner metrics | Pending validation via `assault_model/tests/test_game_state_side_ownership.py` + smoke eval for VP/winner consistency |
| CAPTURE threatened-owned-VP defense helper (pre-gate disabled) | `assault_sim/decision/option_executor_capture.py` -> `_best_defend_owned_vp_action()` remains available as helper; `assault_sim/decision/option_executor.py` no longer invokes owned-VP defense in CAPTURE pre-gate after regression run | Pending redesign/validation before re-enabling (`first_us_vp_loss_turn`, global win/loss impact, forced-ratio impact) |
| Retreat anti-oscillation guardrail (Human-vs-AI stability) | `assault_sim/decision/option_executor.py` -> `OptionExecutor.execute()` (`RETREAT` branch) blocks immediate reversal retreat (`A->B->A`) under pending objectives + non-emergency + low close-threat, and falls back to ADVANCE; helper: `_enemy_count_within()` | Pending smoke validation (lower backtrack loops, fewer `retreat_reversal_blocked_low_threat`-eligible oscillations, stable VP pressure) |
