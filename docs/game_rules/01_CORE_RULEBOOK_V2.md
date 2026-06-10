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

## 7. Compliance Checklist (Core)

- [ ] Phase machine strictly follows Rulebook chapter 6.
- [ ] Status markers alter action legality and dice pools as defined.
- [ ] Terrain/elevation effects are applied before final combat resolution.
- [ ] Critical outcomes are target-type specific (inf/art vs vehicles vs buildings).
- [ ] Campaign overrides can supersede base behavior only where explicitly stated.
