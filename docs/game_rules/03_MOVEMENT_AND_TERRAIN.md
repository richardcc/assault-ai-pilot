# 03 - MOVEMENT AND TERRAIN (Detailed Implementation Spec)

Sources:

- `2024_09_18_Rulebook_rev6_web.pdf` (chapter 9)
- `PN007_GameAid_Back_rev3_web.pdf` (terrain and fortification charts)

## 1. Movement Action Model

Each movement decision must resolve:

1. actor eligibility,
2. legal path set generation,
3. movement-point feasibility,
4. endpoint legality (empty/enemy/friendly-vehicle),
5. post-move side effects (objective control, event emission, activation state).

## 2. Legal Path Generation Requirements

### 2.1 Inputs

- current map topology,
- unit movement allowance,
- unit movement type,
- terrain movement cost table,
- fortification/obstacle crossing rules,
- occupancy map (alive units only).

### 2.2 Outputs

Each path candidate must include:

- ordered hex list,
- resulting outcome category:
  - end in empty hex,
  - end in enemy hex (assault),
  - end in friendly transport vehicle.

### 2.3 Hard Constraints

- cannot exceed movement allowance,
- cannot traverse impassable terrain for that unit type,
- cannot end stacked on prohibited friendly unit types,
- enemy-occupied endpoint is not transit (assault endpoint).

## 3. Terrain Cost and Restriction Resolution Order

For each transition:

1. check hex exists,
2. check unit can enter terrain class,
3. compute base terrain movement cost,
4. apply fortification/obstacle movement modifiers,
5. reject if blocked/impassable,
6. accumulate cost and validate budget.

## 4. Harsh Terrain Handling

When chapter-defined harsh terrain exception applies:

- allow limited single-step entry behavior where rules permit,
- consume full/adjusted movement as specified,
- keep this behavior explicit and test-covered (not hidden fallback logic).

## 5. Special Terrain Categories

### 5.1 Buildings

- single-storey, multi-storey, and large buildings must be treated as distinct
  movement and LOS entities.

### 5.2 Roads and Trails

- pathing and direction-change costs must follow road/trail type semantics.
- covered trail effects can influence reaction/spotting interactions.

### 5.3 Fortifications

- sandbag, trench, gun position, bunker, pillbox:
  - crossing cost,
  - crossing permission,
  - occupancy semantics by unit type.

### 5.4 Obstacles

- stone wall, steep slope, barbed wire, tank barricade:
  - crossing penalties/restrictions vary by unit and action context.

### 5.5 Minefields

- apply entry/exit checks,
- apply result table effects with modifiers (Scout, Mine Detection, fallback, etc.),
- keep minefield behavior deterministic given seed and roll stream.

## 6. Objective Capture Coupling

Movement into objective hexes must integrate with objective control updates:

- control recalc timing must be consistent with end-of-action state,
- objective ownership persistence rules must match scenario logic.

## 7. Unit-Type Specific Notes

- Infantry: full movement rule set including concealment interactions.
- Artillery: additional mobility restrictions (elevation and placement constraints).
- Vehicles: terrain-damage, obstacle constraints, and transport-specific logic.

## 8. Recommended Tests

- distance/path consistency vs neighbor model,
- border/irregular-map path generation,
- enemy endpoint assault-only behavior,
- friendly transport endpoint behavior,
- objective-entry legal opportunity detection.

## 9. Validation Checklist

- [ ] Movement costs match terrain chart by unit type.
- [ ] Impassable transitions are rejected before path acceptance.
- [ ] Harsh terrain exception behavior is deterministic and tested.
- [ ] Endpoint categories (empty/enemy/friendly transport) are explicit.
- [ ] Objective control updates occur at correct timing point.
