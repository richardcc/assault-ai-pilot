# 05 - Close Combat and Criticals (Validation-Level Spec)

Sources:

- `2024_09_18_Rulebook_rev6_web.pdf` (chapter 11, sections 10.7.5 and 10.7.6)
- `PN007_GameAid_Back_rev3_web.pdf`

Implementation references:

- `assault_model/combat/close_combat_resolver.py`
- `assault_model/combat/close_combat_context.py`
- `assault_model/combat/critical_table.py`
- `assault_model/combat/critical_effect.py`
- `assault_model/combat/morale.py`

## Validation Status

Status: **Pending Validation**.

Modifier rows and critical-routing entries remain open until reviewed against
the canonical PDF tables and approved.

---

## 1. Close-Combat Resolution Contract

Each engagement resolves in this strict sequence:

1. validate initiation legality,
2. create close-combat context (participants, terrain, states),
3. build attacker and defender base dice,
4. apply first-round-only modifiers,
5. apply persistent round modifiers,
6. roll and compare results,
7. route critical and morale effects by target category,
8. evaluate continuation/end condition,
9. emit trace with complete modifier stack.

## 2. Initiation Validation

Must verify:

- valid engagement geometry,
- legal target category for close combat,
- unit state eligibility (not excluded by chapter rules),
- crossing/obstacle context recorded for round-1 modifiers.

## 3. Dice and Modifier Model

## 3.1 Formula

`cc_attack_final = cc_attack_base + bonuses - penalties`

`cc_defense_final = cc_defense_base + bonuses - penalties`

## 3.2 Modifier stacking order

The engine must apply in this order:

1. first-round mandatory modifiers,
2. status-based modifiers,
3. terrain/fortification modifiers,
4. experience and support modifiers,
5. reroll rights.

Rerolls apply after initial roll per rulebook conditions.

## 4. First-Round-Only Modifier Table

| Modifier family | Trigger | Effect class | Implemented in |
| --- | --- | --- | --- |
| Obstacle crossing penalty | Attacker enters through obstacle context | Attacker penalty | `assault_model/combat/close_combat_resolver.py` |
| Outflank reroll | Outflank condition met | Reroll bonus | `assault_model/combat/close_combat_resolver.py` |
| Activated-state penalty | Unit already activated status condition | Dice/efficiency penalty | `assault_model/combat/close_combat_resolver.py` |
| Suppression penalty | Unit suppressed at engagement start | Combat penalty | `assault_model/combat/morale.py` + resolver |
| Ambush effect | Ambush state active | Contextual bonus/penalty | `assault_model/combat/close_combat_resolver.py` |

## 5. Critical Routing Table

| Target category | Critical branch | Typical outcomes to validate | Code reference |
| --- | --- | --- | --- |
| Infantry/Artillery | morale + casualty chain | suppression, fallback, elimination escalation | `assault_model/combat/critical_effect.py` |
| Vehicles | mobility/damage chain | immobilized, repeated critical escalation | `assault_model/combat/critical_effect.py` |
| Buildings/Fortifications | structure damage chain | collapse/degrade interactions with occupants | `assault_model/combat/critical_effect.py` + terrain/support integration |

## 6. Canonical Modifier and Outcome Tables (Must be filled verbatim)

Populate directly from PDF/GameAid values.

| Modifier ID | PDF section | Trigger | Dice delta / reroll rule | Round scope | Target scope | Code function | Test ID |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CC-R1-001 | TODO | Obstacle crossed | TODO | Round 1 | Attacker | TODO | TODO |
| CC-R1-002 | TODO | Outflank achieved | TODO | Round 1 | Attacker | TODO | TODO |
| CC-STS-001 | TODO | Suppressed unit | TODO | Any | Unit-side | TODO | TODO |
| CC-ACT-001 | TODO | Activated unit penalty | TODO | Round 1/Any | Unit-side | TODO | TODO |
| CC-CRT-001 | TODO | Vehicle critical | TODO | Any | Vehicle | TODO | TODO |

No row can remain `TODO` if marked as validated.

## 7. Close-Combat Pseudocode

```python
def resolve_close_combat(ctx):
    validate_close_combat_legality(ctx)
    a_pool = build_attacker_base_dice(ctx)
    d_pool = build_defender_base_dice(ctx)

    if ctx.round_index == 1:
        a_pool, d_pool = apply_first_round_modifiers(a_pool, d_pool, ctx)

    a_pool, d_pool = apply_status_and_terrain_modifiers(a_pool, d_pool, ctx)
    roll = roll_close_combat(a_pool, d_pool, ctx.rng)
    outcome = compare_close_combat_roll(roll)
    effects = route_criticals_and_morale(outcome, ctx.target_type)
    apply_effects(ctx.state, effects)
    decide_continuation_or_end(ctx, effects)
    emit_close_combat_trace(ctx, a_pool, d_pool, roll, outcome, effects)
```

## 8. Validation Matrix (Rule -> Code -> Test)

| Validation item | Code location | Expected assertion |
| --- | --- | --- |
| Round-1 modifier ordering | `assault_model/combat/close_combat_resolver.py` | no round-1 modifier applied in later rounds |
| Suppression interaction | `assault_model/combat/morale.py` + resolver | suppression penalty applied exactly once |
| Outflank reroll behavior | resolver | reroll only under valid outflank condition |
| Vehicle critical chain | `assault_model/combat/critical_effect.py` | immobilized/escalation path deterministic |
| End condition resolution | resolver | engagement terminates on rule-defined stop conditions |

## 9. Minimum Acceptance Checklist

- [ ] Chapter-11 close-combat modifier rows transcribed from PDF.
- [ ] Critical routing per target type has direct code mapping.
- [ ] Regression tests cover round-1 modifiers and vehicle critical chain.
- [ ] Trace payload includes applied modifier IDs and order.
