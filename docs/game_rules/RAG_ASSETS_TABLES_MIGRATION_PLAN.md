# RAG + Engine Tables Consolidation Plan

Goal: make `assault_sim/assets` the single source for rules tables consumed by
both the simulation engine and the RAG explainer.

## Current State (Observed)

- `assault_sim/assets` is currently empty.
- Rules data is split across code and data files, mainly under `assault_model`.

### Existing table-like sources

- `assault_model/map/terrain_modifiers.json`
  - terrain defense dice
  - LOS class per terrain (`CLEAR`, `HINDERED`, `BLOCKED`)
  - movement costs by movement mode (`foot`, `artillery`, `wheeled`, `track`)
- `assault_model/map/fortification_modifiers.json`
  - fortification defense bonuses by attacker sector (`FRONT`, `FLANK_*`, `REAR`, `ABOVE`)
  - movement deltas and blocked movement types
- `assault_model/combat/battle_die.py`
  - `DICE_FACE_TABLE` currently hardcoded in Python
- `assault_model/combat/critical_table.py.py`
  - critical outcome map by unit class (also filename should be fixed later)
- `assault_model/combat/terrain_rules.py`
  - `TERRAIN_DEFENSE` hardcoded fallback/legacy table
- `assault_model/combat/line_of_sight.py`
  - LOS algorithm lives in code (expected), but depends on LOS terrain table

## Target Structure

Create and maintain all static rules tables under:

- `assault_sim/assets/rules_tables/terrain/`
- `assault_sim/assets/rules_tables/fortification/`
- `assault_sim/assets/rules_tables/combat/`
- `assault_sim/assets/rules_tables/los/`
- `assault_sim/assets/rules_tables/movement/`
- `assault_sim/assets/rules_tables/manifest/`

Suggested canonical files:

- `terrain/terrain_modifiers.v1.json`
- `fortification/fortification_modifiers.v1.json`
- `combat/dice_face_table.v1.json`
- `combat/critical_table.v1.json`
- `los/los_terrain_classes.v1.json` (can be derived from terrain table if desired)
- `manifest/rules_tables_manifest.v1.json`

## Migration Phases

### Phase 0 - Foundation

- Add `rules_tables_manifest.v1.json` with table IDs, versions, and source refs.
- Add loader utilities that can read from `assault_sim/assets/rules_tables`.
- Clean-cut mode: no fallback to legacy tables.

### Phase 1 - Move pure JSON tables first

- Promote:
  - `terrain_modifiers.json`
  - `fortification_modifiers.json`
- Update loaders (`terrain_config`, `fortification_config`) to read only from
  canonical assets.
- Status: completed for terrain and fortification tables.

### Phase 2 - Externalize hardcoded Python tables

- Move `DICE_FACE_TABLE` from `battle_die.py` into
  `combat/dice_face_table.v1.json`.
- Move critical map into `combat/critical_table.v1.json`.
- Keep code behavior unchanged; only source location changes.
- Status: completed in clean-cut mode (canonical assets active).

### Phase 3 - RAG linking

- Update RAG KB records (`implementation_refs` / data refs) to point at
  canonical files in `assault_sim/assets/rules_tables/...`.
- Ensure explanatory responses can cite exact table IDs + `source_ref`.

### Phase 4 - Cleanup and enforcement

- Remove/retire duplicated legacy tables once parity is validated.
- Add CI check: no new static combat/movement table constants in Python unless
  explicitly justified.

## Contract for Table Files

Each table file should expose:

- `table_id`: stable identifier
- `version`: semantic version-like string (`v1`)
- `source_pdf`: rulebook source
- `source_ref`: section(s) in PDF
- `schema_version`: schema for parser compatibility
- `data`: table payload

## Why this is the right direction

- One source of truth for gameplay data.
- RAG explanations and engine behavior stay aligned.
- Easier audits for "is this rule implemented exactly as table X?".
- Safer updates (versioned assets, deterministic diffs).
