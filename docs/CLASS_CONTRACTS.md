# Class Contracts (Inputs, Outputs, Responsibility)

Status: **Pending Validation**

This page documents each class with a practical contract view:

- **Input contract**: constructor/public method inputs or triggering context.
- **Output contract**: returned values and/or state mutations.
- **Responsibility**: what the class is expected to do.

Notes:

- For data/enum classes, contract is type/value domain oriented.
- For service/engine/resolver classes, output can be both return value and state/event side effects.

## `assault_model/actions`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `Action` | Action context + actor/target metadata | Executable action object/state delta | Base abstraction for game actions |
| `MovementAction` | Movement origin/path/actor constraints | Movement state transition | Base type for movement actions |
| `CombatAction` | Attacker/target/combat context | Combat resolution request | Base type for combat actions |
| `ActionCatalog` | Runtime state + active unit/side | Legal action set | Builds legal actions for current state |
| `ActionResolutionResult` | Applied action + runtime context | Success/failure + side effects summary | Standardized action execution result |
| `MoveAction` | Unit + legal movement path | Unit relocation + events | Standard movement execution |
| `AdvanceAction` | Unit + constrained advance path | Advance move state change | Controlled forward movement |
| `FastMoveAction` | Unit + fast move legality | Fast relocation + marker effects | High-tempo movement mode |
| `RangedAttackAction` | Attacker/target + LOS/spotting context | Ranged combat outcome | Direct ranged engagement action |
| `CloseCombatAction` | Adjacent engagement context | Close combat round/result | Close combat action wrapper |
| `AssaultAction` | Assault-legal movement/combat context | Assault outcome + occupancy update | Assault transition into combat |
| `RangedDirectAttack` | Direct fire legal context | Direct-fire result | Direct attack specialization |
| `RangedIndirectAttack` | Indirect fire legal context | Indirect-fire result/AoI effects | Indirect attack specialization |
| `ReactionFireAction` | Reaction trigger + legal fire context | Interrupt fire resolution | Reactive combat action |
| `EmbarkAction` | Infantry + friendly transport context | Embark state transition | Board transport action |
| `WaitAction` | Activable unit in phase context | No-op with activation consumption | Explicit pass/wait action |
| `EndTurnAction` | Turn-state context | Turn/phase transition | Ends current turn context |
| `MoveThenFireAction` | Composite path + shot context | Ordered move then fire effects | Composite tactical action |
| `FireThenMoveAction` | Composite shot + path context | Ordered fire then move effects | Composite tactical action |

## `assault_model/combat`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `AttackDie` | Attack die color/value domain | Single die result semantics | Attack die domain object |
| `DefenseDie` | Defense die color/value domain | Single die result semantics | Defense die domain object |
| `BattleDie` | Dice roll request + RNG | Symbol/result value | Core die rolling logic |
| `DicePool` | Dice list + modifiers | Comparable pool result | Base dice-pool abstraction |
| `AttackDicePool` | Attack profile + attack modifiers | Final attack dice pool | Build attack-side pool |
| `DefenseDicePool` | Defense profile + defense modifiers | Final defense dice pool | Build defense-side pool |
| `DiceResult` | Rolled symbols/values | Structured roll result | Encapsulates dice outcome |
| `AttackProfile` | Unit attack stats by context | Attack dice selection | Attack profile definition |
| `DefenseProfile` | Unit defense stats by sector/context | Defense dice selection | Defense profile definition |
| `RangeAttackProfile` | Range band + unit capability | Range-adjusted attack profile | Range-aware attack modeling |
| `CombatActionContext` | Attacker/target/map/LOS context | Validated combat context object | Shared context for combat logic |
| `CombatResolutionContext` | Combat context + modifiers + RNG | Resolution-ready context | Detailed close-combat context |
| `CombatResolutionResult` | Combat compare/effect chain | Damage/suppression/critical output | Final combat result container |
| `CloseCombatRoundResult` | Round inputs + dice compare | Round-level combat result | Per-round close-combat output |
| `CloseCombatResult` | Multi-round engagement context | Engagement end-state | Aggregated close-combat output |
| `ReactionContext` | Triggering action + reacting unit state | Reaction eligibility/resolution context | Encodes reaction-fire context |
| `ReactionCondition` | Trigger/state checks | Boolean eligibility | Reaction condition evaluator |
| `ReactionState` | Reaction lifecycle state | State flags/status | Tracks reaction processing state |
| `DiceModifier` | Base pool + condition | Modified pool/delta | Abstract modifier contract |
| `TerrainModifier` | Terrain + unit/attack context | Terrain-based dice delta | Applies terrain modifiers |
| `MoraleModifier` | Morale/suppression/fallback state | Morale-based dice delta | Applies morale modifiers |
| `LineOfSightModifier` | LOS state + fire mode | LOS-based dice delta | Applies LOS-driven modifiers |
| `FlankModifier` | Sector/flank context | Flank bonus/penalty | Applies flanking modifier rules |

