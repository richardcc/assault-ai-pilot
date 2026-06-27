# RAG KB - Rulebook Explicativo (Base de Conocimiento)

Purpose: provide a RAG-friendly, explainable knowledge base derived from the
canonical rulebook PDF (`docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf`), with
coverage across all chapter families.

Source-of-truth rule:

1. PDF text is canonical.
2. This file stores normalized knowledge chunks.
3. If there is conflict, prefer PDF and update this KB.

## Record Schema (per chunk)

```yaml
id: KB-RULE-<chapter>-<section>-<slug>
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "<chapter.section or page range>"
topic: "<short topic label>"
rule_type: "basic|unit-specific|optional|exception|example|reference"
unit_scope: ["infantry","artillery","vehicle","all"]
action_scope: ["setup","movement","ranged_fire","close_combat","support","special_actions","status","victory"]
prerequisites: []
prohibitions: []
steps: []
edge_cases: []
examples: []
related_ids: []
implementation_refs: []
tests_refs: []
status: "implemented|implemented-partial|documented-only|unknown"
last_review_utc: "YYYY-MM-DDTHH:MM:SSZ"
```

## Retrieval Intents

- How to resolve rule X step-by-step.
- Legal/illegal actions for context Y.
- Differences by unit type.
- Exceptions by terrain/status/support module.
- Code/test evidence for a specific rule.

## Rulebook Coverage Index (All Chapters)

- `1.0` Game Components -> `KB-RULE-1-*`
- `2.0` Quick Start -> `KB-RULE-2-*`
- `3.0` Introduction and Overview -> `KB-RULE-3-*`
- `4.0` Game Components in Detail -> `KB-RULE-4-*`
- `5.0` Game Preparation -> `KB-RULE-5-*`
- `6.0` Sequence of Play -> `KB-RULE-6-*`
- `7.0` Support Phase -> `KB-RULE-7-*`
- `8.0` Special Actions -> `KB-RULE-8-*`
- `9.0` Movement Actions -> `KB-RULE-9-*`
- `10.0` Ranged Fire -> `KB-RULE-10-*`
- `11.0` Close Combat -> `KB-RULE-11-*`
- `12.0` Tactical Air and Off-Board Artillery Support -> `KB-RULE-12-*`
- `13.0` Status Markers -> `KB-RULE-13-*`

## Knowledge Records

### Chapter 1 - Game Components

```yaml
id: KB-RULE-1-0-game-components-inventory
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "1.0"
topic: "Game components inventory"
rule_type: "reference"
unit_scope: ["all"]
action_scope: ["setup"]
prerequisites: []
steps:
  - "Verify required components before scenario setup."
edge_cases:
  - "Optional module components may be excluded unless enabled."
implementation_refs:
  - "assault_model/core/scenario_loader.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 2 - Quick Start

```yaml
id: KB-RULE-2-1-training-scenarios
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "2.1-2.2"
topic: "Training scenario scope"
rule_type: "reference"
unit_scope: ["all"]
action_scope: ["setup"]
steps:
  - "Start with infantry-focused scenarios."
  - "Add artillery/vehicle/optional rules incrementally."
implementation_refs:
  - "assault_sim/config/train_config.json"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 3 - Introduction and Overview

```yaml
id: KB-RULE-3-1-objective-victory-overview
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "3.1-3.2"
topic: "Objective and rule taxonomy"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["victory"]
steps:
  - "Evaluate objective outcomes by scenario rules."
  - "Classify rule as basic/unit-specific/optional."
implementation_refs:
  - "assault_model/core/vp_tracker.py"
  - "assault_model/runtime/game_state_runtime.py"
tests_refs: []
status: "implemented"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 4 - Components in Detail

```yaml
id: KB-RULE-4-2-unit-cards-and-attributes
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "4.2-4.9"
topic: "Unit cards, attributes, optional module assets"
rule_type: "reference"
unit_scope: ["all"]
action_scope: ["setup"]
steps:
  - "Read points, armor, experience, and ability metadata from unit definitions."
