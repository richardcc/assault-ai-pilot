# Rules Coverage Roadmap (Traceability)

This roadmap tracks game-rule implementation coverage against the canonical
rulebook PDF (`docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf`) and links each
rule domain to code, tests, and validation gates.

Validation state: **Active**.

## Scope Clarification

This file started as a high-level roadmap and was **not yet a full per-subrule audit**
of every clause in the PDF. The sections below add a granular checklist so we can
trace all major unit types, action families, and chapter-level rules explicitly.

## Status Taxonomy

- `implemented`: coded and covered by tests, pending only periodic regression.
- `implemented-partial`: core coded, but notable edge cases or gaps remain.
- `documented-only`: documented in rules docs, not yet implemented.
- `unknown`: not yet audited.

## Canonical Tables Migration (Completed)

Validation state for rules tables data-source unification: **Completed (clean-cut)**.

- Canonical rules tables are now under `assault_sim/assets/rules_tables/`.
- Runtime loaders read canonical assets directly (no legacy fallback paths).
- Legacy map table files were removed from `assault_model/map/`.
- Combat hardcoded tables were externalized to canonical JSON assets.

### Canonical-active tables

- `assault_sim/assets/rules_tables/terrain/terrain_modifiers.v1.json`
- `assault_sim/assets/rules_tables/fortification/fortification_modifiers.v1.json`
- `assault_sim/assets/rules_tables/combat/dice_face_table.v1.json`
- `assault_sim/assets/rules_tables/combat/critical_table.v1.json`
- `assault_sim/assets/rules_tables/manifest/rules_tables_manifest.v1.json`

### Runtime loader anchors

- `assault_model/map/terrain_config.py`
- `assault_model/map/fortification_config.py`
- `assault_model/combat/battle_die.py`
- `assault_model/combat/critical_table.py`

### Validation scripts

- `scripts/ptest_quick.ps1`
- `scripts/ptest_rules_tables.ps1`
- `scripts/ptest_combat_tables.ps1`
- `scripts/ptest_full.ps1`

## Rule Domains (Coverage Matrix)

| Capability ID | Rule domain | Current status | Primary code area | Evidence/tests |
|---|---|---|---|---|
| `R-TURN-SEQUENCE` | Turn phases + activation loop | implemented | `assault_model/runtime/game_state_runtime.py`, `assault_sim/engine/match_runner.py` | existing runtime/eval suites |
| `R-MOVE-TERRAIN` | Movement, terrain costs, legal paths | implemented-partial | `assault_model/rules/movement_rules.py`, `assault_model/rules/movement_terrain_rules.py` | movement tests + pending edge cases |
| `R-ATTACK-RANGED-RESOLUTION` | Ranged fire, LOS, modifiers | implemented | `assault_model/combat/ranged_combat_resolver.py`, `assault_model/combat/line_of_sight.py` | combat + LOS tests |
| `R-ATTACK-MELEE-RESOLUTION` | Close combat rounds and outcomes | implemented | `assault_model/combat/close_combat_resolver.py` | close-combat tests |
| `R-STATUS-MORALE` | Suppression/fallback/recovery | implemented-partial | `assault_model/combat/morale.py`, `assault_model/units/unit_instance.py` | suppression tests; fallback pathing to enrich |
| `R-SUPPORT-INDIRECT-FIRE` | Support phase indirect fires/smoke | implemented-partial | `assault_model/actions/*`, support/combat flow | add scenario-level assertions |
| `R-ACTION-REACTION-FIRE` | Reaction fire framework | implemented-partial | `assault_model/combat/reaction_*`, runtime integration points | needs full E2E reaction tests |
| `R-OPTIONAL-TAOAS-INTEGRATION` | Tactical air / off-board artillery | documented-only | docs + scenario model | implementation pending |
| `R-VICTORY-CONDITIONS` | VP ownership and objective outcomes | implemented | `assault_model/core/vp_tracker.py` | objective-outcome eval tests |

## Unit Types Coverage Checklist

