# Vendor Game Model (Canonical)

This document summarizes the game model defined by vendor PDFs.  
Primary sources: Rulebook v2.0, Campaign Book v1.0, LOS Examples v1.0, GameAid/TEC clarifications.

## 1) System Scope

Assault is a hex-and-counter tactical system with:

- phased turn sequence,
- unit-level activation and action choices,
- terrain/LOS/spotting-driven combat resolution,
- objective and scenario/campaign victory logic,
- optional expansions (command cards, TAS/OAS, FoW, etc.).

## 2) Core Turn Structure (Rulebook v2.0)

High-level phases (chapter 6):

1. Initiative
2. Planning
3. Support
4. Action
5. Organization
6. Victory Check
7. Reinforcements

The implementation must preserve this order at gameplay level, even when internally optimized.

## 3) Action Taxonomy

From Rulebook chapters 7–11 and special actions:

- **Support actions**: indirect fire, smoke, artillery facing, specials.
- **Special actions**: pass, reaction fire, command card play.
- **Movement actions** (chapter 9):
  - normal/fast movement,
  - move-and-fire options,
  - terrain and harsh terrain interactions,
  - roads/trails, buildings, fortifications, obstacles, minefields,
  - objective capture,
  - infantry/artillery/vehicle-specific movement constraints.
- **Ranged fire** (chapter 10):
  - range factor,
  - LOS and spotting,
  - attack/defense dice and modifiers,
  - critical hit logic by target type.
- **Close combat** (chapter 11):
  - initiation, attack/defense dice modifications,
  - area of attack, support/re-roll contexts, vehicle interactions.

## 4) Terrain, Elevation, LOS, and Spotting

From Rulebook chapter 10 + LOS Examples + GameAid:

- LOS is traced hex-to-hex with terrain/elevation effects.
- LOS states: clear / hindered / blocked.
- Hindrance accumulation is capped (third hindrance can block LOS).
- Building types have distinct LOS/elevation semantics:
  - single-storey, multi-storey, large building differ in LOS impact.
- Terrain charts define:
  - defense effects,
  - movement costs,
  - LOS relevance by terrain and elevation.
- Spotting has explicit roll logic and automatic spotting cases.
- Failed spotting implies blind fire penalties/modifiers (per aid/rules).

## 5) Unit State and Morale Effects

Key status categories in vendor material:

- action status (firing, move/fire, etc.),
- morale status (suppressed, fallback),
- hidden/ambush family,
- half-strength impacts on combat behavior.

Status markers modify both attack and defense procedures, and often alter eligibility for certain actions.

## 6) Objectives and Victory

From Rulebook + Campaign Book:

- Objective hexes can be captured according to chapter 9.7.
- Victory evaluation occurs in dedicated phase logic.
- Campaign book introduces scenario chaining, troop tracking, and end-of-campaign outcomes.
- Campaign-specific rules may override/extend base rules where explicitly stated.

## 7) Optional Modules and Their Status in Vendor Docs

- **Command Cards / Command Points**: optional module integrated in planning/action flow.
- **TAS/OAS** (chapter 12): optional advanced support system with dedicated sequence.
- **FoW markers** (`2025_09_10_FoW_v01.pdf`): explicitly marked as optional draft/experimental.

## 8) Rules Precedence

Canonical precedence used for this project:

1. Rulebook v2.0 base rules.
2. Campaign Book rules for campaign context (explicitly higher when conflict is stated).
3. Clarification docs (`TEC_Clarification`, `GameAid`, LOS Examples) as interpretive support.
4. Optional draft modules (FoW) only when explicitly enabled.
