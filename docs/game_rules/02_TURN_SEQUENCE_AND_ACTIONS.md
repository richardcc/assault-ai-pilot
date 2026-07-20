# 02 - TURN SEQUENCE AND ACTIONS (Execution Contract)

Primary source: Rulebook v2.0 (chapters 6 to 11).

## 1. Phase Order (Hard Constraint)

The engine must process phases in this exact order:

1. Initiative Phase
2. Planning Phase
3. Support Phase
4. Action Phase
5. Organization Phase
6. Victory Check Phase
7. Reinforcements Phase

## 2. Phase Responsibilities

### Initiative

- Determine initiative holder.
- Apply initiative-linked scenario hooks.

### Planning

- Assign command resources/cards (if enabled).
- Register deferred support requests (TAS/OAS optional flow).

### Support

- Execute support actions (indirect fire, smoke, support abilities).
- Apply support-side state updates before action phase.

### Action

- Resolve activations and tactical actions:
  - movement,
  - ranged fire,
  - close combat,
  - special actions.

### Organization

- Resolve status maintenance/cleanup.
- Apply end-of-turn marker transitions.

### Victory Check

- Evaluate scenario victory conditions.
- Set terminal state if conditions are satisfied.

### Reinforcements

- Deploy scenario/campaign reinforcements.

## 3. Action Domain Taxonomy

### Movement

- normal/fast movement,
- move-and-fire variants when legal,
- hide/ambush movement interactions,
- objective-entry and capture effects.

### Ranged Fire

- direct and indirect modes,
- LOS/spotting validation,
- dice resolution and critical routing.

### Close Combat

- initiation conditions,
- round-level attack/defense modifiers,
- fallback/elimination closure behavior.

### Special Actions

- pass,
- reaction fire,

Reaction fire runtime status (current):

- integrated behind feature flag `ASSAULT_ENABLE_REACTION_FIRE` (default ON),
- runtime hook is in `assault_model/runtime/game_state_runtime.py`,
- deterministic reactor selection: first eligible enemy reactor by `unit_id`, max one reaction per reactor per turn, and reaction consumes reactor activation,
- human-controlled reaction windows are now supported: when reactor side is human, runtime opens a pending decision (`pending_reaction`) instead of auto-firing,
- unit validation: `assault_model/tests/test_runtime_reaction_fire_flag.py`,
- full interrupt-order/UI-flow E2E parity remains pending for production hardening.

## 4. RL Guardrail Traceability (P4.3c)

Validation state: **Pending Validation**.

- In CAPTURE-context decisions, runtime guardrails may enforce movement priority.
- Overrides are now explicitly traced per decision with:
  - `capture_emergency_override`
  - `capture_legal_override`
  - `capture_override_reason`
- Strategy intent sampling in Gym training/eval controller is per-activation (not locked for full turn) to reduce turn-wide intent collapse.
- Strategy intent sampling in SB3 evaluation controller is also per-activation (turn-wide lock removed) to keep eval behavior aligned with Gym runtime.
- Operational mapping:
  - decision source: `assault_sim/decision/option_executor.py`
  - activation strategy source: `assault_sim/envs/gym_assault_env.py` (`_GymActionController.act`)
  - info propagation: `assault_sim/training_env.py`
  - trace persistence: `assault_sim/evaluation/record_sb3_trace.py`
  - aggregation/reporting: `assault_sim/evaluation/evaluator.py`, `assault_sim/evaluation/results_analyzer.py`
- Side attribution contract (training/eval telemetry): combat `damage/kills` must be
  attributed by normalized side key (`actor_side_norm` vs `rl_side_norm`) because
  runtime side values may be enum-like objects (`side.value`) while `rl_side` is a
  plain string. Validation state: **Pending Validation**.
- CAPTURE distance-progress diagnostics (observability-only, no rules change):
  - `capture_progress_available`: at least one legal move reduced distance to an uncaptured VP.
  - `capture_suspected_progress_miss`: progress existed but selected move reason was not `objective_progress_move`.
  - candidate counters: `capture_progress_candidates`, `capture_equal_candidates`, `capture_increase_candidates`, `capture_reversal_filtered`.
  - intent: detect possible distance/progress selection anomalies before changing tactical policy.
- CAPTURE movement priority rule (behavioral guardrail):
  - when at least one legal CAPTURE move reduces distance to an uncaptured VP, selector must choose a `objective_progress_move`.
  - lateral `objective_staging_move` is allowed only when no progress move exists.
  - for CAPTURE-forced `ADVANCE`, movement selection uses strict objective distance priority and prefers non-worsening moves when available.

## 5. Objective/Reward Runtime Parameterization (MuZero + EfficientZero v2)

Validation state: **Pending Validation**.

- Objective and reward-shaping runtime behavior is now configured from YAML, with legacy-compatible defaults injected by `agents/muzero/configs/config_loader.py`.
- EfficientZero v2 objective/reward runtime defaults are locally injected by `agents/efficientzero_v2/core/interop.py` and surfaced in run/report contracts (`run_manifest.json`, objective/reward tab in `mlops/reporting/viewer.py`).
- EfficientZero v2 action-level VP diagnostics now include candidate comparatives with fallback-safe VP deltas (`mcts_action_candidates[*].vp_progress_delta`, `why_action_vs_vp`) from `agents/efficientzero_v2/core/selfplay.py`.
- EfficientZero v2 root-value producer contract now avoids action-value broadcast: selfplay passes policy priors only when action-conditional values are unavailable, and MCTS uses deterministic prior-based fallback values (`agents/efficientzero_v2/core/selfplay.py` -> `_priors_and_values`, `agents/efficientzero_v2/core/mcts.py` -> `run_mcts_puct` fallback branch).
- EfficientZero v2 optional multi-VP auxiliary objective contract is available in training (`aux_objective_enabled`, `aux_objective_loss_weight`, `aux_intent_loss_weight`, `aux_multi_vp_loss_weight`, `aux_multi_vp_feature_dim`, `aux_intent_classes`) and consumed by `agents/efficientzero_v2/train/trainer.py`.
- Objective signal opportunity window is configurable (`train.objective_signal.opportunity_near_vp_max_dist`) and consumed by `agents/muzero/core/selfplay.py` -> `objective_step_signal(...)`.
- Objective head label behavior is configurable (`train.objective_head.progress_positive_threshold`) and consumed by:
  - `agents/muzero/train/trainer.py`,
  - `agents/efficientzero_v2/train/trainer.py`.
