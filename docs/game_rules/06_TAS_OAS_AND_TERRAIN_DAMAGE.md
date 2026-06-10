# 06 - TAS, OAS, AND TERRAIN DAMAGE (Detailed Implementation Spec)

Sources:

- `2024_09_18_Rulebook_rev6_web.pdf` (chapter 12)
- `PN007_GameAid_Back_rev3_web.pdf`

## 1. TAS Sequence Contract

Execution stages:

1. request TAS,
2. resolve timing/availability,
3. identify target,
4. resolve AA defense,
5. TAS attack resolution:
   - TAS spotting,
   - TAS accuracy,
   - result application,
   - optional second run.

Each stage should emit traceable state/events.

## 2. OAS Sequence Contract

Execution stages:

1. request OAS in planning window,
2. target-hex spotting,
3. exploratory shells phase,
4. action-phase strike,
5. choose fire mode and impact area,
6. resolve damage/effects and terrain transformation.

## 3. OAS Fire Modes

- Smoke Screen
- Suppressive Fire
- Fire For Effect

Mode selection must map to distinct area/effect templates.

## 4. Building/Fortification Blast Logic

Blast resolution must support:

- collapse outcomes,
- partial degradation outcomes,
- unit-state consequences in affected hex,
- fortification downgrade/removal paths.

## 5. Crater Generation

When crater conditions are met:

- place crater marker,
- mutate terrain behavior according to chart,
- preserve traceability of original terrain category.

## 6. TAS Friendly Fire Branch

Low-accuracy branch may redirect unresolved attack potential into adjacent friendly units
under chapter-defined conditions.

This branch must be explicit (not implicit side effect).

## 7. Recommended Tests

- TAS AA outcomes and branch routing,
- OAS exploratory drift behavior,
- OAS mode-specific impact templates,
- building collapse state transitions,
- craterized terrain behavior changes.

## 8. Validation Checklist

- [ ] TAS/OAS stage order is deterministic.
- [ ] Mode-specific behavior is data-driven and testable.
- [ ] Blast/building outcomes match table semantics.
- [ ] Crater placement updates terrain behavior consistently.
- [ ] Friendly-fire path is auditable in telemetry.
