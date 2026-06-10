# Class Hierarchy by Package

Status: **Pending Validation**

This document inventories classes currently defined in the codebase, grouped by package hierarchy.

## Scope

- Included: `assault_model`, `assault_sim`, `assault_backend`, `assault_ai_ui/src`
- Excluded: test-only helper classes

## `assault_model`

### `assault_model/actions`

- `Action`
- `MovementAction`
- `CombatAction`
- `ActionCatalog`
- `ActionResolutionResult`
- `MoveAction`
- `AdvanceAction`
- `FastMoveAction`
- `RangedAttackAction`
- `CloseCombatAction`
- `AssaultAction`
- `RangedDirectAttack`
- `RangedIndirectAttack`
- `ReactionFireAction`
- `EmbarkAction`
- `WaitAction`
- `EndTurnAction`
- `MoveThenFireAction`
- `FireThenMoveAction`

### `assault_model/combat`

- `AttackDie`
- `DefenseDie`
- `BattleDie`
- `DicePool`
- `AttackDicePool`
- `DefenseDicePool`
- `DiceResult`
- `AttackProfile`
- `DefenseProfile`
- `RangeAttackProfile`
- `CombatActionContext`
- `CombatResolutionContext`
- `CombatResolutionResult`
- `CloseCombatRoundResult`
- `CloseCombatResult`
- `ReactionContext`
- `ReactionCondition`
- `ReactionState`
- `DiceModifier`
- `TerrainModifier`
- `MoraleModifier`
- `LineOfSightModifier`
- `FlankModifier`

### `assault_model/combat` (Enums / typed classes)

- `DiceColor`
- `DiceFace`
- `RangeBand`
- `CombatBand`
- `AttackSector`
- `Flank`
- `CriticalEffect`
- `UnitClass`
- `LineOfSight`
- `ReactionTrigger`

### `assault_model/core`

- `Scenario`
- `VictoryPoint`
- `VictoryPointTracker`
- `VictoryConditions`
- `ActivationState`
- `ReactionRegistry`

### `assault_model/map`

- `Map`
- `Hex`
- `HexCoord`
- `HexState`
- `MapPieceDefinition`
- `TerrainConfig`
- `FortificationConfig`

### `assault_model/map` (Enums / typed classes)

- `Terrain`
- `HexDirection`
- `HexOwnership`
- `HexEdgeFeature`

### `assault_model/rules`

- `MovementRules`
- `MovementTerrainRules`
- `MovementPath`

### `assault_model/rules` (Enums / typed classes)

- `MovementOutcome`

### `assault_model/runtime`

- `RuntimeGameState`
- `ExecutionContext`
- `GameStateReactions`

### `assault_model/state`

- `GameState`
- `TurnState`

### `assault_model/state` (Enums / typed classes)

- `TurnPhase`

### `assault_model/units`

- `UnitInstance`
- `UnitType`

### `assault_model/units` (Enums / typed classes)

- `UnitSide`
- `UnitCategory`

## `assault_sim`

### `assault_sim/config`

- `SimConfig`
- `RewardConfig`
- `MovementTacticalConfig`
- `PPOConfig`
- `ScenarioScheduleEntry`
- `TrainConfig`

### `assault_sim/contracts`

- `TrajectoryStep`
- `RolloutBatch`
- `EvalResult`

### `assault_sim/decision`

- `ActionDecisionTrace`
- `ActionBridge`
- `DecisionEngine`
- `DecisionEngineController`
- `HRLController`
- `OptionExecutor`
- `RLvsHeuristicController`
- `SideController`

### `assault_sim/envs`

- `_GymActionController`
- `GymAssaultEnv`

### `assault_sim/engine`

- `ActivationManager`
- `MatchRunner`
- `MetricsTracker`

### `assault_sim/evaluation`

- `AdvancedMetrics`
- `Evaluator`
- `EvalDashboard`
- `EvaluationLogger`
- `MetricsTracker`
- `ResultsAnalyzer`
- `SB3EvalController`
- `ExperimentRow`
- `EpisodeRow`
- `DecisionRow`
- `OutcomeRow`

### `assault_sim/heuristics`

- `HeuristicBase`
- `BasicHeuristic`
- `HeuristicTracer`
- `MoveToVictoryPointHeuristic`
- `NoOpHeuristic`
- `Phase01_InitialContactPolicy`
- `TacticalPathHeuristic`
- `Target`
- `VictoryPointBrick`

### `assault_sim/knowledge`

- `KnowledgeBrick`
- `KnowledgeArea`
- `EnemyProximityBrick`

### `assault_sim/policies`

- `PolicyRegistry`

### `assault_sim/rewards`

- `BaseReward`
- `ProgressiveReward`
- `ShapedReward`
- `VPDifferenceReward`
- `CombatReward`
- `DecisionReward`
- `PositioningReward`
- `SurvivalReward`
- `VPReward`

### `assault_sim/rl`

- `PolicyNet`
- `ReplayBuffer`
- `OptionPolicy`
- `RLPolicyController`
- `RandomPolicyController`
- `SideAwareController`

### `assault_sim/rl` (Enums / typed classes)

- `TacticalOption`
- `StrategicIntent`

### `assault_sim/debug`

- `CombatRenderer`
- `ConsoleListener`
- `ConsoleObserver`
- `DebugConfig`
- `DeploymentRenderer`
- `EventBus`
- `MapRenderer`
- `MovementRenderer`
- `Replay`
- `ReplayObserver`
- `ReplayWriter`
- `TurnBuffer`
- `UnitFormatter`

### Root module classes

- `SimEnv`
- `TrainingEnv`

## `assault_backend`

### Root package

- `ExplainableEngine`
- `GameSession`
- `HRLCache`
- `HRLService`
- `TacticalCache`
- `TacticalService`
- `SB3AIService`

### `assault_backend/main.py` (API request models)

- `GameStartRequest`
- `UnitActionsRequest`

### `assault_backend/schemas`

- `StrategicState`
- `ActivationPayload`
- `ExplainActivationRequest`
- `ExplainActivationResponse`
- `ScenarioSide`
- `ScenarioResponse`

## `assault_ai_ui/src`

### `assault_ai_ui/src/game`

- `GameController`
- `HighlightLayer`
- `UnitLayer`
- `SoundService`

## Maintenance Rule

Any new class or class rename must update this file in the same task.
