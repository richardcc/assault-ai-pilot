# 01 - CORE RULEBOOK V2 (Implementation Baseline)

Primary canonical source: `2024_09_18_Rulebook_rev6_web.pdf`.

This chapter defines the implementation baseline and non-negotiable rules
that all engine modules must satisfy.

## 1. Scope

Assault is a hex-and-counter tactical system with:

- deterministic turn sequencing,
- per-unit activation and action execution,
- terrain/elevation/LOS/spotting-dependent combat,
- objective and scenario/campaign victory checks,
- optional modules (Command Cards, TAS/OAS, FoW).

## 2. Source-of-Truth Rule

When implementing or reviewing any mechanic:

1. Vendor PDFs in `docs/pdfs/` are authoritative.
2. This markdown is an implementation spec derived from PDFs.
3. If conflict exists, PDF wins and markdown/code must be aligned.

## 3. Mandatory Data Domains

The runtime model must represent at least:

- **Map Layer**
  - hex coordinates,
  - terrain type,
  - elevation context,
  - optional fortification/obstacle overlays.
- **Unit Layer**
  - side/faction,
  - type/classification,
  - HP/strength state (normal vs half-strength),
  - morale/action markers (suppressed, fallback, hidden, ambush, etc.),
  - activation eligibility.
- **Combat Layer**
  - attack/defense dice pools,
  - area of impact semantics,
  - spotting/LOS state,
  - critical effect handling by target category.
- **Objective Layer**
  - objective hexes,
  - ownership/control state,
  - scenario-specific victory outcomes.
- **Turn/Phase Layer**
  - current phase,
  - active side,
  - activation progression,
  - turn counter and end conditions.

## 4. Determinism Requirements

For AI training and reproducibility:

- same input state + same action + same random seed => same transition/output.
- phase order cannot be bypassed by convenience shortcuts.
- rule precedence must be explicit (e.g., blocked LOS overrides fire intent).

## 5. Rule Families (by chapter)

- **Ch. 6**: sequence of play and phase transitions.
- **Ch. 7**: support-phase actions (indirect, smoke, artillery-facing, etc.).
- **Ch. 8**: special actions (reaction fire, command cards, pass).
- **Ch. 9**: movement and terrain costs/restrictions.
- **Ch. 10**: ranged fire, LOS, spotting, criticals.
- **Ch. 11**: close combat.
- **Ch. 12**: TAS/OAS optional support module.
- **Ch. 13**: status marker summary and effects.

## 6. Minimal Engine Invariants

Any compliant implementation must preserve:

1. phase order validity,
2. legal action filtering by status and context,
3. unit-type constraints (infantry/artillery/vehicle distinctions),
4. consistent LOS/spotting interaction,
5. objective control and victory checks at correct timing points.

### 6.1 Objective Ownership Mapping Invariant

Validation state: **Pending Validation**.

- Runtime side-to-ownership mapping must use only controlled values
  (`SIDE_A`, `SIDE_B`, ...), never `NONE`.
- `NONE` is reserved exclusively for neutral/uncontrolled or contested states.
- Rule-to-code mapping:
  - rule: side ownership cannot map to neutral sentinel
  - file/function: `assault_model/state/game_state.py` -> `GameState._build_side_ownership()`
  - test: `assault_model/tests/test_game_state_side_ownership.py`

### 6.2 Owned-VP Defense Priority (AI tactical policy)

Validation state: **Pending Validation**.

- Defensive helper logic for threatened owned VP exists in tactical utilities,
  but CAPTURE pre-gate priority is currently disabled after regression checks.
- Current runtime behavior does not force owned-VP defense before normal
  CAPTURE progression.
- Rule-to-code mapping:
  - rule: owned-VP defense helper available, pre-gate force disabled
  - file/function: `assault_sim/decision/option_executor_capture.py` -> `_best_defend_owned_vp_action()`
  - file/function: `assault_sim/decision/option_executor.py` -> `OptionExecutor.execute()` (CAPTURE pre-gate disabled for owned-VP force)
  - test: Pending dedicated tactical regression before re-enabling

### 6.3 Anti-Oscillation Retreat Guardrail (AI tactical policy)

Validation state: **Pending Validation**.

- To avoid repetitive advance/retreat ping-pong, immediate retreat reversals
  (`A -> B -> A`) are blocked when:
  - objectives remain pending,
  - no capture emergency is active,
  - no close enemy pressure is present.
- In those conditions, tactical flow prefers an ADVANCE action instead of retreat.
- Rule-to-code mapping:
  - rule: block low-threat immediate retreat reversals
  - file/function: `assault_sim/decision/option_executor.py` -> `OptionExecutor.execute()` (`RETREAT` branch)
  - file/function: `assault_sim/decision/option_executor.py` -> `_enemy_count_within()`
  - test: Pending dedicated tactical regression

### 6.4 CAPTURE Unit Selection Reliability Bias (AI policy-side)

Validation state: **Pending Validation**.

- Candidate approach documented for future tuning; currently disabled after
  regression checks.
- Rule-to-code mapping:
  - rule: reliability-bias candidate (disabled)
  - file/function: `assault_sim/envs/gym_assault_env.py` -> `_GymActionController._capture_unit_sort_key()` baseline rank-only path
  - file/function: `assault_sim/evaluation/eval_sb3.py` -> `SB3EvalController._capture_unit_sort_key()` baseline rank-only path
  - test: Re-enable only with dedicated tactical regression

### 6.5 Local Owned-VP Interception Unit Bias (AI policy-side)

Validation state: **Pending Validation**.

- During CAPTURE unit selection, if an owned VP is immediately threatened
  (enemy distance <=1), selection may temporarily prioritize the closest local
  unit (distance <=3) to that threatened VP.
- Scope is limited to unit choice for the current activation; no global
  strategy override or quota mutation.
- Rule-to-code mapping:
  - file/function: `assault_sim/envs/gym_assault_env.py` -> `_GymActionController._defense_intercept_unit()` and `select_best_unit()`
  - file/function: `assault_sim/evaluation/eval_sb3.py` -> `SB3EvalController._defense_intercept_unit()` and `select_best_unit()`
  - test: Pending tactical regression

### 6.6 Recently-Lost VP Retake Priority (AI policy-side)

Validation state: **Pending Validation**.

- Candidate approach documented for future tuning; currently disabled after
  regression checks.
- Rule-to-code mapping:
  - file/function: `assault_sim/envs/gym_assault_env.py` -> CAPTURE unit selection baseline path
  - file/function: `assault_sim/evaluation/eval_sb3.py` -> CAPTURE unit selection baseline path
  - test: Re-enable only with dedicated tactical regression

## 7. Compliance Checklist (Core)

- [ ] Phase machine strictly follows Rulebook chapter 6.
- [ ] Status markers alter action legality and dice pools as defined.
- [ ] Terrain/elevation effects are applied before final combat resolution.
- [ ] Critical outcomes are target-type specific (inf/art vs vehicles vs buildings).
- [ ] Campaign overrides can supersede base behavior only where explicitly stated.