## `assault_model/combat` enums and typed classes

`DiceColor`, `DiceFace`, `RangeBand`, `CombatBand`, `AttackSector`, `Flank`, `CriticalEffect`, `UnitClass`, `LineOfSight`, `ReactionTrigger`

- **Input contract**: valid enum member domain.
- **Output contract**: normalized symbolic value used by resolvers/services.
- **Responsibility**: constrain and standardize combat domain vocabulary.

## `assault_model/core`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `Scenario` | Scenario config data | Runtime scenario definition | Scenario metadata and setup |
| `VictoryPoint` | VP hex identity + owner/value | VP state object | Objective point representation |
| `VictoryPointTracker` | Game state + VP updates | VP totals/control summary | Tracks objective control changes |
| `VictoryConditions` | State + scenario win rules | Win/loss/draw decision | Evaluates victory conditions |
| `ActivationState` | Unit activation inputs | Activation bookkeeping | Tracks side/unit activation flow |
| `ReactionRegistry` | Reaction rules + handlers | Reaction lookup/dispatch map | Registers reaction behavior |

## `assault_model/map`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `Map` | Hex grid + terrain metadata | Queryable board state | Main map container |
| `Hex` | Coordinate + terrain/features | Hex state object | Single cell domain object |
| `HexCoord` | q,r coordinate values | Coordinate utility value | Coordinate canonical type |
| `HexState` | Ownership/marker/status fields | Mutable hex runtime state | Stores per-hex dynamic state |
| `MapPieceDefinition` | Map-piece file/config input | Piece topology definition | Defines reusable map fragments |
| `TerrainConfig` | Terrain rules/config tables | Terrain movement/defense data | Terrain parameter resolver |
| `FortificationConfig` | Fortification config tables | Fortification bonus/cost data | Fortification parameter resolver |

## `assault_model/map` enums and typed classes

`Terrain`, `HexDirection`, `HexOwnership`, `HexEdgeFeature`

- **Input contract**: valid map-domain enum value.
- **Output contract**: normalized value consumed by movement/LOS/combat logic.
- **Responsibility**: encode map and ownership state domains.

## `assault_model/rules`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `MovementRules` | Unit + map + budget + occupancy | Legal movement outcomes/paths | Main movement legality engine |
| `MovementTerrainRules` | Terrain + unit-type context | Entry cost/permission | Terrain-specific movement constraints |
| `MovementPath` | Ordered hex sequence + cost metadata | Path object + total movement cost | Encapsulates candidate path |

`MovementOutcome` (enum):

- **Input contract**: movement legality decision domain.
- **Output contract**: normalized outcome label.
- **Responsibility**: represent movement result categories.

## `assault_model/runtime` and `state`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `RuntimeGameState` | Base game state + scenario | Mutable runtime engine state | Authoritative state transition layer |
| `ExecutionContext` | Action execution parameters | Structured execution context | Carries runtime execution metadata |
| `GameStateReactions` | Runtime state + trigger events | Reaction processing updates | Applies reaction side effects |
| `GameState` | Initial map/unit/objective data | Full game-state snapshot | Canonical state model |
| `TurnState` | Phase/turn counters + active side | Turn progression state | Turn lifecycle bookkeeping |

`TurnPhase` (enum):

- **Input contract**: phase-domain value.
- **Output contract**: normalized phase identifier.
- **Responsibility**: constrain turn machine transitions.

## `assault_model/units`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `UnitInstance` | Unit type + runtime status/position | Mutable unit state | Represents a unit in play |
| `UnitType` | Unit card/profile data | Combat/movement capability accessors | Static unit capabilities model |

`UnitSide`, `UnitCategory` (enums):