implementation_refs:
  - "assault_model/units/unit_type.py"
  - "assault_model/units/catalog_loader.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 5 - Game Preparation

```yaml
id: KB-RULE-5-0-game-preparation
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "5.0-5.9"
topic: "Scenario/faction/setup/placement/deck prep"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["setup"]
steps:
  - "Select scenario, factions, players, and map layout."
  - "Load formation/unit pools and apply placement constraints."
  - "Initialize runtime/decks/markers."
implementation_refs:
  - "assault_model/core/scenario_loader.py"
  - "assault_model/runtime/game_state_runtime.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 6 - Sequence of Play

```yaml
id: KB-RULE-6-0-sequence-of-play
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "6.1-6.7"
topic: "Initiative -> Planning -> Support -> Action -> Organization -> Victory"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["victory","special_actions"]
steps:
  - "Resolve phases in defined order."
  - "Apply reinforcement and victory checks at designated gates."
related_ids:
  - "KB-RULE-7-0-support-phase"
  - "KB-RULE-8-0-special-actions"
implementation_refs:
  - "assault_model/runtime/game_state_runtime.py"
  - "assault_sim/engine/match_runner.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 7 - Support Phase

```yaml
id: KB-RULE-7-0-support-phase
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "7.1-7.4"
topic: "Indirect fire, spotting, smoke, support abilities"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["support"]
steps:
  - "Validate spotting/targeting conditions."
  - "Resolve support effect (damage/smoke/adjustment)."
edge_cases:
  - "Vehicle-specific indirect interactions require dedicated parity tests."
implementation_refs:
  - "assault_model/combat/ranged_combat_resolver.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 8 - Special Actions

```yaml
id: KB-RULE-8-0-special-actions
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "8.1-8.4"
topic: "Pass, reaction fire, command-card timing"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["special_actions","ranged_fire"]
steps:
  - "Allow pass action with proper activation advancement."
  - "Allow reaction windows for inactive side where legal."
prohibitions:
  - "Out-of-window reaction/interrupt resolution."
implementation_refs:
  - "assault_model/actions/status.py"
  - "assault_model/combat/reaction_state.py"
  - "assault_model/combat/reaction_fire_resolution.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 9 - Movement Actions

```yaml
id: KB-RULE-9-0-movement-actions
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.1-9.13"
topic: "Movement modes, terrain, unit-specific movement, transport, hide/ambush"
rule_type: "unit-specific"
unit_scope: ["infantry","artillery","vehicle","all"]
action_scope: ["movement"]
steps:
  - "Generate legal movement options under movement budget and terrain constraints."
  - "Apply stacking, objective capture, transport, and special movement rules."
edge_cases:
  - "Minefields, obstacles, overrun, immobile artillery load/unload."
related_ids:
  - "KB-RULE-10-0-ranged-fire"
implementation_refs:
  - "assault_model/rules/movement_rules.py"
  - "assault_model/rules/movement_terrain_rules.py"
  - "assault_model/actions/action_catalog.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 10 - Ranged Fire

```yaml
id: KB-RULE-10-0-ranged-fire
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.1-10.10"
topic: "Range, LOS, spotting, arc, attack/defense modifiers, criticals"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["ranged_fire"]
steps:
  - "Validate range/LOS/spotting/arc."
  - "Build attack and defense dice pools."
  - "Resolve damage/critical effects and transport edge cases."
edge_cases:
  - "Critical tables by target class and transport emergency disembark."
implementation_refs:
  - "assault_model/combat/line_of_sight.py"
  - "assault_model/combat/ranged_combat_resolver.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 11 - Close Combat