- Objective diagnostics/objective-path thresholds are configurable (`train.objective_reporting.*`) and consumed by:
  - `agents/muzero/train/train_muzero.py` (near-vp, confidence and assault context thresholds),
  - `agents/efficientzero_v2/train/train_engine.py` (conversion window and assault context thresholds).
- Run-level reporting now surfaces active objective/reward parameters in a dedicated tab (`Objective/Reward Config`) in `mlops/reporting/viewer.py`, including source precedence (`run_config` vs `fallback_default` vs `legacy_missing`).
  - when CAPTURE remains in `objective_staging_move` while near VP (`<=2`), fallback forces an attack (`forced_attack_near_vp_staging`) to break local loops.
  - relaxed CAPTURE attack fallback is constrained to VP-relevant targets (enemy/neutral VP holders or threats on owned VP).
  - VP-window opening guardrail: when near VP (`<=3`) without legal step-in and movement is blocked/staging (or any near-VP no-step-in streak), force VP-lane-opening attack (`forced_attack_open_vp_window`) including threats adjacent to uncaptured VP, with anti-spam per-unit throttle (max once every 2 CAPTURE decisions).
  - per-unit CAPTURE focus lock (short TTL) keeps the same VP target for a few activations to reduce target ping-pong when no progress is available.
  - all CAPTURE guardrails are gated by `capture_guardrails_enabled` (train config) to support A/B validation against non-guardrail behavior.
  - aggressive L3 enforcement: with pending objectives and no emergency, attacker-side intent is forced to `CAPTURE` (`aggressive_l3_capture_force`) to prevent collapse into `PRESERVE`.
  - L3 CAPTURE quota guardrail: per side/turn, enforce a minimum CAPTURE-intent quota (`minimum_capture_intent_quota`) under pending objectives and no emergency; telemetry includes `l3_capture_forced_count/rate` and reason histogram.
  - near-VP conversion guardrail: with `nearest_vp_d <= 2`, CAPTURE prioritizes movement progression/entry and blocks non-VP attack drift unless explicitly opening VP lane.
  - CAPTURE movement selector now optimizes toward the uncaptured VP **adjacent ring** (not only VP center), with enemy-pressure-aware scoring and stronger anti-lateral penalty near VP.
  - CAPTURE + fire-support coupling: support-class units near VP (`dist 2..3`) can prioritize lane-opening attacks on threats adjacent to uncaptured VP (`attack_gate_support_open_lane`), while low-value non-lane high-adv attacks are de-prioritized to reduce attrition drift.
  - Post-opening conversion guardrail: after `forced_attack_open_vp_window`, next CAPTURE decision for that unit prioritizes a non-worsening follow-up advance (`post_open_window_followup_advance`) with success telemetry (`post_open_window_followup_success_rate`); low-quality opening attacks trigger short cooldown.
