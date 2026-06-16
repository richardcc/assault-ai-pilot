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
- CAPTURE distance-progress diagnostics (observability-only, no rules change):
  - `capture_progress_available`: at least one legal move reduced distance to an uncaptured VP.
  - `capture_suspected_progress_miss`: progress existed but selected move reason was not `objective_progress_move`.
  - candidate counters: `capture_progress_candidates`, `capture_equal_candidates`, `capture_increase_candidates`, `capture_reversal_filtered`.
  - intent: detect possible distance/progress selection anomalies before changing tactical policy.
- CAPTURE movement priority rule (behavioral guardrail):
  - when at least one legal CAPTURE move reduces distance to an uncaptured VP, selector must choose a `objective_progress_move`.
  - lateral `objective_staging_move` is allowed only when no progress move exists.
  - for CAPTURE-forced `ADVANCE`, movement selection uses strict objective distance priority and prefers non-worsening moves when available.
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
  - Rule: CAPTURE should prefer real objective progress over endless staging when progress exists.
  - Code: `assault_sim/decision/option_executor.py` (`_best_capture_staging_move`, `_capture_priority_action`, `_tag_action`).
  - Telemetry path: `assault_sim/training_env.py` -> `assault_sim/evaluation/evaluator.py` -> `assault_sim/evaluation/results_analyzer.py` and `assault_sim/evaluation/record_sb3_trace.py`.
  - Test: Pending dedicated regression test for `capture_suspected_progress_miss_rate`.
- command card play.

## 4. Activation Eligibility

A unit may be ineligible if:

- suppressed or fallback state forbids action,
- already activated in current activation cycle,
- action-specific legality fails,
- terrain/LOS/arc constraints block execution.

## 5. Validation Checklist

- [ ] Phase order is immutable and auditable.
- [ ] Legal-action generation is phase-aware.
- [ ] State updates are committed immediately after action resolution.
- [ ] Victory check timing matches rule semantics.
- [ ] Reinforcements are handled only in reinforcement timing.