- **Input contract**: valid side/category value.
- **Output contract**: normalized unit taxonomy value.
- **Responsibility**: enforce side/category domain consistency.

## `assault_sim/config` and `contracts`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `SimConfig` | Simulation config sources | Runtime simulation config object | Central sim configuration |
| `RewardConfig` | Reward parameters | Reward weight/config object | Reward shaping config |
| `MovementTacticalConfig` | Tactical movement knobs | Tactical threshold config | Movement tactical tuning |
| `PPOConfig` | PPO hyperparameters | PPO-ready config object | Training algorithm config |
| `ScenarioScheduleEntry` | Scenario id + episode allocation | Schedule row object | Per-scenario training allocation |
| `TrainConfig` | Training run parameters | Complete train/eval config | Top-level training configuration |
| `TrajectoryStep` | obs/action/reward/next_obs fields | Step data record | Single transition contract |
| `RolloutBatch` | Sequence of trajectory steps | Batch for training update | Rollout storage contract |
| `EvalResult` | Episode metrics fields | Structured eval output | Evaluation result record |

## `assault_sim/decision`, `envs`, `engine`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `ActionDecisionTrace` | Decision metadata fields | Trace record | Captures decision telemetry |
| `ActionBridge` | Policy output + legal action set | Concrete executable action | Translates policy to action |
| `DecisionEngine` | Current state + side policy context | Selected action/option | Core tactical decision driver |
| `DecisionEngineController` | Side + engine + runtime state | Side action decision | Controller wrapper for engine |
| `HRLController` | Hierarchical policy + state | Strategic+tactical action choice | HRL top-level controller |
| `OptionExecutor` | Strategy/option + legal actions | Chosen action with tags | Applies option-level guardrails |
| `RLvsHeuristicController` | RL policy + heuristic fallback | Action choice | Hybrid control adapter |
| `SideController` | Side-specific policy input | Side action decision | Side-focused decision interface |
| `_GymActionController` | Gym action vector + env state | Executable game action | Gym-to-game action translator |
| `GymAssaultEnv` | Config + scenario + runtime hooks | Gym step/reset API outputs | RL environment wrapper |
| `ActivationManager` | Runtime units/sides state | Next activable side/unit flow | Activation rotation manager |
| `MatchRunner` | Env/controllers + episode config | Match result and logs | Runs full match rollout |
| `MetricsTracker` | Step/episode events | Aggregated metrics snapshot | Tracks episode metrics |

## `assault_sim/evaluation`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `AdvancedMetrics` | Episode traces and counters | Derived advanced KPIs | Computes advanced evaluation metrics |
| `Evaluator` | Env + controllers + scenario context | Per-episode eval result | Runs and scores evaluation episodes |
| `EvalDashboard` | Eval aggregates | Report-ready dashboard data | Formats evaluation summaries |
| `EvaluationLogger` | Episode/decision/outcome rows | CSV/log outputs | Persists evaluation rows |
| `ResultsAnalyzer` | Multiple eval results | Aggregate performance report | Consolidates experiment outcomes |
| `SB3EvalController` | SB3 model + state | Model action selection | SB3-specific eval controller |
| `ExperimentRow` | Experiment-level fields | Typed row object | CSV data model |
| `EpisodeRow` | Episode-level fields | Typed row object | CSV data model |
| `DecisionRow` | Decision-level fields | Typed row object | CSV data model |
| `OutcomeRow` | Outcome-level fields | Typed row object | CSV data model |

## `assault_sim/heuristics`, `knowledge`, `policies`, `rewards`, `rl`, `debug`

### Heuristics and knowledge

`HeuristicBase`, `BasicHeuristic`, `HeuristicTracer`, `MoveToVictoryPointHeuristic`, `NoOpHeuristic`, `Phase01_InitialContactPolicy`, `TacticalPathHeuristic`, `Target`, `VictoryPointBrick`, `KnowledgeBrick`, `KnowledgeArea`, `EnemyProximityBrick`, `PolicyRegistry`

- **Input contract**: tactical state features and/or unit/map context.
- **Output contract**: target/score/action hint or heuristic decision.
- **Responsibility**: provide deterministic tactical guidance blocks and policy lookup.

### Rewards

`BaseReward`, `ProgressiveReward`, `ShapedReward`, `VPDifferenceReward`, `CombatReward`, `DecisionReward`, `PositioningReward`, `SurvivalReward`, `VPReward`