- ATTRIT/DENY anti-collapse guardrail: when strategy is `ATTRIT` or `DENY`, and a legal immediate attack exists (outside strict near-VP CAPTURE budget context), `ADVANCE` is remapped to `ATTACK` to avoid low-pressure movement loops.
- Reward coherence shaping: `ProgressiveReward` now adds explicit bonus for real attacks under `ATTRIT`/`DENY` and applies contextual penalty to `ADVANCE` in those intents (validation pending).
- CAPTURE force de-escalation: global CAPTURE forcing is now limited to near-objective pressure (`nearest_vp_d <= 2`) and primarily for `PRESERVE`; `DENY` is only remapped to CAPTURE near objective when no immediate legal attack exists.
- CAPTURE budget overrides scope: soft/hard near-VP budget overrides now apply only when current strategy is `CAPTURE`, reducing unintended `ATTACK -> ADVANCE` coercion in `ATTRIT`/`DENY`.
- ATTACK execution contract: in `ATTACK` option, if no legal attack exists, executor may reposition only when movement improves pressure/progress (`no_legal_attack_reposition`); otherwise it falls back to hold (`no_legal_attack_hold_no_progress`). Explicit CAPTURE path can still use move fallback (`no_legal_attack_move_fallback`). All paths are traced in mission telemetry.
- ATTACK micro-reposition quota: non-progress tactical reposition fallback from `ATTACK` is budget-capped per side/turn (small quota) and requires survivability/tactical gain (terrain/pressure) to avoid reopening uncontrolled `ATTACK -> ADVANCE` drift.
- ATTACK micro-reposition quota is context-aware: near uncaptured VP (`nearest_vp_d <= 3`) can widen the shared per side/turn fallback budget (v8: near cap 3 per side/turn), while far-from-objective contexts keep the stricter cap (1) to preserve local conversion pressure without reopening global drift.
- ATTACK fallback objective contract (v9): when no legal shot exists, fallback reposition may also pass by objective-ring progress (`no_legal_attack_objective_push`) or one-turn contact setup proxy (`no_legal_attack_contact_setup`); in near-VP contexts, if generic reposition fails but `move_closer(capture_strict=True)` yields objective progress, executor applies bounded `no_legal_attack_forced_objective_push` instead of default hold.
- ATTACK fallback legal-followup contract (v10): no-shot fallback now prioritizes reposition candidates that generate a **real legal follow-up attack** under simulated post-move state (`no_legal_attack_legal_followup_setup`), then applies objective/contact/pressure gates; this aims to change effective behavior (not only reason relabeling) while keeping per-turn budget limits.
- ATTACK near-VP hard gate (v11): in near-objective context, no-shot fallback no longer accepts weak pressure/contact-only reposition; it now requires either simulated legal follow-up attack setup or explicit objective-progress move, otherwise attempts strict objective push and then falls back to hold.
- ATTACK near-VP legal hard gate (v12): in near-objective context, no-shot fallback reposition now requires simulated legal follow-up attack **and** tangible progress signal; strict objective push is accepted only with both objective progress and legal follow-up. If none exist, fallback records `no_legal_attack_no_followup_near_vp` and holds.
- ATTACK legal-followup diagnostics (v13): near-VP no-followup hold reason now carries a structured diagnostic suffix (`no_legal_attack_no_followup_near_vp:<detail>`) that distinguishes `reposition_followup_*` and `objective_push_*` failure modes (e.g., deepcopy/action-catalog failure vs no legal attacks after move), enabling root-cause attribution in eval telemetry.
- ATTACK near-VP fire-window fallback (v14): when no legal immediate follow-up shot exists, near-VP fallback may still accept objective-progress reposition if it clearly improves local fire window geometry (enemy distance reduced into <=3 band), traced as `no_legal_attack_fire_window_setup` or `no_legal_attack_forced_fire_window_push`; this is bounded by the same per-turn fallback budget.
- Anti-zigzag movement stabilization (v15): for non-RETREAT movement intents (`ADVANCE`/`FLANK`), if chosen movement causes immediate reversal (`A->B->A`) under low-threat context (`enemy_count_within radius=2 == 0`) while objectives are pending, executor blocks the reversal; if resulting move is non-displacing (same-hex), it falls back to explicit `WAIT` (`non_displacement_move_wait_fallback`) instead of inventing replacement movement.
- Retreat pressure guardrail (v16): when objectives remain uncaptured and no emergency is active, low local threat (`enemy_count_within radius=2 <= 1`) blocks `RETREAT` and remaps to `ADVANCE` (`retreat_blocked_low_threat_objective_pressure`) to avoid passive fallback loops in Human-vs-AI even if the opponent also disengages.
- Turn-start first-player anchor (v17): runtime now preserves a stable first-player side across turns (`first_player_side`) and re-applies it at each new turn when that side still has available activations; if unavailable, activation falls forward deterministically to the next side with available units.
- PPO/reward anti-plateau retune (v4): training config increases exploration (`ENTROPY_COEF` raised to `0.07` in `assault_sim/config/ppo_config.py`) and reward config increases passive non-attack hold penalty (`hold_non_attack_penalty=0.36` in `assault_sim/config/reward_config.json`) to reduce stable local minima dominated by no-progress hold behavior.
- Opening-turn anti-retreat pressure lock (v18): when objectives are pending and no emergency is active, `RETREAT` is blocked in turns `<=3` and remapped to `ADVANCE` (`retreat_blocked_opening_turn_pressure`) to prevent early passive disengagement loops in Human-vs-AI.
- Objective shortfall reward shaping (v19): `ProgressiveReward` now applies per-step shortfall penalty when tracked-side controlled VP count is below campaign target ratio (`objective_control_target_ratio`), plus extra terminal shortfall penalty on tracked-side objective defeat. Purpose: teach policy that delaying/avoiding VP capture directly increases loss risk, not only at end-of-episode.
 - Training/eval action finalizer parity (v20): Gym and SB3 eval controllers now finalize RL-selected actions against current `ActionCatalog` before execution (`_finalize_rl_action`), reject non-displacement pseudo-moves, and prioritize immediate legal step-in to uncaptured VP when available (`_catalog_priority_action`). This aligns learned behavior with runtime execution constraints and reduces invalid-policy drift.
 - Multi-turn mission planner contract (v21): a dedicated planner context (`intent`, `stage`, `focus_vp_id`, commitment TTL/replan reason) is produced per activation and injected into tactical execution. Runtime (`/api/game/ai-turn`), Gym controller, and SB3 eval controller pass planner context into `OptionExecutor.execute(...)` so plan stage (`SETUP`/`STEP_IN`/`HOLD`) can bias option resolution before final legality checks.
 - R2.1 learning-side finalization pressure (v22): reward now penalizes invalid/fallback finalization outcomes (`not_in_catalog`, `empty_action_id`, `non_displacement`) and penalizes `wait_recovery_sb3_backstep` specifically in planner `SETUP`, while evaluator/analyzer expose hard KPIs (`invalid_action_rate`, `fallback_rate`, `wait_recovery_sb3_backstep_rate`) for promotion gating.
 - Planner-tagging normalization (v23): diagnostics now normalize staged planner intent `SETUP_CAPTURE` as CAPTURE-compatible for `intent_alignment_stub`, and reduce role-tag drift to `UNKNOWN` by assigning stable fallback roles (`ASSAULT` for ATTRIT contexts, `SCREEN` as maneuver fallback).
 - Planner intent steering (v24): planner-managed execution now applies intent-aware strategy/option shaping before tactical guardrails (`CAPTURE`/`SETUP_CAPTURE` avoid passive `HOLD/RETREAT`; `ATTRIT` avoids retreat default), reducing short-horizon drift during `SETUP`.