```yaml
id: KB-RULE-11-0-close-combat
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "11.1-11.6"
topic: "Close combat initiation/resolution and special cases"
rule_type: "basic"
unit_scope: ["infantry","vehicle","artillery","all"]
action_scope: ["close_combat"]
steps:
  - "Initiate legal close combat."
  - "Resolve round exchanges and assign damage."
  - "Apply end conditions and special clauses."
edge_cases:
  - "Dug-in defenders, area attack, emergency disembark, infantry-vs-vehicle."
implementation_refs:
  - "assault_model/combat/close_combat_resolver.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 12 - Tactical Air and Off-Board Artillery

```yaml
id: KB-RULE-12-0-ta-oas
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "12.1-12.5"
topic: "Optional TA/OAS module integration and strike resolution"
rule_type: "optional"
unit_scope: ["all"]
action_scope: ["support"]
steps:
  - "Integrate optional deck/module assets."
  - "Request support, resolve timing, target, defense, and blast."
edge_cases:
  - "Building/fortification blast-value interactions."
implementation_refs: []
tests_refs: []
status: "documented-only"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 13 - Status Markers

```yaml
id: KB-RULE-13-0-status-markers
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "13.1-13.3"
topic: "General, action, morale status markers and effects"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["status"]
steps:
  - "Apply marker effects to action legality/modifiers."
  - "Apply morale/suppression/fallback transitions."
edge_cases:
  - "Stacking/order of marker effects."
implementation_refs:
  - "assault_model/units/unit_instance.py"
  - "assault_model/combat/morale.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

## Remaining Strict Ingestion Work

- Expand this chapter-level set into subsection-level entries (`9.6.4`, `10.9.6`, `11.4`, etc.).
- Add explicit `tests_refs` per chunk.
- Add explicit `implementation_refs` for optional modules once coded.

## Subsection-Level Records (Strict Pass v1)

These records provide stable, atomic anchors for retrieval by subrule in chapters
9-13. They are intentionally concise and can be expanded later with exact
`tests_refs` and deeper implementation mapping.

### Chapter 9 - Movement Actions (Subsections)

```yaml
id: KB-RULE-9-1-activation-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.1"
topic: "Activation and legal movement declaration"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Validate unit can activate and move this action window."]
implementation_refs: ["assault_model/actions/action_catalog.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-2-movement-allowance
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.2"
topic: "Movement allowance and spending"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Consume movement budget per hex/terrain/rule cost."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-3-terrain-cost-restrictions
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.3"
topic: "Terrain movement costs and entry restrictions"
rule_type: "unit-specific"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Apply terrain-dependent entry/cost constraints by unit type."]
implementation_refs: ["assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-4-stacking-control
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.4"
topic: "Stacking limits and control constraints while moving"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Reject moves violating stack/control occupancy limits."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-5-vp-capture-on-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.5"
topic: "Objective capture and control updates during movement"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["movement","victory"]
steps: ["Update VP control state when legal capture conditions are met."]
implementation_refs: ["assault_model/core/vp_tracker.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-transport-embark-disembark
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6"
topic: "Transport load/unload and passenger constraints"
rule_type: "unit-specific"
unit_scope: ["infantry","vehicle","all"]
action_scope: ["movement","special_actions"]
steps: ["Validate embark/disembark legality and transport capacity."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-4-emergency-disembark
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.4"
topic: "Emergency disembark edge resolution"
rule_type: "exception"
unit_scope: ["infantry","vehicle"]
action_scope: ["movement","close_combat","ranged_fire"]
steps: ["Resolve forced disembark destination, state, and penalties."]
implementation_refs: ["assault_model/combat/ranged_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-7-hide-ambush
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.7"
topic: "Hide, reveal, and ambush movement interactions"
rule_type: "unit-specific"
unit_scope: ["infantry","all"]
action_scope: ["movement","special_actions"]
steps: ["Apply concealment state transitions on legal triggers."]
implementation_refs: ["assault_model/actions/status.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-8-obstacles-mines
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.8"
topic: "Obstacle/minefield movement interactions"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Apply obstacle crossing/mine trigger restrictions and effects."]
implementation_refs: ["assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-9-overrun-special-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.9"
topic: "Overrun and special movement attacks"
rule_type: "unit-specific"
unit_scope: ["vehicle","all"]
action_scope: ["movement","close_combat"]
steps: ["Validate overrun path/target legality and resolve outcome."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "documented-only"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 10 - Ranged Fire (Subsections)

```yaml
id: KB-RULE-10-1-declare-ranged-attack
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.1"
topic: "Declare legal ranged attack"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["ranged_fire"]
steps: ["Validate attacker readiness, target class, and attack permission."]
implementation_refs: ["assault_model/combat/ranged_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-10-2-range-los-spotting
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.2"
topic: "Range, LOS, and spotting prerequisites"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["ranged_fire"]
steps: ["Enforce range bands, LOS blockers, and spotter requirements."]
implementation_refs: ["assault_model/combat/line_of_sight.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-10-3-fire-arc-facing
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.3"
topic: "Fire arc and facing constraints"
rule_type: "unit-specific"
unit_scope: ["vehicle","all"]
action_scope: ["ranged_fire"]
steps: ["Apply weapon arc/facing limits before attack resolution."]
implementation_refs: ["assault_model/combat/line_of_sight.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-10-4-attack-defense-pools
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.4"
topic: "Build attack and defense dice pools"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["ranged_fire"]
steps: ["Compute modifiers and assemble attack/defense values."]
implementation_refs: ["assault_model/combat/ranged_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-10-5-apply-damage-effects
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.5"
topic: "Damage assignment and status effect application"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["ranged_fire","status"]
steps: ["Apply hits, damage tracks, and resulting marker effects."]
implementation_refs: ["assault_model/combat/ranged_combat_resolver.py","assault_model/combat/morale.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-10-9-6-critical-hit-vehicles
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.9.6"
topic: "Vehicle critical-hit subtable handling"
rule_type: "exception"
unit_scope: ["vehicle"]
action_scope: ["ranged_fire","status"]
steps: ["Resolve vehicle critical outcome and persistent penalties."]
implementation_refs: ["assault_model/combat/ranged_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 11 - Close Combat (Subsections)

```yaml
id: KB-RULE-11-1-initiate-close-combat
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "11.1"
topic: "Close combat initiation constraints"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["close_combat"]
steps: ["Validate adjacency/eligibility and start close combat."]
implementation_refs: ["assault_model/combat/close_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-11-2-close-combat-round
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "11.2"
topic: "Close combat round resolution"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["close_combat"]
steps: ["Resolve opposing values and apply casualties/states."]
implementation_refs: ["assault_model/combat/close_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-11-4-special-close-combat-cases
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "11.4"
topic: "Special close combat cases by unit/terrain state"
rule_type: "exception"
unit_scope: ["infantry","vehicle","artillery","all"]
action_scope: ["close_combat"]
steps: ["Apply special modifiers/restrictions for defined exception states."]
implementation_refs: ["assault_model/combat/close_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 12 - Tactical Air / Off-Board Artillery (Subsections)

```yaml
id: KB-RULE-12-1-module-enable
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "12.1"
topic: "Enable optional TA/OAS module"
rule_type: "optional"
unit_scope: ["all"]
action_scope: ["support","setup"]
steps: ["Load optional assets/rules only when module is enabled."]
implementation_refs: []
tests_refs: []
status: "documented-only"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-12-2-call-for-support
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "12.2"
topic: "Support request timing and legality"
rule_type: "optional"
unit_scope: ["all"]
action_scope: ["support"]
steps: ["Validate request window, target legality, and availability."]
implementation_refs: []
tests_refs: []
status: "documented-only"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-12-3-strike-resolution
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "12.3"
topic: "TA/OAS strike resolution and blast effects"
rule_type: "optional"
unit_scope: ["all"]
action_scope: ["support","status"]
steps: ["Resolve strike, defense, blast radius, and status outcomes."]
implementation_refs: []
tests_refs: []
status: "documented-only"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Chapter 13 - Status Markers (Subsections)

```yaml
id: KB-RULE-13-1-general-markers
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "13.1"
topic: "General marker semantics and timing"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["status"]
steps: ["Apply marker effects according to timing and stacking rules."]
implementation_refs: ["assault_model/units/unit_instance.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-13-2-action-markers
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "13.2"
topic: "Action-related markers and legality impact"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["status","special_actions"]
steps: ["Gate action legality and modifiers from active markers."]
implementation_refs: ["assault_model/actions/status.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-13-3-morale-markers
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "13.3"
topic: "Morale/suppression marker transitions"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["status"]
steps: ["Resolve morale state changes and resulting restrictions."]
implementation_refs: ["assault_model/combat/morale.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

## Subsection-Level Records (Strict Pass v2 - Action Complete Focus)

This pass expands action coverage with explicit subtypes for movement and linked
action families so retrieval can answer "which movement/action variants exist?"
without collapsing multiple clauses into one record.

### Chapter 9 - Movement Variants (Expanded)

```yaml
id: KB-RULE-9-1-normal-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.1"
topic: "Normal movement"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Move using standard allowance and normal legality checks."]
implementation_refs: ["assault_model/rules/movement_rules.py","assault_model/actions/action_catalog.py"]
tests_refs: ["assault_sim/tests/test_action_executor.py"]
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-2-fast-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.2"
topic: "Fast movement variant"
rule_type: "unit-specific"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Apply fast-move allowance/penalties and compatibility constraints."]
implementation_refs: ["assault_model/rules/movement_rules.py","assault_model/actions/action_catalog.py"]
tests_refs: ["assault_sim/tests/test_action_executor.py"]
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-3-move-and-fire
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.3"
topic: "Move and fire composite action"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["movement","ranged_fire"]
steps: ["Resolve movement then apply fire eligibility/modifier constraints."]
implementation_refs: ["assault_model/actions/action_catalog.py","assault_model/combat/ranged_combat_resolver.py"]
tests_refs: ["assault_sim/tests/test_action_executor.py"]
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-1-hills
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.1"
topic: "Movement interactions with hills"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Apply hill entry/cost and related movement constraints."]
implementation_refs: ["assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-2-buildings
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.2"
topic: "Movement interactions with buildings"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Apply building entry/exit and occupancy movement constraints."]
implementation_refs: ["assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-3-roads-trails
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.3"
topic: "Road and trail movement modifiers"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Apply road/trail cost reductions and restrictions where legal."]
implementation_refs: ["assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-4-fortifications
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.4"
topic: "Fortification movement constraints"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Enforce movement legality across/into fortification features."]
implementation_refs: ["assault_model/rules/fortification_rules.py","assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-5-obstacles
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.5"
topic: "Obstacle crossing movement rules"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement"]
steps: ["Evaluate if obstacle crossing is legal and apply penalties."]
implementation_refs: ["assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-6-minefields
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.6"
topic: "Minefield trigger and movement restrictions"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement","status"]
steps: ["Resolve minefield movement legality, trigger, and resulting effects."]
implementation_refs: ["assault_model/rules/movement_terrain_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-8-1-infantry-specific-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.8.1"
topic: "Infantry specific movement clause A"
rule_type: "unit-specific"
unit_scope: ["infantry"]
action_scope: ["movement"]
steps: ["Apply infantry-only movement permissions/restrictions set A."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-8-2-infantry-specific-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.8.2"
topic: "Infantry specific movement clause B"
rule_type: "unit-specific"
unit_scope: ["infantry"]
action_scope: ["movement"]
steps: ["Apply infantry-only movement permissions/restrictions set B."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-9-artillery-specific-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.9"
topic: "Artillery specific movement"
rule_type: "unit-specific"
unit_scope: ["artillery"]
action_scope: ["movement"]
steps: ["Apply artillery movement constraints including setup/immobility rules."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-10-1-vehicle-specific-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.10.1"
topic: "Vehicle specific movement clause A"
rule_type: "unit-specific"
unit_scope: ["vehicle"]
action_scope: ["movement"]
steps: ["Apply vehicle movement constraints for clause A."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-10-2-vehicle-specific-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.10.2"
topic: "Vehicle specific movement clause B"
rule_type: "unit-specific"
unit_scope: ["vehicle"]
action_scope: ["movement"]
steps: ["Apply vehicle movement constraints for clause B."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-10-3-vehicle-specific-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.10.3"
topic: "Vehicle specific movement clause C"
rule_type: "unit-specific"
unit_scope: ["vehicle"]
action_scope: ["movement"]
steps: ["Apply vehicle movement constraints for clause C."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-11-1-transport-capacity
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.11.1"
topic: "Transport capacity and passenger eligibility"
rule_type: "unit-specific"
unit_scope: ["infantry","vehicle"]
action_scope: ["movement","special_actions"]
steps: ["Validate who can embark and transport capacity limits."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-11-2-embark-disembark-order
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.11.2"
topic: "Embark/disembark sequencing and legality"
rule_type: "unit-specific"
unit_scope: ["infantry","vehicle"]
action_scope: ["movement","special_actions"]
steps: ["Enforce legal order/timing for embark and disembark."]
implementation_refs: ["assault_model/rules/movement_rules.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-11-3-emergency-unload
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.11.3"
topic: "Emergency unload/disembark transport edge case"
rule_type: "exception"
unit_scope: ["infantry","vehicle"]
action_scope: ["movement","ranged_fire","close_combat"]
steps: ["Resolve forced unload with valid destination and penalties."]
implementation_refs: ["assault_model/combat/ranged_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-12-hide-action
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.12"
topic: "Hide action declaration and concealment state"
rule_type: "unit-specific"
unit_scope: ["infantry","all"]
action_scope: ["movement","special_actions","status"]
steps: ["Apply legal hide declaration and concealment state transition."]
implementation_refs: ["assault_model/actions/status.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-12-1-ambush-trigger
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.12.1"
topic: "Ambush trigger conditions"
rule_type: "exception"
unit_scope: ["infantry","all"]
action_scope: ["movement","ranged_fire","special_actions"]
steps: ["Check ambush trigger windows and reveal/attack legality."]
implementation_refs: ["assault_model/combat/reaction_state.py","assault_model/combat/reaction_fire_resolution.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-13-covering-fire-move
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.13"
topic: "Movement with covering fire"
rule_type: "unit-specific"
unit_scope: ["all"]
action_scope: ["movement","ranged_fire","support"]
steps: ["Resolve move + covering fire sequencing and legality constraints."]
implementation_refs: ["assault_model/actions/action_catalog.py","assault_model/combat/ranged_combat_resolver.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Action Families - Explicit Anchors

```yaml
id: KB-RULE-ACTION-PASS
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "8.1"
topic: "Pass action"
rule_type: "basic"
unit_scope: ["all"]
action_scope: ["special_actions"]
steps: ["Skip action legally and advance activation state."]
implementation_refs: ["assault_model/actions/status.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-ACTION-REACTION-FIRE
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "8.2"
topic: "Reaction fire interrupt action"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["special_actions","ranged_fire"]
steps: ["Open reaction window, validate trigger, resolve interrupt fire."]
implementation_refs: ["assault_model/combat/reaction_state.py","assault_model/combat/reaction_fire_resolution.py"]
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-ACTION-COMMAND-CARD
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "8.3"
topic: "Command card action timing"
rule_type: "optional"
unit_scope: ["all"]
action_scope: ["special_actions"]
steps: ["Apply card timing and effect only in legal timing windows."]
implementation_refs: []
tests_refs: []
status: "documented-only"
last_review_utc: "2026-06-27T00:00:00Z"
```

## Subsection-Level Records (Strict Pass v3 - Facing Specific)

Focused expansion for fire-arc and fortification-orientation cases so explainable
retrieval can answer directional legality and modifier questions directly.

### Fire Arc and Facing (10.3)

```yaml
id: KB-RULE-10-3-1-fire-arc-front
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.3"
topic: "Front arc fire legality"
rule_type: "unit-specific"
unit_scope: ["vehicle","all"]
action_scope: ["ranged_fire"]
prerequisites: ["Target must be inside front fire arc for front-only weapons."]
prohibitions: ["Attack is illegal when target lies outside permitted front arc."]
steps:
  - "Determine attacker facing and weapon arc profile."
  - "Project target hex relative to attacker facing."
  - "Allow fire only if target is in front arc."
edge_cases:
  - "Turret-capable units may override strict hull-front constraints."
implementation_refs:
  - "assault_model/combat/line_of_sight.py"
  - "assault_model/combat/ranged_combat_resolver.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-10-3-2-fire-arc-flank
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.3"
topic: "Flank arc fire legality and effects"
rule_type: "unit-specific"
unit_scope: ["vehicle","all"]
action_scope: ["ranged_fire"]
prerequisites: ["Target must fall in legal lateral arc for the firing profile."]
prohibitions: ["No flank shot if unit/weapon profile forbids lateral fire."]
steps:
  - "Classify target bearing as flank-left or flank-right."
  - "Apply flank-arc legality constraints."
  - "Apply any flank-specific modifiers if rule-set requires."
implementation_refs:
  - "assault_model/combat/line_of_sight.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-10-3-3-fire-arc-rear
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "10.3"
topic: "Rear arc shot legality"
rule_type: "unit-specific"
unit_scope: ["vehicle","all"]
action_scope: ["ranged_fire"]
prerequisites: ["Rear arc attacks are legal only for weapons/profiles that permit them."]
prohibitions: ["Reject rear shot when attacker arc does not include rear bearing."]
steps:
  - "Determine rear-bearing relation from facing."
  - "Check weapon/vehicle profile for rear fire permission."
  - "Resolve attack only if rear-fire legality is satisfied."
edge_cases:
  - "Pivot/orientation changes in prior action may alter arc classification."
implementation_refs:
  - "assault_model/combat/line_of_sight.py"
  - "assault_model/actions/action_catalog.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```

### Fortifications by Orientation (9.6.4)

```yaml
id: KB-RULE-9-6-4-1-fortification-facing-front
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.4"
topic: "Fortification frontal orientation interaction"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement","ranged_fire","close_combat"]
prerequisites: ["Unit enters/attacks fortification side aligned with frontal orientation rules."]
prohibitions: ["Disallow movement/attack options blocked by frontal-facing fortification geometry."]
steps:
  - "Identify fortification facing and front side."
  - "Classify approach vector as frontal."
  - "Apply frontal access/protection modifiers and legality."
implementation_refs:
  - "assault_model/rules/fortification_rules.py"
  - "assault_model/rules/movement_terrain_rules.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-4-2-fortification-facing-oblique
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.4"
topic: "Fortification oblique/flank orientation interaction"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement","ranged_fire","close_combat"]
prerequisites: ["Approach vector intersects non-frontal protected sides."]
prohibitions: ["Reject transitions through disallowed flanking edges if geometry forbids."]
steps:
  - "Compute relative bearing against fortification facing."
  - "Mark approach as oblique/flank."
  - "Apply flank-side entry/fire/assault constraints."
implementation_refs:
  - "assault_model/rules/fortification_rules.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
---
id: KB-RULE-9-6-4-3-fortification-facing-rear
source_pdf: docs/pdfs/2024_09_18_Rulebook_rev6_web.pdf
source_ref: "9.6.4"
topic: "Fortification rear orientation interaction"
rule_type: "exception"
unit_scope: ["all"]
action_scope: ["movement","ranged_fire","close_combat"]
prerequisites: ["Approach/attack path reaches fortification rear side."]
prohibitions: ["Block rear interactions when pathing/edge constraints prohibit access."]
steps:
  - "Determine rear side from fortification facing."
  - "Validate movement/fire/assault legality against rear side."
  - "Apply rear-side modifiers/penalties where defined."
edge_cases:
  - "Scenario-specific fortification templates may override default rear behavior."
implementation_refs:
  - "assault_model/rules/fortification_rules.py"
  - "assault_model/combat/line_of_sight.py"
tests_refs: []
status: "implemented-partial"
last_review_utc: "2026-06-27T00:00:00Z"
```