| Capability ID | Unit/rule family from PDF | Status | Code anchor | Validation status |
|---|---|---|---|---|
| `R-UNIT-INFANTRY-CORE` | Infantry baseline rules | implemented-partial | `assault_model/units/*`, movement/combat resolvers | chapter-by-chapter verification complete (infantry scope); vehicle/artillery parity deferred |
| `R-UNIT-ARTILLERY-MOVE` | Artillery-specific movement | implemented-partial | `assault_model/rules/movement_rules.py`, action catalog | edge cases pending |
| `R-UNIT-ARTILLERY-INDIRECT` | Artillery/indirect fire effects | implemented-partial | `assault_model/combat/ranged_combat_resolver.py` | support-phase parity pending |
| `R-UNIT-VEHICLE-CORE` | Vehicle movement/combat | implemented-partial | movement + ranged/close combat modules | terrain-damage/full exceptions pending |
| `R-UNIT-ARMORED-VS-UNARMORED` | Armored/unarmored distinctions | implemented-partial | unit_type attributes + combat modifiers | PDF cross-check pending |
| `R-UNIT-EXPERIENCE-LEVELS` | Experience-level effects | implemented-partial | unit stats + combat modifier flow | complete modifier matrix pending |
| `R-UNIT-TRANSPORT-CAPACITY` | Transport capacity/load/unload | implemented-partial | movement rules + embark paths | full unload/emergency paths pending |
| `R-UNIT-IMMOBILE-ARTILLERY` | Loading/unloading immobile artillery | documented-only | docs currently | implementation coverage pending |

## Action Families Coverage Checklist

| Capability ID | Action family from PDF | Status | Code anchor | Validation status |
|---|---|---|---|---|
| `R-ACTION-PASS` | Pass action | implemented | runtime/action status flow | regression pending |
| `R-ACTION-REACTION-FIRE` | Reaction fire + interruption order | implemented-partial | `assault_model/combat/reaction_*` | E2E runtime integration pending |
| `R-ACTION-COMMAND-CARD` | Play command card | documented-only | docs/optional rules | engine implementation pending |
| `R-ACTION-MOVE-NORMAL` | Normal movement | implemented | movement rules + catalog | stable |
| `R-ACTION-MOVE-FAST` | Fast movement | implemented-partial | movement/action catalog | full constraints audit pending |
| `R-ACTION-MOVE-AND-FIRE` | Move and fire | implemented | composite fire actions + resolver | stable |
| `R-ACTION-HIDE-AMBUSH` | Hide action and ambush | implemented-partial | action/rules flow | chapter parity pending |
| `R-ACTION-COVERING-FIRE` | Movement with covering fire | implemented-partial | action catalog/combat flow | explicit rules audit pending |
| `R-ACTION-RANGED-FIRE` | Ranged fire resolution | implemented | ranged resolver + LOS | stable |
| `R-ACTION-CLOSE-COMBAT` | Close combat resolution | implemented | close combat resolver | stable |
| `R-ACTION-SUPPORT-INDIRECT` | Support-phase indirect fire | implemented-partial | support/ranged pipelines | phase-order parity pending |
| `R-ACTION-SUPPORT-SMOKE` | Smoke usage | implemented-partial | support/rules/actions | scenario-level tests pending |
| `R-ACTION-TA-OAS` | TA/OAS actions | documented-only | docs only | implementation pending |

## Infantry Chapter-by-Chapter Verification (Completed Scope)

Scope completed here is infantry baseline behavior only. Vehicle/artillery-specific
exception matrices remain tracked separately.

- `9.x Movement (infantry path)`:
  - baseline movement + fast movement + move&fire behavior traced in movement/action modules.
  - special movement interactions (`hide/ambush`, objective capture, obstacle crossing) traced in action/rules flow.
- `10.x Ranged (infantry-relevant modifiers)`:
  - LOS hindered, suppressed attacker, terrain/fortification defense, spotting gate are covered in Annex C (`RF-001..RF-005`) with parity tests.
- `11.x Close combat (infantry scope)`:
  - obstacle crossing, outflank reroll, activated penalty, suppression, ambush are covered in Annex C (`CC-001..CC-005`) with parity tests.
- `10.x/11.x critical routing (infantry-involved)`:
  - infantry/artillery and vehicle critical mappings are validated (`CR-001`, `CR-002`);
  - building/fortification critical route remains explicit mismatch (`CR-003`) pending model extension.

Primary evidence:
- `docs/game_rules/annexes/C_DICE_MODIFIER_VALIDATION_TABLES.md`
- `assault_model/tests/test_modifier_parity_ranged_close.py`

Annex C transcription status update:
- Chapter references and transcription notes for `RF-001..RF-005`, `CC-001..CC-005`, and `CR-001..CR-003` were completed in Annex C.
- Remaining uncertainty is now limited to explicitly tagged OCR-limited snippets (not silent TODO/pending markers).

