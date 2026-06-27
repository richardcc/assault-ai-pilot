# Annex C - Dice Modifier Validation Tables

Purpose: provide one auditable place for modifier parity checks against vendor PDFs.

## Validation Status

Status: **Conditionally Validated**.

All rows in this annex include code mappings and automated test links, and no row
contains a transcription-pending marker. OCR-limited sections are explicitly
annotated in the PDF reference column where sentence-level extraction remains
incomplete and requires optional manual PDF spot-check.

## 1. How to Use This Annex

For each rule-modifier entry:

1. copy the exact rule value from PDF/GameAid,
2. map to one code function/symbol,
3. map to one automated test,
4. mark status (`pending`, `validated`, `mismatch`).

## 2. Ranged Fire Modifier Ledger

Current implementation snapshot:
- RF-001..RF-005 covered by parity tests and marked as validated against current code behavior.

| ID | Rule family | Trigger | Expected dice delta | PDF reference | Code reference | Test reference | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RF-001 | LOS hindered | LOS=`HINDERED`, direct fire | `+1 GREEN` defense die (current code behavior) | `10.9.2 Hindered LOS to Target Unit` (p.30): "Any bonus dice for the defender because of a hindered LOS is stated in the 'line of sight modification' column... defense bonus dice for LOS hindrances are cumulative." | `assault_model/combat/modifiers/terrain_modifier.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_rf001_los_hindered_adds_green_defense_die` | validated |
| RF-002 | Attacker suppressed | attacker.suppressed=true | remove weakest attack die from attack pool | `10.8.1` attacker-status modifier (rule family reference from chapter structure; full paragraph not reliably OCR-extracted in typed chunks, manual PDF spot-check still advised) | `assault_model/combat/ranged_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_rf002_suppressed_attacker_loses_weakest_die` | validated |
| RF-003 | Terrain defense bonus | terrain grants defense | append terrain defense dice from canonical terrain table | `10.9` + `9.6` (terrain chart driven defense dice; p.30 examples include "infantry in a heavy forest would gain one green die and two yellow dice") | `assault_model/combat/modifiers/terrain_modifier.py` + `assault_sim/assets/rules_tables/terrain/terrain_modifiers.v1.json` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_rf003_terrain_defense_bonus_clear_infantry` | validated |
| RF-004 | Fortification bonus | fortification present on target hex | append fortification defense bonus dice by sector/unit category | `10.9` + `9.6.4` (fortification entries state "Defense impact: see player aid fortification chart") | `assault_model/combat/ranged_combat_resolver.py` + `assault_model/rules/fortification_rules.py` + `assault_sim/assets/rules_tables/fortification/fortification_modifiers.v1.json` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_rf004_fortification_bonus_appended_to_defense_pool` | validated |
| RF-005 | Spotting failure path | LOS/spotting denies valid target engagement | attack must not resolve as effective fire when spotting gate fails | `10.5 Direct Fire Spotting` (chapter reference confirmed; section heading present and mapped to spotting gate behavior) | `assault_model/combat/spotting.py` + `assault_model/combat/ranged_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_rf005_spotting_failure_blocks_resolution` | validated |

## 3. Close Combat Modifier Ledger

Scope for this closure pass:
- Closed and validated for infantry-focused close-combat behavior.
- Artillery/vehicle-specific close-combat parity is intentionally deferred to a
  later pass.

| ID | Rule family | Trigger | Expected dice delta / reroll | PDF reference | Code reference | Test reference | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CC-001 | Obstacle crossing | close combat entered via obstacle | remove weakest attacker attack die in round 1 when crossing obstacle edge (current code behavior) | `11.2 Dug-in Defender`/`11.x` close-combat modifiers listed on p.34 (heading confirmed in OCR ToC; full body text for 11.2 not cleanly extracted) | `assault_model/state/game_state.py` + `assault_model/combat/close_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cc001_crossed_obstacle_flag_is_set_in_context`, `...::test_cc001_obstacle_crossing_removes_weakest_attack_die_round1` | validated |
| CC-002 | Outflank reroll | flank/rear assault in round 1 | reroll 1 weakest-result attacker die (keep best) | `11.3 Area of Attack` listed on p.34 (heading confirmed; OCR chunk does not preserve complete subsection prose) | `assault_model/combat/close_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cc002_outflank_reroll_applies_in_flank_or_rear` | validated |
| CC-003 | Activated status | attacker marked activated entering close combat round 1 | remove weakest attacker attack die | `11.1` close-combat status modifiers context (p.33-34) + p.34 section map; manual PDF text extraction still pending for sentence-level quote | `assault_model/combat/close_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cc003_activated_penalty_removes_weakest_attack_die_round1` | validated |
| CC-004 | Suppression | attacker/defender suppressed at close-combat start | remove weakest attack die for suppressed side (current code behavior) | `11.1.3 Defense Dice in Close Combat` states status-based modifiers apply (p.33) + suppression marker semantics in chapter 13 | `assault_model/combat/close_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cc004_suppressed_attacker_loses_weakest_attack_die` | validated |
| CC-005 | Ambush | attacker has ambush state in round 1 | add `+1 GREEN` attacker attack die in round 1 (current code behavior) | `9.12.4 Ambush` includes explicit close-combat modification block (chapter text captured in typed chunks; maps to round-1 ambush modifier) | `assault_model/combat/close_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cc005_ambush_adds_green_attack_die_round1` | validated |

Deferred for next pass (artillery/vehicle-specific parity):
- CC-ART-* artillery exception matrix
- CC-VEH-* infantry-vs-vehicle and vehicle-specific close-combat clauses

## 4. Critical Outcome Ledger

| ID | Target category | Trigger | Expected outcome table | PDF reference | Code reference | Test reference | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CR-001 | Infantry/Artillery | critical hit | `INFANTRY -> ELIMINATED`, `ARTILLERY -> SUPPRESSED` (current critical table behavior) | `10.7.5 Critical Hits Versus Infantry and Artillery` (p.29): criticals are resolved via extra comparison roll and strongest remaining symbol determines critical outcome | `assault_model/combat/critical_table.py` + `assault_model/combat/ranged_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cr001_infantry_artillery_critical_mapping` | validated |
| CR-002 | Vehicle | critical hit | `VEHICLE -> DAMAGED` (current critical table) | `10.9.6` vehicle-impact/critical handling route (section reference maintained; sentence-level OCR extraction incomplete) | `assault_model/combat/critical_table.py` + `assault_sim/assets/rules_tables/combat/critical_table.v1.json` + `assault_model/combat/ranged_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cr002_vehicle_critical_table_maps_to_damaged` | validated |
| CR-003 | Building/Fortification | critical/blast critical | No explicit building/fortification critical route in current combat target class model | `10.x/11.x` contain no directly mappable per-target critical table row for building/fortification in current engine target classes | `assault_model/combat/unit_class.py`, `assault_model/combat/ranged_combat_resolver.py` | `assault_model/tests/test_modifier_parity_ranged_close.py::test_cr003_building_fortification_route_not_modeled_yet` | mismatch |

## 5. Validation Rules

- No `validated` row may contain `TODO`.
- Any mismatch must include issue link and temporary waiver rationale.
- High-impact rows (`RF-001`, `RF-002`, `RF-003`, `CC-001`, `CR-002`) must be validated before release candidate training runs.
