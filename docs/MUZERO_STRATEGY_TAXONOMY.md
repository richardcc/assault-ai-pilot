# MuZero Strategy Taxonomy

Validation state: **Pending Validation**.

## Purpose

Define the canonical mapping from low-level `action_kind` events to
high-level strategy labels used in MuZero dashboards and reports.

This taxonomy is operational and deterministic: same input action kind must
always map to the same strategy bucket.

## Canonical mapping

- `MOVE` -> `ADVANCE`
- `WAIT` -> `HOLD`
- `CAPTURE`, `FIRE_CAPTURE` -> `CAPTURE`
- `ASSAULT_MELEE`, `MELEE`, any `action_kind` containing `ASSAULT` -> `ASSAULT`
- `FIRE_MOVE`, `RANGED_DIRECT`, `RANGED_INDIRECT`, `OPPORTUNITY_FIRE` -> `ATTACK`
- Any unmapped or unknown action kind -> `OTHER`

## Rationale

- `ADVANCE`: movement/positioning actions intended to change board geometry.
- `HOLD`: explicit no-commit action preserving current posture.
- `CAPTURE`: objective conversion actions tied to VP progress.
- `ASSAULT`: close-combat commitment with higher tactical risk.
- `ATTACK`: fire-oriented engagement not classified as objective capture.
- `OTHER`: safety bucket for future action kinds pending explicit classification.

## Contract requirements

- Producers must emit `action_kind` in transition telemetry.
- Strategy summaries must include:
  - global counts/rates by strategy
  - side-level counts/rates by strategy
- Unknown action kinds MUST be counted in `OTHER`, never dropped.

## Governance

- Any change to this mapping requires:
  1. Update of this document.
  2. Update of MuZero runner implementation that emits `strategy_summary`.
  3. Update of related report tests/snapshots.