## Chapter-Level PDF Audit Backlog

This is the explicit “what is still to be audited from the PDF” list:

- `9.x Movement`: complete clause-by-clause audit for hills/buildings/roads/fortifications/obstacles/minefields.
- `9.8/9.9/9.10/9.11`: infantry/artillery/vehicle/transport subrules parity audit.
- `10.x Ranged Fire`: verify full modifier table coverage (status, terrain, experience, special abilities).
- `11.x Close Combat`: verify dug-in/area attack/emergency disembark/infantry-vs-vehicle special cases.
- `12.x TA/OAS`: implement and validate optional module flow end-to-end.
- `13.x Status markers`: ensure marker taxonomy/effects are fully reflected in engine states and tests.

## PDF Subsection Trace Table (Initial Strict Pass)

Format: one row per explicit PDF subsection to avoid ambiguity in coverage.

| PDF ref | Rule topic | Status | Code evidence | Test evidence | Pending |
|---|---|---|---|---|---|
| `6.1` | Initiative phase | implemented-partial | `assault_model/runtime/game_state_runtime.py` | runtime/eval smoke | explicit phase unit tests |
| `6.2` | Planning phase | implemented-partial | runtime + controllers in `assault_sim` | integration smoke | command-card parity |
| `6.3` | Support phase overview | implemented-partial | support flow + actions/combat modules | partial | strict support-phase ordering tests |
| `6.4` | Action phase overview | implemented | runtime/action execution loop | existing smoke | dedicated sequence assertions |
| `6.5` | Organization phase | implemented-partial | runtime cleanup/recovery hooks | partial | explicit org-phase test |
| `6.6` | Victory check phase | implemented | `assault_model/core/vp_tracker.py` + runtime | eval reports | scenario edge-case tests |
| `6.7` | Placing reinforcements | implemented-partial | scenario/runtime placement paths | partial | reinforcement timing tests |
| `8.1` | Passing | implemented | `WaitAction` + activation advance | covered in runtime behavior | isolated pass-contract test |
| `8.2` | Reaction fire | implemented-partial | `assault_model/combat/reaction_*` | limited | full E2E trigger/interrupt tests |
| `8.3` | Play command card | documented-only | docs only | none | engine implementation |
| `9.1` | Normal movement | implemented | movement rules + action catalog | movement tests | regression expansion |
| `9.2` | Fast movement | implemented-partial | movement/action generation | partial | penalties/limits parity audit |
| `9.3` | Moving and firing | implemented | composite actions + resolution | existing tests | edge-case matrix |
| `9.4` | Terrain movement costs | implemented-partial | movement + terrain config | partial | full table parity |
| `9.6.1` | Hills | implemented-partial | terrain + LOS interaction | partial | chapter-specific assertions |
| `9.6.2` | Buildings | implemented-partial | terrain/defense/LOS handling | partial | special-case audit |
| `9.6.3` | Roads and trails | implemented-partial | terrain movement paths | limited | exact cost-rule parity |
| `9.6.4` | Fortifications | implemented-partial | `assault_model/rules/fortification_rules.py` | partial | exhaustive rule cases |
| `9.6.5` | Obstacles | implemented-partial | terrain/marker interactions | limited | blocking/interaction tests |
| `9.6.6` | Minefields | implemented-partial | movement/terrain marker flow | limited | trigger/damage parity tests |
| `9.7` | Capturing objective hexes | implemented | game state ownership + VP tracker | eval metrics | corner-case ownership tests |
| `9.8` | Infantry specific movement | implemented-partial | infantry movement + unit traits | partial | all subclauses (`9.8.1`,`9.8.2`) |
| `9.9` | Artillery specific movement | implemented-partial | movement rules + action catalog | partial | artillery exceptions tests |
| `9.10` | Vehicle specific movement | implemented-partial | vehicle movement + terrain/combat interaction | partial | `9.10.1-9.10.3` completeness |
| `9.11` | Transporting units | implemented-partial | embark/load/unload paths | limited | capacity + emergency paths |
| `9.12` | Hide action and ambush | implemented-partial | hide/ambush logic in action/rules flow | limited | reveal/ambush sequencing |
| `9.13` | Movement with covering fire | implemented-partial | action/combat coupling | limited | explicit covering-fire tests |
| `10.1` | Range factor | implemented | ranged resolver range checks | combat tests | per-unit range table parity |
| `10.2-10.4` | LOS/checking/elevation | implemented | `line_of_sight.py` | LOS tests | expanded scenario fixtures |
| `10.5` | Direct fire spotting | implemented-partial | spotting hooks in ranged flow | partial | full spotting rule matrix |
| `10.6` | Arc of fire | implemented-partial | attack legality/action generation | partial | strict arc constraints tests |
| `10.7` | Resolving combat + criticals | implemented | ranged resolver critical paths | combat tests | buildings/vehicle edge suite |
| `10.8` | Attack dice modifiers | implemented-partial | unit attributes/status/experience in resolver | partial | modifier table parity |
| `10.9` | Defense dice modifiers | implemented-partial | terrain/LOS/status modifiers | partial | modifier table parity |
| `10.10` | Ranged fire vs transporting vehicles | implemented-partial | combat + transport interactions | limited | emergency disembark parity |
| `11.1` | Resolving close combat | implemented | close combat resolver | close-combat tests | round-by-round matrix |
| `11.2` | Dug-in defender | implemented-partial | defense modifiers | limited | dedicated dug-in tests |
| `11.3` | Area of attack | implemented-partial | combat resolution pathways | limited | area-attack parity |
| `11.4` | Emergency disembark | implemented-partial | transport/combat interplay | limited | dedicated scenario tests |
| `11.5` | Infantry special attack vs vehicles | implemented-partial | close/ranged special handling | limited | explicit anti-vehicle cases |
| `12.2` | Integrating TA/OAS expansion | documented-only | docs only | none | module implementation |
| `12.3` | Tactical Air Support | documented-only | docs only | none | full TAS flow |
| `12.4` | Off-board artillery support | documented-only | docs only | none | full OAS flow |
| `12.5` | Blast vs buildings/fortifications | documented-only | docs only | none | blast/damage integration |
| `13.1` | General status markers | implemented-partial | unit/runtime states | partial | complete marker parity |
| `13.2` | Action status markers | implemented-partial | action gating/status usage | partial | full marker parity |
| `13.3` | Morale status markers | implemented-partial | suppression/fallback in units/combat | partial | full morale-marker parity |