- Team Intent + active role mapping (v25): `MissionPlanner` now selects team intent from contextual signals (VP control balance, nearest VP distance, local enemy pressure), while `role_mapper` assigns per-activation roles using unit profile plus tactical state. L2 option resolution applies role+intent weighted scoring and writes explicit plan fallback reason (`intent_blocked`, `budget_exhausted`, `emergency_override`) into trace/report telemetry.
- P4.2 stuck/missed retune (v25-b): planner-managed stagnation (`blocked_steps>=2`) rotates intent between `CAPTURE` and `DENY`, role tagging forbids normal `UNKNOWN` fallbacks (deterministic strategy-based fallback), and near-VP (`<=3`) CAPTURE contexts bias `ADVANCE` over opportunistic `ATTACK` to reduce missed VP entries.
- P4.2 stabilization rollback (v25-c): removed blocked-step CAPTURE/DENY rotation introduced in v25-b (regressed loss/stability), and hardened anti-`UNKNOWN` role fallback at `_tag_action` as a last-mile guarantee while keeping near-VP CAPTURE `ADVANCE` bias.
- P4.3a budget observability (v26): plan trace/info now includes `budget_remaining_by_role`, `budget_violation_count` and `budget_violation_delta`; evaluator/analyzer expose aggregate `budget_compliance_rate` and `budget_violation_rate` so budget guardrails can be validated as contract metrics without adding new tactical coercions.
- T-telemetry-v1 (v27): pre-training diagnostics now emit role-unknown causes (`plan_role_unknown_reason_counts`), CAPTURE branch usage (`capture_branch_counts`), near-VP transition matrix (`sampled->resolved->action_class`), and mission latency signals (`turn_first_contact/progress/capture`, `contact_to_progress_delay`, `progress_to_capture_delay`) to reduce blind tuning before reward retraining.
- R2.1-a kickoff (v28): reward now penalizes near-VP CAPTURE `ADVANCE` moves that fail to produce conversion/progress, and rewards post-contact `objective_progress_move` decisions that improve objective distance; progress latency telemetry is constrained to post-contact progress to avoid negative delay artifacts.
- R2.1-b capture-conversion retune (v30): reward shaping increases objective/capture pressure (`vp_delta_weight`, `objective_approach_bonus`, `capture_strategy_bonus`, VP entry/retention bonuses), and increases penalties for CAPTURE no-progress loops and CAPTURE->ATTACK fallback when progress windows exist near VP.
- CAPTURE near-VP attack deconfliction (v30): `forced_attack_open_vp_window` and `forced_attack_near_vp_staging` no longer trigger when a legal CAPTURE progress move exists; gated CAPTURE attacks are also suppressed in progress-available states except VP-critical cases.
- SB3 curriculum/eval contract (v30): training schedule supports a two-phase same-scenario curriculum (capture warmup then full phase), with phase-1 CAPTURE-forced intent via env overrides and shorter/frequent tuning eval (`sb3_eval_freq=5000`, `sb3_eval_episodes=20`).
- Telemetry latency contract hardening (v29): `contact_to_progress_delay` and `progress_to_capture_delay` are reported only for valid temporal orderings (`contact <= progress <= capture`); invalid sequences now surface via counters (`latency_invalid_order_count`, `latency_missing_progress_count`, `latency_missing_capture_count`) instead of misleading negative delays.
- R2 helper 1 (v30): reward pipeline now emits lightweight component attribution (`reward_component_means`) so tuning can separate dominant signals (e.g. trade/objective/near-VP penalties) from residual `unattributed` mass before launching longer retrains.
- R2.1-b retune-1 (v31): reward balance shifts back toward objective play by lowering combat-only pressure (`trade_weight`), penalizing non-CAPTURE strategy when near VP under pending objectives, and rewarding support-fire damage in CAPTURE post-contact windows.
- R2.1-b retune-2 (v32, Pending Validation): conservative rollback from v31 restores intermediate combat pressure (`trade_weight=0.80`), keeps near-VP anti-drift penalty (`non_capture_near_vp_penalty`), and halves CAPTURE support-fire amplification (`capture_support_fire_window_bonus`) to reduce over-steering risk.
- Planner role contract hardening (v33, Pending Validation): role resolution is centralized in `role_mapper.resolve_role_with_reason(...)` and runtime tagging no longer emits `UNKNOWN` in normal flows; fallback reasons are explicit (`fallback_*`) and traceable via `plan_role_unknown_reason`.
- R2.1-b retune-3 (v34, Pending Validation): conversion-oriented rebalance lowers CAPTURE no-progress/fallback penalties from v30 to avoid over-braking, increases post-contact progress reward (`capture_post_contact_progress_move_bonus`), and raises objective delta pressure (`vp_delta_weight`) while keeping near-VP anti-drift active.
- R2.1-b multi-seed short decision (v34 package, Pending Validation): short gate run (`seed=42/43/44`, 10 eps each) results in operational **NO-GO** (`true_win_rate=0`, high `loss_rate`, no `vp_entry_missed_rate` relief), so next R2.1 loop is constrained to a single reward lever with planner changes frozen.
- R2.1-c formal confirmation (v34 package, Pending Validation): confirmation run (`seed=42/43/44`, 20 eps each) preserves **NO-GO** (`true_win_rate=0`, `loss_rate` high, `vp_entry_missed_rate` high, `objective_delta_term` inactive), so planner remains frozen and next loop is `R2.1-d` single-lever tuning (`vp_delta_weight` only).
- R2.1-d single-lever kickoff (v35, Pending Validation): reward tuning changes only `vp_delta_weight` (`10.0 -> 12.0`) to isolate objective-pressure effect; no additional reward/planner changes are allowed in this cycle until short multi-seed results are reviewed.
- R2.1-g single-lever CAPTURE priority (v45, Pending Validation): reward tuning changes only `capture_strategy_bonus` (`0.60 -> 0.90`) to increase CAPTURE strategic mass before conversion, with planner/guardrails/finalizer levers frozen for attribution cleanliness.
- R2.1-h single-lever post-contact conversion (v46, Pending Validation): reward tuning changes only `capture_post_contact_progress_move_bonus` (`0.70 -> 1.00`) to reinforce objective-progress moves after first contact, keeping planner/guardrails/finalizer and other reward levers unchanged.
- MuZero VP event shaping alignment (v47, Pending Validation): MuZero self-play reward now credits objective progress from observed state transitions (`vp_captures` and side VP net delta) instead of relying only on action-id CAPTURE string patterns, via `agents/muzero/core/selfplay.py::shaped_training_reward`; new reward components are `vp_capture_event`, `vp_net_gain`, and `vp_net_loss`.
- MuZero unit-capability observation channels (v48, Pending Validation): CNN observation encoding now includes per-unit normalized mobility, direct-range, indirect-range, attack-power, and defense-power planes by side (ally/enemy pairs), derived from `assault_sim/assets/catalogs/unit_catalog.json` and projected in `agents/muzero/core/selfplay.py::observation_to_tensor`.
- MuZero VP opportunity instrumentation alignment (v49, Pending Validation): self-play now infers `legal_capture_options` from legal action destinations on enemy/neutral VP hexes (not only CAPTURE/VP string markers), and training aggregates treat VP gain/capture events as objective-action evidence so `capture_actions_total` and objective-opportunity conversion reflect real VP transitions.
- MuZero reaction fire as explicit decision option (v50, Pending Validation): VOEC simulator exposes reaction-window choices as legal actions (`OPPORTUNITY_FIRE:<reactor>:<target>` and `OPPORTUNITY_SKIP:<reactor>:<target>`) instead of auto-resolving AI reactions, so the learning policy can decide whether to consume reactor activation.
- MuZero reaction-fire efficiency shaping (v51, Pending Validation): reward shaping adds `reaction_fire_miss_penalty` applied when `OPPORTUNITY_FIRE` deals no damage and causes no kill, to reduce low-value reaction shots that consume activation without objective progress.
- MuZero opportunity-phase VP tradeoff shaping (v59, Pending Validation): in reaction windows, objective-aware weighting now distinguishes `OPPORTUNITY_FIRE` vs `OPPORTUNITY_SKIP` under near-VP opportunity context using YAML knobs in `selfplay.reward_shaping`:
  - `opportunity_fire_no_progress_penalty`: extra penalty for `OPPORTUNITY_FIRE` when near VP and the action does not preserve objective progress.
  - `opportunity_skip_capture_preserve_bonus`: positive shaping for `OPPORTUNITY_SKIP` when it preserves imminent VP-capture potential (no immediate capture available yet).
  - `opportunity_vp_distance_threshold`: activation window for the two rules above.
  - Rule-to-code-to-test mapping: `agents/muzero/core/selfplay.py::shaped_training_reward` -> `agents/muzero/tests/test_reward_targets.py` (`test_shaped_reward_prefers_opportunity_skip_to_preserve_near_vp_capture`, `test_shaped_reward_keeps_opportunity_fire_when_tactically_strong`).