- **Input contract**: transition tuple (state, action, next_state, done/info).
- **Output contract**: scalar reward component or composed reward.
- **Responsibility**: define and aggregate reward shaping logic.

### RL core

`PolicyNet`, `ReplayBuffer`, `OptionPolicy`, `RLPolicyController`, `RandomPolicyController`, `SideAwareController`, `TacticalOption`, `StrategicIntent`

- **Input contract**: encoded observations/action masks and policy state.
- **Output contract**: logits/actions/controller decisions.
- **Responsibility**: learning policy representation and action selection.

### Debug

`CombatRenderer`, `ConsoleListener`, `ConsoleObserver`, `DebugConfig`, `DeploymentRenderer`, `EventBus`, `MapRenderer`, `MovementRenderer`, `Replay`, `ReplayObserver`, `ReplayWriter`, `TurnBuffer`, `UnitFormatter`

- **Input contract**: runtime/debug events and snapshots.
- **Output contract**: rendered/debug artifacts, logs, or replay persistence.
- **Responsibility**: observability and replay tooling.

### Root classes

`SimEnv`, `TrainingEnv`

- **Input contract**: simulation/training config + scenario/runtime dependencies.
- **Output contract**: step/reset transitions and training-compatible interfaces.
- **Responsibility**: high-level simulation and training orchestration.

## `assault_backend`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `ExplainableEngine` | Request state + explanation context | Explanation payload | Produces explainable tactical rationale |
| `GameSession` | Scenario/session init payload | Session state lifecycle | Manages live game session |
| `HRLCache` | Keyed HRL request context | Cached HRL artifacts | Caches HRL service outputs |
| `HRLService` | Tactical/strategic request payload | HRL inference response | Serves HRL decisions |
| `TacticalCache` | Keyed tactical request context | Cached tactical artifacts | Caches tactical service outputs |
| `TacticalService` | Tactical request payload | Tactical decision/analysis response | Backend tactical orchestration |
| `SB3AIService` | Encoded state + model context | SB3-selected action | Backend SB3 inference service |
| `GameStartRequest` | API fields for scenario start | Validated request model | API start payload schema |
| `UnitActionsRequest` | API fields for unit actions | Validated request model | API action payload schema |
| `StrategicState` | Strategic schema fields | Pydantic model instance | Strategic API schema |
| `ActivationPayload` | Activation schema fields | Pydantic model instance | Activation API schema |
| `ExplainActivationRequest` | Explain request fields | Pydantic model instance | Explain API input schema |
| `ExplainActivationResponse` | Explain response fields | Pydantic model instance | Explain API output schema |
| `ScenarioSide` | Scenario side fields | Pydantic model instance | Scenario side schema |
| `ScenarioResponse` | Scenario response fields | Pydantic model instance | Scenario API response schema |

## `assault_ai_ui/src/game`

| Class | Input contract | Output contract | Responsibility |
| --- | --- | --- | --- |
| `GameController` | UI state + backend game events | UI-driven game commands/state updates | Frontend gameplay orchestrator |
| `HighlightLayer` | Tile/action highlight requests | Rendered highlight overlays | Visual highlight management |
| `UnitLayer` | Unit state snapshots + sprite assets | Rendered unit layer updates | Unit rendering layer |
| `SoundService` | Audio trigger events | Playback side effects | UI audio orchestration |

## Method-Level Contracts (Critical Classes)

### `RuntimeGameState` (`assault_model/runtime/game_state_runtime.py`)

- **`__init__(base_state: GameState, scenario)`**
  - Input: canonical state + scenario definition.
  - Output: initialized runtime engine with activation tracking and cache version bootstrap.
  - Pre: `base_state.units` available.
  - Post: `active_side` derived from alive sides.
- **`get_available_units(side)`**
  - Input: side identifier.
  - Output: list of non-activated, act-capable units for side.
  - Pre: runtime has synchronized eliminated units.
  - Post: returned units satisfy `_can_unit_act`.
- **`next_activation()`**
  - Input: current runtime activation context.
  - Output: mutates `active_side` (and maybe turn rollover).
  - Pre: `active_side` can be `None`.
  - Post: either next side with available units, or turn increments and activations reset.
- **`turn_has_ended() -> bool`**
  - Input: runtime unit/activation state.
  - Output: `True` when all eligible units already activated.
