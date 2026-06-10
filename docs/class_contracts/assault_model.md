# assault_model Class Contracts

## actions

`Action`, `MovementAction`, `CombatAction`, `ActionCatalog`, `ActionResolutionResult`, `MoveAction`, `AdvanceAction`, `FastMoveAction`, `RangedAttackAction`, `CloseCombatAction`, `AssaultAction`, `RangedDirectAttack`, `RangedIndirectAttack`, `ReactionFireAction`, `EmbarkAction`, `WaitAction`, `EndTurnAction`, `MoveThenFireAction`, `FireThenMoveAction`

- **Input contract**: action context, actor/target metadata, movement/combat parameters.
- **Output contract**: executable action object and/or deterministic state delta.
- **Responsibility**: define legal tactical operations and action variants.

## combat

`AttackDie`, `DefenseDie`, `BattleDie`, `DicePool`, `AttackDicePool`, `DefenseDicePool`, `DiceResult`, `AttackProfile`, `DefenseProfile`, `RangeAttackProfile`, `CombatActionContext`, `CombatResolutionContext`, `CombatResolutionResult`, `CloseCombatRoundResult`, `CloseCombatResult`, `ReactionContext`, `ReactionCondition`, `ReactionState`, `DiceModifier`, `TerrainModifier`, `MoraleModifier`, `LineOfSightModifier`, `FlankModifier`

- **Input contract**: combat participants, range/LOS/terrain/modifier context, RNG stream.
- **Output contract**: roll comparisons, effect chains, combat results.
- **Responsibility**: implement deterministic combat resolution and modifier application.

### combat enums / typed classes

`DiceColor`, `DiceFace`, `RangeBand`, `CombatBand`, `AttackSector`, `Flank`, `CriticalEffect`, `UnitClass`, `LineOfSight`, `ReactionTrigger`

- **Input**: valid enum domain value.
- **Output**: normalized symbolic value for resolvers.

## core

`Scenario`, `VictoryPoint`, `VictoryPointTracker`, `VictoryConditions`, `ActivationState`, `ReactionRegistry`

- **Input contract**: scenario/objective/activation definitions.
- **Output contract**: objective tracking, win checks, activation bookkeeping.
- **Responsibility**: game meta-logic (scenario/victory/activation registries).

## map

`Map`, `Hex`, `HexCoord`, `HexState`, `MapPieceDefinition`, `TerrainConfig`, `FortificationConfig`

- **Input contract**: map topology, terrain and fortification tables.
- **Output contract**: queryable board and per-hex dynamic state.
- **Responsibility**: map representation and map-rule parameters.

### map enums / typed classes

`Terrain`, `HexDirection`, `HexOwnership`, `HexEdgeFeature`

## rules

`MovementRules`, `MovementTerrainRules`, `MovementPath`, `MovementOutcome`

- **Input contract**: unit + map + occupancy + movement budget.
- **Output contract**: legal movement paths and categorized outcomes.
- **Responsibility**: movement legality and outcome modeling.

## runtime and state

`RuntimeGameState`, `ExecutionContext`, `GameStateReactions`, `GameState`, `TurnState`, `TurnPhase`

- **Input contract**: current state + action execution context.
- **Output contract**: authoritative state transitions and phase progression.
- **Responsibility**: runtime engine and canonical state lifecycle.

## units

`UnitInstance`, `UnitType`, `UnitSide`, `UnitCategory`

- **Input contract**: static unit profile + runtime attributes.
- **Output contract**: mutable unit state and capability accessors.
- **Responsibility**: unit taxonomy and in-match unit representation.
