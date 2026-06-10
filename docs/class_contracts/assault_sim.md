# assault_sim Class Contracts

## config and contracts

`SimConfig`, `RewardConfig`, `MovementTacticalConfig`, `PPOConfig`, `ScenarioScheduleEntry`, `TrainConfig`, `TrajectoryStep`, `RolloutBatch`, `EvalResult`

- **Input contract**: simulation/training config fields and typed rollout data.
- **Output contract**: validated config/data records used by training/eval.

## decision, envs, engine

`ActionDecisionTrace`, `ActionBridge`, `DecisionEngine`, `DecisionEngineController`, `HRLController`, `OptionExecutor`, `RLvsHeuristicController`, `SideController`, `_GymActionController`, `GymAssaultEnv`, `ActivationManager`, `MatchRunner`, `MetricsTracker`

- **Input contract**: state + policy intent + legal action context.
- **Output contract**: executable actions and step-level engine transitions.
- **Responsibility**: tactical decisioning and environment orchestration.

## evaluation

`AdvancedMetrics`, `Evaluator`, `EvalDashboard`, `EvaluationLogger`, `ResultsAnalyzer`, `SB3EvalController`, `ExperimentRow`, `EpisodeRow`, `DecisionRow`, `OutcomeRow`

- **Input contract**: episode traces, step info, and controller outputs.
- **Output contract**: per-episode and aggregate KPI reports.

## heuristics / knowledge / policies

`HeuristicBase`, `BasicHeuristic`, `HeuristicTracer`, `MoveToVictoryPointHeuristic`, `NoOpHeuristic`, `Phase01_InitialContactPolicy`, `TacticalPathHeuristic`, `Target`, `VictoryPointBrick`, `KnowledgeBrick`, `KnowledgeArea`, `EnemyProximityBrick`, `PolicyRegistry`

- **Input contract**: tactical features and board/unit context.
- **Output contract**: scoring/selection hints or deterministic heuristic actions.

## rewards

`BaseReward`, `ProgressiveReward`, `ShapedReward`, `VPDifferenceReward`, `CombatReward`, `DecisionReward`, `PositioningReward`, `SurvivalReward`, `VPReward`

- **Input contract**: transition tuple (`state`, `action`, `next_state`, `info`, `done`).
- **Output contract**: scalar reward components/composed reward.

## rl

`PolicyNet`, `ReplayBuffer`, `OptionPolicy`, `RLPolicyController`, `RandomPolicyController`, `SideAwareController`, `TacticalOption`, `StrategicIntent`

- **Input contract**: encoded observations, masks, policy/controller context.
- **Output contract**: logits/actions/controller decisions.

## debug + root

`CombatRenderer`, `ConsoleListener`, `ConsoleObserver`, `DebugConfig`, `DeploymentRenderer`, `EventBus`, `MapRenderer`, `MovementRenderer`, `Replay`, `ReplayObserver`, `ReplayWriter`, `TurnBuffer`, `UnitFormatter`, `SimEnv`, `TrainingEnv`

- **Input contract**: runtime events and snapshots.
- **Output contract**: debug artifacts, replay persistence, env transitions.