- **`start_turn()`**
  - Input: current runtime turn state.
  - Output: mutates turn activation context and clears suppression/fallback recoveries.
  - Post: `activated_units` reset; `active_side` recomputed.
- **`end_turn()`**
  - Input: runtime state.
  - Output: delegates to base state end-turn and runs match-end checks.
- **`is_match_over() -> bool`**
  - Output: `base_state.done`.
- **`apply_action(action, combat_result=None, context=None)`**
  - Input: executable action + optional combat/context.
  - Output: action resolution result or wait payload; mutates authoritative state.
  - Pre: action must reference valid actor when unit-bound.
  - Post:
    - state updated through `resolve_action`,
    - `_cache_version` incremented,
    - hex control recalculated,
    - activation advanced,
    - end-of-match re-evaluated,
    - movement/vp events emitted when applicable.

### `MovementRules` (`assault_model/rules/movement_rules.py`)

- **`get_legal_paths(game_state, unit)`** (static)
  - Input: game state, acting unit.
  - Output: `list[MovementPath]` across outcomes:
    - `END_IN_EMPTY_HEX`
    - `END_IN_ENEMY_HEX`
    - `END_IN_FRIENDLY_VEHICLE`
  - Pre:
    - unit has valid position,
    - positive movement allowance.
  - Post:
    - respects terrain/fortification costs and impassability,
    - allows friendly traversal but not illegal final stacking,
    - enemy-occupied endpoint treated as assault destination,
    - supports harsh-terrain one-step exception,
    - caches result by state version/unit signature.

### `OptionExecutor` (`assault_sim/decision/option_executor.py`)

- **`__init__(heuristic_controller, avoid_bad_trades=False, adv_threshold=-0.5)`**
  - Input: heuristic backend + attack filtering knobs.
  - Output: option executor with anti-oscillation and retreat/capture streak state.
- **`execute(state, unit, option, attack_mode=None, strategy=None, objective_tracked_side=None)`**
  - Input: current state, selected unit, L2 option, optional strategy/L3 context.
  - Output: tagged executable action (`rl_l2_option`, `rl_l3_strategy` + capture telemetry fields).
  - Pre: `unit` may be `None` (falls back to `WaitAction("SYSTEM")`).
  - Post:
    - strategy/option coerced by guardrails,
    - CAPTURE path uses deterministic `_capture_priority_action`,
    - retreat loops constrained,
    - returns deep-copied tagged action via `_tag_action`.
- **`_capture_priority_action(state, unit, attack_mode)`**
  - Input: CAPTURE intent context.
  - Output: `(action, TacticalOption)` prioritized for VP entry/progress.
  - Post precedence:
    1) capture emergency -> retreat,
    2) immediate step into uncaptured VP,
    3) staging/progress move evaluation,
    4) gated attacks only when movement is blocked or staging-loop break,
    5) fallback move/hold.
- **`_best_capture_staging_move(state, unit)`**
  - Output: `(move_or_none, reason, dist_before, dist_after)`.
  - Guarantees explicit reason taxonomy (`objective_progress_move`, `objective_staging_move`, `all_moves_increase_distance`, etc.).
- **`_best_attack(attacks, state=None, unit=None)`**
  - Input: candidate attack actions.
  - Output: highest-scoring attack (or safe fallback first attack).
  - Post: composite attacks gated by advantage/expected-damage thresholds unless VP-relevant.

### `TrainingEnv` (`assault_sim/training_env.py`)

- **`__init__(sim_env, env_config_path, rl_side, scenario_override=None, reward_fn=None, seed=None)`**
  - Input: simulator and training config path + RL side.
  - Output: training wrapper with reward and metric counters initialized.
- **`reset()`**
  - Input: optional deterministic seed stream (`base_seed + reset_count`).
  - Output: encoded observation vector.
  - Post:
    - simulator reset,
    - reward function reset,
    - counters reset,
    - memory features emitted (`own_activated_ratio`, `enemy_activated_ratio`, `last_action_type`).
- **`step(action)`**
  - Input: action object (or `None` -> `WaitAction("SYSTEM")`).
  - Output: `(obs, reward, done, info)`.
  - Post:
    - computes action typing and rich telemetry in `info`,
    - tracks damage/kills/attacks by side,
    - computes VP/objective progression fields,
    - computes reward only when RL side is actor,
    - returns encoded next observation with memory features.