- MuZero objective progress funnel instrumentation (v52, Pending Validation): transition telemetry now records objective-distance delta to nearest uncaptured VP (`objective_distance_before/after`, `objective_progress_delta`) and conversion flags (`objective_had_opportunity`, `objective_converted`); run diagnostics add `objective_progress_funnel` (opportunity/progress/conversion/stall rates) to support capability-driven tuning.
- MuZero/EfficientZero objective conversion retune (v57, Pending Validation): conservative objective-path reward tuning raises `objective_progress_bonus_per_hex` (~+15%), strengthens no-progress penalties in opportunity states (`objective_no_progress_penalty`, `objective_no_progress_attack_penalty`), and increases VP conversion event bonus (`vp_capture_bonus_per_hex`) to improve `objective conversion on opportunities` without touching damage/kill shaping or MCTS core.
- MuZero eval objective-distance parity (v56, Pending Validation): benchmark/eval trace now computes and serializes VP-distance objective signals per step using the same base logic as self-play (`objective_min_dist_before/after`, `objective_progress_delta`, `objective_best_vp_id`, `vp_distance_vector`), and `objective_had_opportunity` is derived from legal capture windows plus distance-reduction opportunities. Eval head telemetry marks `objective` as `complete` when these distances are present, removing legacy `objective_distance_not_in_eval_pipeline` partials on new runs.
- MuZero/EfficientZero objective target filtering hardening (v60, Pending Validation): objective-target selection now normalizes VP owner-map keys by coordinates and excludes already-owned VPs from capture-progress signals by default (`objective_best_vp_id`, `objective_min_dist_*`, `objective_progress_delta`, opportunity flags). Optional owned-VP inclusion is available only through explicit defense gating inputs (`include_owned_for_defense`, `defendable_vp_ids`) and is OFF by default.
- Attack effectiveness calibration telemetry (v61, Pending Validation): benchmark/eval decision summary now aggregates attack-quality diagnostics across action/side and combat-context buckets (`E[dmg]`, damage variance, exchange win-rate, attack-good Brier/calibration bins) to quantify whether high-confidence attack choices are actually effective under sampled combat outcomes.
- EfficientZero v2 expected-damage proxy feature injection (v61, Pending Validation): selfplay now computes a fast analytical proxy `expected_damage(attacker, defender, distance, cover, los)` from unit combat tables and injects it into model-facing spatial channels and per-candidate action telemetry (`expected_damage_proxy`) without changing policy scoring by default.
- MuZero/EZv2 sampled-expectation chance handling in MCTS (v61, Pending Validation): `run_mcts_puct` now supports optional `sampled_expectation` backup (`mcts_chance_mode`, `mcts_chance_samples_per_expansion`, `mcts_chance_value_noise_std`), defaulting to `off` for backward compatibility and runtime safety.
- EfficientZero v2 VP-horizon soft channel (v62, Pending Validation): selfplay computes bounded VP-horizon telemetry (`vp_horizon_steps`, `vp_horizon_signal`) and applies a conservative soft decision term (`vp_horizon_decision_component`) in candidate ranking; defaults are `reward_shaping.vp_horizon_soft_enabled=true`, `reward_shaping.vp_horizon_soft_weight=0.02`, `reward_shaping.vp_horizon_soft_cap_steps=8.0`, and viewer eval diagnostics expose channel-level usage/coverage under the `Eval Metrics` tab.
- Phase-2 unit-prefilter observability wiring (Pending Validation): benchmark/eval step telemetry forwards unit-prefilter producer fields (`unit_prefilter_enabled`, `unit_prefilter_selected_unit_id`, `unit_prefilter_constrained_count`, `unit_prefilter_global_count`) into `eval_decision_steps_top`; reporting catalog preserves them in `eval_history.results[*].eval_decision_steps_top[*]`; viewer diagnostics surface them in `Eval Metrics` channel rows, `Eval Metrics` per-step tables, and `Decision Influence` info lines with producer-first `N/A` fallback semantics when producers omit fields.
- MuZero objective auxiliary head (v54, Pending Validation): model prediction trunk includes a dedicated objective logit head (`prediction_objective`) trained with masked class-balanced BCE over objective-opportunity samples (`objective_had_opportunity`) against progress labels (`objective_progress_delta > 0`), with knobs `train.objective_loss_weight`, `train.objective_target_mode`, and `train.objective_pos_weight`; `objective_loss` tracks whether latent state is learning progress-relevant structure instead of sparse end conversion only.
- Eval VP opportunity metric unification (v58, Pending Validation): benchmark/eval aggregate objective metrics now use one primary opportunity definition aligned with per-step telemetry (`objective_had_opportunity`). `eval_vp_capture_opportunity_steps` is the sum of per-step opportunities, while strict immediate-window opportunities are tracked separately as `eval_vp_immediate_capture_opportunity_steps` and now mean "at least one legal `MOVE` can land on an enemy/neutral VP hex". Immediate taken now means chosen `MOVE` lands on that capturable VP hex and ownership transitions to acting side in post-step state. Conversion/take rates expose explicit denominator counters (`eval_vp_capture_take_rate_denominator_steps`, `eval_vp_conversion_efficiency_denominator_steps`) and viewer labels clarify both semantics.
- MuZero phase-2.9 reaction/assault benchmark gate (v55, Pending Validation): benchmark now computes reaction-window and assault/melee KPIs in eval (`phase_2_9_eval_kpis`) and compares them against train metrics (`phase_2_9_train_eval`), then emits promotion gate status (`phase_2_9_promotion_gate`) with explicit checks and fail-fast misuse blocks.
- Eval source-mix diagnostics (v36, Pending Validation): mission report now separates decisions into `sb3_kept`, `planner_override`, and `finalizer_override`, and prints per-bucket capture-event rates so we can distinguish policy weakness from override-driven behavior during eval.
- Eval minimal-overrides diagnostic mode (v37, Pending Validation): `eval_sb3 --diagnostic-min-overrides` disables planner-like eval coercions (step-in option forcing and mission-priority CAPTURE forcing) while preserving legality finalization, to compare hybrid control against a more SB3-kept behavior baseline.
- SB3 artifact workspace partitioning (v38, Pending Validation): training/eval can target a scoped model directory via `sb3_models_subdir`; cleanup now removes only artifacts for configured `rl_sides` within that workspace, enabling safe parallel side training without cross-run deletion.
- Backend SB3 model routing by scenario+side (v40, Pending Validation): runtime inference now resolves checkpoints and vecnormalize stats by `(scenario, side)` key before fallback, using `sb3_models_subdir_template` from `assault_sim/config/train_config.json` (default: `scenario_{scenario}/side_{side}`) and legacy flat `models/` compatibility.
- Train/eval template auto-resolution (v41, Pending Validation): `train_sb3` and `eval_sb3` now resolve model workspace through `TrainConfig.resolve_models_subdir(scenario, side)`, so artifact write/read paths follow the same `sb3_models_subdir_template` automatically without manual `sb3_models_subdir` edits per run.
- Eval config-path override (v42, Pending Validation): `eval_sb3` now supports `--config <path>` (same as `train_sb3`) so multi-run validation can point to per-run `train_config` files without overwriting the workspace default config.
- Objective-only win criterion for eval summaries (v43, Pending Validation): evaluation summary metrics now treat scenario `tracked_result` as canonical (`Vittoria*` => win, `Pareggio` => draw, others => loss), and comparative labels explicitly reference objective criterion to avoid mixing runtime `winner` with objective-table outcomes.
- Side-asymmetry action-generation diagnostics (v44, Pending Validation): eval mission metrics now include legal-action volume and generation latency (`avg_legal_actions_per_decision`, `mean_action_catalog_gen_ms`) both aggregated and by side, to compare CPU/tactical asymmetry before tuning throughput.
- R2.1-d.1 legality-pressure retune (v39, Pending Validation): before next train, increase only `invalid_action_finalization_penalty` (`0.20 -> 0.50`) to reduce invalid/finalizer-corrected actions while keeping planner and other reward levers unchanged.
- Eval scenario dedupe contract (v34): SB3 evaluation now deduplicates repeated `scenario_schedule` entries by `scenario id` before running side/scenario loops, preventing duplicate comparative rows when curriculum phases reuse the same scenario.
  - R4 policy-redesign skeleton: Gym/SB3 eval controllers expose a legal step-in mask proxy (`stepin_legal_mask`) and optional option bias (`stepin_forced_option`) that nudges `ADVANCE` when CAPTURE has an immediate legal VP entry.
  - CAPTURE `move_block_profile` is always populated (no `unknown`) for traceability.
  - diagnostic mode: `diagnostic_force_capture_only=true` forces attacker-side L3 to `CAPTURE` (unless emergency) to isolate whether failures come from strategic intent collapse.
  - VP entry observability captures:
    - legal step-in opportunities (`vp_stepin_legal_count`)
    - selected step-ins (`vp_stepin_selected_count`)
    - selection ratio and block reasons (`vp_stepin_block_reason_counts`)
  - explicit near-VP no-stepin blocker (`no_legal_stepin_near_vp`) to separate "no legal entry" from strategy-choice misses
  - nearest uncaptured objective distance per decision (`vp_nearest_uncaptured_dist`) for CAPTURE funnel localization
  - opening-lane candidates count (`vp_opening_attack_candidates_count`) to diagnose whether forced opening attacks fail by branch priority or lack of valid targets
    - control persistence after entry (`vp_control_after_entry_turns_p50/p90`)
    - per-unit entry attempts/success (`per_unit_vp_entry_attempts`, `per_unit_vp_entry_success`)