### Automated strict-pass battery (current)

- Test file: `assault_model/tests/test_pdf_subsection_trace_strict_pass.py`
- Run script: `scripts/ptest_pdf_trace_strict.ps1`
- Covered subsection contracts in current battery:
  - `6.4` / `8.1` (WAIT/pass activation progression)
  - `9.4` (terrain movement cost baseline)
  - `9.6.4` (fortification defense bonus presence)
  - `9.7` (objective hex control switch)
  - `10.2-10.4` (LOS blocked/hindered)
  - `10.5` (spotting fail path)
  - `13.3` (suppression -> fallback transition)

## Gap-Closing Roadmap

## Phase R1 - Movement and Morale hardening

- Expand terrain-entry legality beyond permissive defaults.
- Replace simplified morale fallback retreat with path-aware retreat selection.
- Add deterministic tests for edge terrain + fallback behavior.

Exit gate:

- No regressions in movement legal-action set under fixed seeds.
- Fallback behavior verified in at least 3 focused scenario tests.

## Phase R2 - Reaction Fire completion

- Consolidate reaction-fire path into the main runtime loop.
- Align legacy reaction modules with current action/runtime APIs.
- Add end-to-end tests for trigger, resolution, and interruption ordering.

Exit gate:

- Reaction fire triggers and resolves deterministically in smoke scenarios.
- No increase in invalid-action finalization rates during eval.

## Phase R3 - Support systems (TA/OAS)

- Implement optional TA/OAS request-target-resolve pipeline behind feature flags.
- Add scenario-level toggles for optional modules.
- Add report telemetry for TA/OAS usage and effectiveness.

Exit gate:

- Feature-flag OFF path remains behavior-identical.
- Feature-flag ON path passes scenario-specific rules tests.

## Phase R4 - Rules-complete production trace

- For each capability ID, require:
  - code reference,
  - at least one automated test,
  - one validation note in rule docs.
- Sync status with `docs/GAP_ANALYSIS.md` and `docs/game_rules/annexes/B_PDF_TRACEABILITY.md`.

Exit gate:

- All priority capability IDs are at least `implemented-partial`.
- Production candidate requires all core combat/movement/turn/victory IDs at `implemented`.

## Working Agreement

- One gameplay rules palanca per cycle where possible.
- Any new rule must include traceability update (this file + tests reference).
- If a change regresses tactical gates in 2/3 seeds, rollback only the last palanca.
