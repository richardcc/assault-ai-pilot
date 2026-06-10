# Annex C - Dice Modifier Validation Tables

Purpose: provide one auditable place for modifier parity checks against vendor PDFs.

## Validation Status

Status: **Pending Validation**.

Rows in this annex are not final until PDF references, exact values, code links,
and test links are fully completed and reviewed.

## 1. How to Use This Annex

For each rule-modifier entry:

1. copy the exact rule value from PDF/GameAid,
2. map to one code function/symbol,
3. map to one automated test,
4. mark status (`pending`, `validated`, `mismatch`).

## 2. Ranged Fire Modifier Ledger

| ID | Rule family | Trigger | Expected dice delta | PDF reference | Code reference | Test reference | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RF-001 | LOS hindered | LOS=`HINDERED`, direct fire | TODO | TODO | `assault_backend/services/targeting_service.py` | TODO | pending |
| RF-002 | Attacker suppressed | attacker.suppressed=true | TODO | TODO | `assault_backend/services/targeting_service.py` | TODO | pending |
| RF-003 | Terrain defense bonus | terrain grants defense | TODO | TODO | `assault_backend/services/targeting_service.py` | TODO | pending |
| RF-004 | Fortification bonus | fortification present | TODO | TODO | `assault_backend/services/targeting_service.py` | TODO | pending |
| RF-005 | Spotting failure path | spotting fail | TODO | TODO | `assault_model/combat/spotting.py` + resolver | TODO | pending |

## 3. Close Combat Modifier Ledger

| ID | Rule family | Trigger | Expected dice delta / reroll | PDF reference | Code reference | Test reference | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CC-001 | Obstacle crossing | close combat entered via obstacle | TODO | TODO | `assault_model/combat/close_combat_resolver.py` | TODO | pending |
| CC-002 | Outflank reroll | outflank valid | TODO | TODO | `assault_model/combat/close_combat_resolver.py` | TODO | pending |
| CC-003 | Activated status | activated penalty condition | TODO | TODO | `assault_model/combat/close_combat_resolver.py` | TODO | pending |
| CC-004 | Suppression | suppressed at combat | TODO | TODO | `assault_model/combat/morale.py` | TODO | pending |
| CC-005 | Ambush | ambush state active | TODO | TODO | `assault_model/combat/close_combat_resolver.py` | TODO | pending |

## 4. Critical Outcome Ledger

| ID | Target category | Trigger | Expected outcome table | PDF reference | Code reference | Test reference | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CR-001 | Infantry/Artillery | critical hit | TODO | TODO | `assault_model/combat/critical_effect.py` | TODO | pending |
| CR-002 | Vehicle | critical hit | TODO | TODO | `assault_model/combat/critical_effect.py` | TODO | pending |
| CR-003 | Building/Fortification | critical/blast critical | TODO | TODO | `assault_model/combat/critical_effect.py` | TODO | pending |

## 5. Validation Rules

- No `validated` row may contain `TODO`.
- Any mismatch must include issue link and temporary waiver rationale.
- High-impact rows (`RF-001`, `RF-002`, `RF-003`, `CC-001`, `CR-002`) must be validated before release candidate training runs.