- **`_activation_ratios(state)`**
  - Output: `(own_ratio: float, enemy_ratio: float)` in `[0,1]`.

### `Evaluator` (`assault_sim/evaluation/evaluator.py`)

- **`__init__(env, rl_controller, enemy_controller, rl_side, max_steps=300)`**
  - Input: evaluation environment and controller(s).
  - Output: evaluator configured for multi-episode rollout.
- **`run_episode()`**
  - Input: current evaluator context.
  - Output: typed episode result dict (`EvalResult.to_dict()`).
  - Post:
    - executes full loop via `MatchRunner`,
    - collects action/combat events with fallback synthesis,
    - aggregates decision alignment, mission metrics, advanced metrics,
    - computes conversion KPIs (`vp_entry_conversion_rate`, `vp_entry_missed_rate`, etc.).
- **`evaluate(episodes: int)`**
  - Input: number of episodes.
  - Output: list of episode result dicts.
  - Post: continues on per-episode failures with logged errors.
- **`_can_enter_uncaptured_vp_now(state, unit) -> bool`**
  - Input: state + unit.
  - Output: whether at least one legal movement action can enter uncaptured VP now.
- **`_ownership_for_side(state, side)`**
  - Output: robust ownership mapping across normalized side keys.

### `ActionCatalog` (`assault_model/actions/action_catalog.py`)

- **`__init__(game_state, unit, terrain_config)`**
  - Input: authoritative game state, active unit, terrain config (required).
  - Output: catalog instance bound to one state/unit context.
  - Pre: `terrain_config` must be provided.
  - Post: raises `ValueError` if terrain config is missing.
- **`actions()`**
  - Input: current bound state/unit snapshot.
  - Output: list of executable actions (movement, ranged, composites, wait).
  - Pre:
    - `unit is None` => `[WaitAction("SYSTEM")]`,
    - dead unit => `[]`.
  - Post:
    - includes movement actions derived from `MovementRules.get_legal_paths`,
    - includes assault actions for enemy-end movement outcomes,
    - includes ranged actions from `_ranged_fire_actions`,
    - includes composite actions from `_move_fire_actions`,
    - always appends `WaitAction(unit_id)` for alive unit,
    - caches by `(state_version + unit tactical snapshot)` and returns cached list when valid.
- **`_ranged_fire_actions(active)`**
  - Input: active unit.
  - Output: list of `RangedDirectAttack` / `RangedIndirectAttack`.
  - Pre:
    - unit must be able to fire,
    - target must be alive enemy and spotted,
    - target must be in weapon range.
  - Post:
    - direct fire requires LOS check,
    - indirect fire bypasses direct LOS gate,
    - action compatibility metadata set (`target_id`, `attack_mode`).
- **`_in_weapon_range(attacker, target) -> bool`**
  - Input: attacker/target units with positions.
  - Output: `True` if any attack table band matches distance.
- **`_has_line_of_sight(attacker, target) -> bool`**
  - Input: attacker/target + map/terrain context.
  - Output: LOS boolean via `has_line_of_sight`.
- **`_half_move_actions(movement_paths, unit)`**
  - Input: legal movement outcomes + unit.
  - Output: deduplicated half-move `MoveAction` list.
  - Post:
    - only empty-hex outcomes,
    - path length <= half move limit,
    - excludes no-op and duplicate destination moves.
- **`_ranged_fire_actions_from_position(active, position)`**
  - Input: unit + temporary position.
  - Output: ranged actions as if unit were at that position.
  - Post: restores original unit position after computation.
- **`_move_fire_actions(active, movement_paths)`**
  - Input: active unit + legal movement paths.
  - Output: list of `FireThenMoveAction` and `MoveThenFireAction`.
  - Pre:
    - unit can fire,
    - unit is not artillery-like,
    - half moves available.
  - Post:
    - creates composites in both orders,
    - de-duplicates by target+destination key,
    - evaluates post-move firing opportunities for move-then-fire branch.

## Completion criteria

This page is considered validated when:

- every class row has verified method-level signatures,
- every responsibility line is confirmed against implementation,
- high-impact classes (`RuntimeGameState`, `ActionCatalog`, `MovementRules`, `OptionExecutor`, `TrainingEnv`, `Evaluator`) have explicit method-level I/O contract blocks.
