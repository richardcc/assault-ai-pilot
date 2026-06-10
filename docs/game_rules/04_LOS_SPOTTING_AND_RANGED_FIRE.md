# 04 - LOS, Spotting, and Ranged Fire (Validation-Level Spec)

Sources:

- `2024_09_18_Rulebook_rev6_web.pdf` (chapter 10)
- `2024_10_LOS_Examples_v1.pdf`
- `PN007_GameAid_Back_rev3_web.pdf`
- `TEC_Clarification.pdf`

Implementation references:

- `assault_model/combat/line_of_sight.py`
- `assault_model/combat/spotting.py`
- `assault_model/combat/spotting_runtime.py`
- `assault_model/combat/ranged_combat_resolver.py`
- `assault_backend/services/targeting_service.py`

## Validation Status

Status: **Pending Validation**.

This chapter contains validation scaffolding and mapping tables that require
final confirmation against vendor PDF values before closure.

---

## 1. Deterministic Resolution Contract

Ranged combat must run in this strict order:

1. validate attacker/target legality,
2. resolve LOS state (`CLEAR`, `HINDERED`, `BLOCKED`),
3. resolve spotting (auto/roll/fail),
4. build attack base dice,
5. apply attacker-side modifiers,
6. build defense base dice,
7. apply defender-side modifiers,
8. roll and compare dice,
9. resolve damage/suppression/critical chains by target type,
10. emit telemetry with all applied modifiers.

No modifier may be applied before its gate condition is known.

## 2. LOS and Spotting Gates

### 2.1 LOS output domain

LOS output is closed and mandatory:

- `CLEAR`
- `HINDERED`
- `BLOCKED`

### 2.2 Gate behavior

- if LOS is `BLOCKED`, direct ranged attack is illegal.
- if LOS requires spotting and spotting fails, branch to blind-fire path.
- indirect fire uses dedicated LOS/spotting constraints and does not reuse direct-fire assumptions.

## 3. Ranged Dice Model

## 3.1 Attack Dice Structure

`attack_final = attack_base + attacker_positive_mods - attacker_negative_mods`

Where:

- `attack_base` comes from unit profile and range mode.
- negative mods include status penalties (for example suppression).
- additional mods may come from abilities/cards/support.

## 3.2 Defense Dice Structure

`defense_final = defense_base + terrain_bonus + fortification_bonus + los_bonus + status_bonus`

Where:

- `defense_base` comes from target profile and attack sector.
- LOS-based bonus depends on LOS state and fire mode.

## 4. Explicit Modifier Table (Current Implemented Behavior)

This table captures implemented behavior that must stay aligned with PDFs.

| Rule family | Condition | Effect | Implemented in |
| --- | --- | --- | --- |
| Attacker suppression | Attacker is suppressed | Remove weakest attack die | `assault_backend/services/targeting_service.py` |
| LOS hindered (direct fire) | LOS = `HINDERED` and fire is direct | Add one defense die (green) | `assault_backend/services/targeting_service.py` |
| Indirect fire LOS behavior | Fire mode is indirect | Do not apply LOS hindered defense die | `assault_backend/services/targeting_service.py` |
| Terrain defense bonus | Target hex terrain grants defense dice | Add terrain bonus dice | `assault_backend/services/targeting_service.py` |
| Terrain stripping trait | Attacker has remove-weakest or remove-strongest terrain trait | Remove one terrain defense die based on trait | `assault_backend/services/targeting_service.py` |
| Fortification bonus | Target has fortification and valid attack sector interaction | Add fortification defense dice | `assault_backend/services/targeting_service.py` |

## 5. Canonical PDF Table Transcription (Required)

Populate this section verbatim from PDF tables (do not paraphrase values).
Use one row per modifier entry.

| Modifier ID | PDF source page/section | Trigger | Dice delta | Applies to (attack/defense) | Exceptions | Code symbol/function | Test ID |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-LOS-001 | TODO | LOS hindered | TODO | Defense | Indirect fire | TODO | TODO |
| R-SUP-001 | TODO | Attacker suppressed | TODO | Attack | None | TODO | TODO |
| R-TRN-001 | TODO | Terrain type X | TODO | Defense | Unit-type exceptions | TODO | TODO |
| R-FORT-001 | TODO | Fortification type X | TODO | Defense | Sector exceptions | TODO | TODO |
| R-SPT-001 | TODO | Spotting failed | TODO | Attack/Defense | Auto spotting cases | TODO | TODO |

Status rule:

- `TODO` rows are considered unvalidated until filled and tested.

## 6. Detailed Combat Pseudocode

```python
def resolve_ranged_combat(ctx):
    ensure_legal_target(ctx)
    los = resolve_los(ctx.attacker, ctx.target, ctx.map)
    if ctx.is_direct and los == "BLOCKED":
        return illegal("blocked_los")

    spotting = resolve_spotting(ctx, los)
    attack = build_attack_base(ctx)
    attack = apply_attacker_modifiers(attack, ctx, spotting, los)

    defense = build_defense_base(ctx)
    defense = apply_terrain_bonus(defense, ctx)
    defense = apply_fortification_bonus(defense, ctx)
    defense = apply_los_bonus(defense, ctx, los)
    defense = apply_defender_status_modifiers(defense, ctx)

    outcome = roll_and_compare(attack, defense, ctx.rng)
    effects = route_outcome_by_target_type(outcome, ctx.target)
    apply_effects(ctx.state, effects)
    emit_combat_trace(ctx, los, spotting, attack, defense, outcome, effects)
    return effects
```

## 7. Validation Matrix (Rule -> Code -> Test)

| Validation item | Code location | Expected assertion |
| --- | --- | --- |
| LOS tri-state only | `assault_model/combat/line_of_sight.py` | output in `{CLEAR,HINDERED,BLOCKED}` |
| Hindered adds defense bonus (direct only) | `assault_backend/services/targeting_service.py` | one defense die added when hindered and direct |
| Suppressed attacker penalty | `assault_backend/services/targeting_service.py` | weakest attack die removed |
| Terrain bonus inclusion | `assault_backend/services/targeting_service.py` | terrain dice appended before final compare |
| Fortification bonus inclusion | `assault_backend/services/targeting_service.py` | fortification dice appended when valid |
| Spotting branch behavior | `assault_model/combat/spotting.py` + resolver | fail branch applies blind-fire path |

## 8. Minimum Acceptance Checklist

- [ ] All chapter-10 modifier rows transcribed from PDF into section 5.
- [ ] Every transcribed row references one concrete code function.
- [ ] Every transcribed row has at least one deterministic test.
- [ ] No unresolved `TODO` remains for high-impact modifiers.