- Rule-to-code-to-test mapping (Pending Validation):
  - Rule: adjacency to already-owned VP must not be counted as objective capture progress/opportunity unless explicit defense gating is enabled.
  - Code: `agents/muzero/objective_signals.py` (`_owner_by_qr`, `_enemy_vp_candidates`, `objective_min_distance_snapshot`, `objective_step_signal`) and `agents/efficientzero_v2/core/objective_signals.py` (`_owner_by_qr`, `objective_min_distance_snapshot`, `objective_step_signal`); supporting diagnostics filter in `agents/efficientzero_v2/core/selfplay.py` (`_best_enemy_vp_qr_for_side`).
  - Test: `agents/muzero/tests/test_objective_signals.py` (`test_objective_signal_excludes_owned_vp_from_progress_and_opportunity`, `test_objective_signal_keeps_non_owned_vp_progress_behavior`) and `agents/efficientzero_v2/tests/test_selfplay_native_contract.py` (`test_native_selfplay_ignores_owned_vp_in_objective_progress_diagnostics`).
  - Rule: action selection diagnostics should expose explicit VP-progress comparisons with robust fallback (no parse-only N/A collapse).
  - Code: `agents/efficientzero_v2/core/selfplay.py` (`mcts_action_candidates`, `why_action_vs_vp`, `vp_progress_source`).
  - Test: `agents/efficientzero_v2/tests/test_selfplay_native_contract.py::test_native_selfplay_vp_candidate_fallbacks_are_present`.
  - Rule: root value output from policy/value producer must not be broadcast as per-action values when action-conditional estimates are unavailable.
  - Code: `agents/efficientzero_v2/core/selfplay.py` (`_priors_and_values` no-broadcast contract + fallback telemetry fields), `agents/efficientzero_v2/core/mcts.py` (`run_mcts_puct` deterministic no-values fallback).
  - Test: `agents/efficientzero_v2/tests/test_selfplay_native_contract.py` (`test_priors_and_values_do_not_broadcast_root_value_across_actions`, `test_native_selfplay_reports_mcts_action_value_fallback_usage`).
  - Rule: VP conversion credit assignment may include a bounded horizon-aware soft term, but must remain optional and producer-observable.
  - Code: `agents/efficientzero_v2/core/selfplay.py` (`_vp_horizon_soft_components`, `mcts_action_candidates[*].vp_horizon_*`, `info.vp_horizon_*`), `agents/efficientzero_v2/core/interop.py` + `agents/efficientzero_v2/configs/efficientzero_v2_config*.yaml` (`vp_horizon_soft_*` defaults/knobs), `mlops/reporting/viewer.py` (`renderEvalMetrics` tab).
  - Test: `agents/efficientzero_v2/tests/test_selfplay_native_contract.py` (`test_native_selfplay_vp_horizon_soft_term_can_break_near_ties`), `agents/efficientzero_v2/tests/test_config_loader_objective_defaults.py`, `mlops/tests/test_reporting_viewer_replay_filter.py` (`test_model_html_includes_eval_metrics_channel_diagnostics_tab_and_hooks`).
  - Rule: phase-2 unit-prefilter telemetry must remain producer-visible across benchmark schema, reporting catalog, and replay diagnostics, without inventing fallback planning data.
  - Code: `assault_bench/runner.py` (`_run_episode_with_policy`, `_build_eval_decision_steps_top`), `mlops/reporting/build_catalog.py` (`build_reporting_catalog` result preservation), and `mlops/reporting/viewer.py` (`renderEvalMetrics`, `renderDecisionInfluence`).
  - Test: `assault_bench/tests/test_benchmark_smoke.py::test_benchmark_returns_results`, `mlops/tests/test_reporting_catalog.py::test_reporting_catalog_preserves_unit_prefilter_fields_in_eval_decision_steps_top`, `mlops/tests/test_reporting_viewer_replay_filter.py` (`test_model_html_includes_unit_prefilter_channels_with_producer_sources`, `test_model_html_eval_metrics_renders_unit_prefilter_step_columns`, `test_model_html_decision_influence_renders_unit_prefilter_info_line`).
  - Rule: objective learning should support explicit multi-VP auxiliary representation in configurable low-risk mode.
  - Code: `agents/efficientzero_v2/core/network_base.py`, `agents/efficientzero_v2/train/trainer.py`, `agents/efficientzero_v2/train/train_engine.py`, `agents/efficientzero_v2/core/interop.py`.
  - Test: `agents/efficientzero_v2/tests/test_train_engine_contracts.py::test_trainer_aux_objective_wiring_smoke_contract`.
- Rule: attack decision quality must be auditable with explicit calibration statistics, not only raw damage totals.
  - Code: `assault_bench/runner.py` (`_build_eval_decision_summary` -> `attack_effectiveness`) and `mlops/reporting/viewer.py` (`renderUnifiedActions`, "Attack Effectiveness (calibration)" tables).
  - Test: `assault_bench/tests/test_benchmark_dashboard_damage_pipeline.py::test_eval_decision_summary_builds_attack_effectiveness_calibration_metrics`.
- Rule: MCTS chance handling must remain opt-in and default-safe while exposing explicit telemetry.
  - Code: `agents/efficientzero_v2/core/mcts.py`, `agents/muzero/core/mcts.py`, `agents/efficientzero_v2/train/train_engine.py`, `agents/muzero/train/train_muzero.py`.
  - Test: `agents/efficientzero_v2/tests/test_mcts_q_normalization.py::test_mcts_sampled_expectation_chance_mode_reports_effective_k`, `agents/muzero/tests/test_mcts_contract.py::test_mcts_sampled_expectation_chance_mode_tracks_k`.
  - Rule: CAPTURE should prefer real objective progress over endless staging when progress exists.
  - Code: `assault_sim/decision/option_executor.py` (`_best_capture_staging_move`, `_capture_priority_action`, `_tag_action`).
  - Telemetry path: `assault_sim/training_env.py` -> `assault_sim/evaluation/evaluator.py` -> `assault_sim/evaluation/results_analyzer.py` and `assault_sim/evaluation/record_sb3_trace.py`.
  - Test: Pending dedicated regression test for `capture_suspected_progress_miss_rate`.
  - Rule: `ATTRIT`/`DENY` should not collapse into repeated `ADVANCE` when legal shots exist.
  - Code: `assault_sim/decision/option_executor.py` (`execute`, anti-collapse remap block) and `assault_sim/rewards/progressive_reward.py` (L3/L2 coherence shaping).
  - Test: Pending validation in SB3 smoke eval (`strategy -> option`, attack share, damage ratio).
  - Rule: with objective-rule scenarios, policy should feel continuous pressure to satisfy campaign VP capture target before terminal check.
  - Code: `assault_sim/rewards/progressive_reward.py` (tracked-side VP shortfall shaping in-step + terminal) and `assault_sim/config/reward_config.py`/`assault_sim/config/reward_config.json` (`objective_control_target_ratio`, `objective_shortfall_step_penalty`, `objective_shortfall_terminal_penalty`).
  - Test: Pending validation in SB3 smoke eval (`first_vp_entry_turn`, `vp_entry_conversion_rate`, `captured_final_counts`, `loss_rate`).
 - Rule: RL policy output must execute as a legal catalog action (or deterministic catalog fallback), never as non-displacement pseudo-move.
 - Code: `assault_sim/envs/gym_assault_env.py` (`_GymActionController._finalize_rl_action`, `_catalog_priority_action`) and `assault_sim/evaluation/eval_sb3.py` (`SB3EvalController._finalize_rl_action`, `_catalog_priority_action`).
 - Test: Pending validation in train/eval smoke (`rl_training_finalized_reason` / `rl_eval_finalized_reason` distributions, reduced `not_in_catalog` and `non_displacement` incidence).
 - Rule: strategic intent should persist across activations through explicit plan state, not ad-hoc runtime rewrites.
 - Code: `assault_sim/decision/mission_planner.py` (`MissionPlanner`, `PlannerContext`) + integrations in `assault_backend/main.py`, `assault_backend/services/sb3_ai_service.py`, `assault_sim/envs/gym_assault_env.py`, `assault_sim/evaluation/eval_sb3.py`, and `assault_sim/decision/option_executor.py`.
 - Test: Pending validation in smoke + multi-seed eval (`plan_commit_rate`, `focus_switch_rate`, `plan_stage_counts`, `action_finalize_reason_counts`).
- Rule: comparative SB3 win gates must use scenario objective outcome labels as canonical truth, not engine-side `winner`, in objective-resolved scenarios.
- Code: `assault_sim/evaluation/results_analyzer.py` (`summary`) and `assault_sim/evaluation/eval_sb3.py` comparative printing; combined runner parity in `scripts/run_eval_parallel_configs.ps1`.
- Test: Pending validation by replaying `battaglia_cittadina_2_1 IT` eval and checking `true_win_rate_objective == (tracked_result_counts.Vittoria* / episodes)`.
- Rule: side-level runtime cost asymmetry must be observable before comparing model quality/performance between sides.
- Code: `assault_sim/evaluation/evaluator.py` (catalog count/timing capture), `assault_sim/evaluation/results_analyzer.py` (aggregation/printing), `scripts/run_eval_parallel_configs.ps1` (comparative table).
- Test: Pending validation by multi-side eval run with non-empty per-side metrics.
- Rule: when objective opportunity exists, no-progress actions should be penalized more strongly than progress/conversion actions.
- Code: `agents/muzero/core/selfplay.py` (`shaped_training_reward` objective components) and active knobs in `agents/muzero/configs/muzero_config.yaml` + `agents/efficientzero_v2/configs/efficientzero_v2_config*.yaml`.
- Test: `agents/muzero/tests/test_reward_targets.py` (`test_shaped_reward_opportunity_no_progress_penalty_is_effective`, `test_shaped_reward_progress_and_conversion_outweigh_no_progress_path`).
- Rule: policy must learn to reduce invalid/fallback action-finalization events without adding new backend hard-force behavior.
- Code: `assault_sim/rewards/progressive_reward.py` (`action_finalized_reason` shaping + `SETUP` backstep wait penalty), `assault_sim/config/reward_config.py/json` (new v22 reward knobs), `assault_sim/evaluation/evaluator.py` and `assault_sim/evaluation/results_analyzer.py` (R2.1 KPI counters/rates).
- Test: Pending validation in train+eval (`invalid_action_rate`, `fallback_rate`, `wait_recovery_sb3_backstep_rate` down vs baseline; no material `loss_rate` regression).
- Rule: when CAPTURE has a legal progress move toward uncaptured VP, policy should prefer conversion pressure over opportunistic CAPTURE->ATTACK fallback.
- Code: `assault_sim/decision/option_executor_capture.py` (`_capture_priority_action`) and `assault_sim/rewards/progressive_reward.py` (CAPTURE fallback penalty scaling with progress-available context).
- Test: Pending validation in SB3 smoke eval (`capture_attempt_success_rate`, `vp_entry_conversion_rate`, `fallback_to_attack_rate_in_capture`, `capture_fallback_reason_counts`).
- Rule: planner diagnostics must reflect semantic CAPTURE continuity (`SETUP_CAPTURE` should align to CAPTURE intent) and keep role tags informative for P4 analysis.
- Code: `assault_sim/decision/option_executor/state.py` (`_plan_intent_alignment_label`) and `assault_sim/decision/option_executor.py` (`_plan_unit_role`, `_tag_action` intent-alignment computation).
- Test: `assault_sim/tests/test_option_executor_plan_tags.py::test_option_executor_setup_capture_intent_aligns_with_capture_l3`.
- Rule: planner intent must influence tactical choice even when stage is `SETUP`, otherwise CAPTURE plans can drift into passive local actions.
- Code: `assault_sim/decision/option_executor.py` (`execute` planner-managed pre-guardrail branch using `planner_intent`).
- Test: Pending validation in smoke+multi-seed (`capture_intent_persistence`, `vp_entry_conversion_rate`, `loss_rate`).
- Rule: plan role emitted to telemetry must be a valid operational role (`ASSAULT|SUPPORT_FIRE|SCREEN|HOLD_VP|RESERVE`) for normal runtime paths.
- Code: `assault_sim/decision/role_mapper.py` (`resolve_role_with_reason`, `assign_role`), `assault_sim/decision/option_executor.py` (`_plan_unit_role`, `_tag_action`), and `assault_sim/training_env.py` (role inference fallback when action tags are absent).
- Test: `assault_sim/tests/test_role_mapper_contract.py` and `assault_sim/tests/test_option_executor_plan_tags.py`.
- command card play.

## 4. Activation Eligibility

A unit may be ineligible if:

- suppressed or fallback state forbids action,
- already activated in current activation cycle,
- action-specific legality fails,
- terrain/LOS/arc constraints block execution.

Turn rollover recovery contract (runtime):

- Suppression and fallback markers are cleared at each turn start, including rollover reached from activation exhaustion (`RuntimeGameState.next_activation()` -> `start_turn()`).
- Validation state: **Pending Validation** (covered by unit regression test, pending full replay validation).

## 5. Validation Checklist

- [ ] Phase order is immutable and auditable.
- [ ] Legal-action generation is phase-aware.
- [ ] State updates are committed immediately after action resolution.
- [ ] Victory check timing matches rule semantics.
- [ ] Reinforcements are handled only in reinforcement timing.

## 6. VOEC Simulator Contract (Architecture-Neutral)

Validation state: **Pending Validation**.

- Rule: external AI architectures must consume the same episode API without using legacy training controllers.
- Code: `voec_sim/core/simulator.py` (`VOECSimulator.new_episode`, `legal_actions`, `step`, `is_terminal`).
- Test: `voec_sim/tests/test_sim_determinism.py`, `voec_sim/tests/test_legal_actions_contract.py`, `voec_sim/tests/test_terminal_conditions_v1.py`.

- Rule: VOEC v1 must reuse existing scenario/unit assets rather than synthetic redefinition.
- Code: `voec_sim/assets_bridge/importers.py`.
- Test: `voec_sim/tests/test_asset_parity_units.py`, `voec_sim/tests/test_asset_parity_scenarios.py`.
