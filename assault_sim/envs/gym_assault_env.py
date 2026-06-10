from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover
    import gym as gym  # type: ignore
    from gym import spaces  # type: ignore

from assault_model.actions.status import WaitAction
from assault_sim.config.ppo_config import PPOConfig
from assault_sim.decision.action_bridge import ActionBridge
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.engine.env_factory import make_env
from assault_sim.engine.match_runner import MatchRunner
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.rewards.shaped_reward import ShapedReward


class _GymActionController:
    """
    Controller used by GymAssaultEnv.
    - RL side consumes external action set by env.step(action)
    - Enemy side keeps heuristic policy
    """

    def __init__(self, rl_side: str, sim_env):
        self.rl_side = rl_side
        self.sim_env = sim_env
        self.heuristic = TacticalPathHeuristic()
        self.executor = OptionExecutor(self.heuristic, avoid_bad_trades=False, adv_threshold=-0.5)
        self.action_bridge = ActionBridge()
        self.pending_action: tuple[int, ...] | None = None

        self.current_option = None
        self.current_option_sampled = None
        self.current_option_resolved = None
        self.current_attack_mode = 0
        self.last_decision_trace = None
        self.last_logp = None
        self.last_value = None
        self.current_strategy = None
        self.training_mode = False
        self._locked_strategy: StrategicIntent | None = None
        self._locked_strategy_turn: int | None = None

    def reset(self):
        self.pending_action = None
        self.current_option = None
        self.current_option_sampled = None
        self.current_option_resolved = None
        self.current_attack_mode = 0
        self.last_decision_trace = None
        self._locked_strategy = None
        self._locked_strategy_turn = None

    def set_action(self, action: tuple[int, ...]):
        self.pending_action = action

    def _candidate_units_for_side(self, state, side, blocked_units):
        blocked = blocked_units or set()
        side_norm = str(side).upper()
        units = [
            u for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and str(getattr(u, "side", "")).upper() == side_norm
            and getattr(u, "unit_id", None) not in blocked
        ]
        # Stable ordering: fixed by unit_id (US_1, US_2, ...)
        return sorted(units, key=lambda u: str(getattr(u, "unit_id", "")))

    def select_best_unit(self, side, state, blocked_units):
        # Let enemy side keep default selection behavior.
        if str(side).upper() != str(self.rl_side).upper():
            return None
        if self.pending_action is None:
            return None
        units = self._candidate_units_for_side(state, side, blocked_units)
        if not units:
            return None
        slot = 0
        if len(self.pending_action) >= 4:
            try:
                slot = int(self.pending_action[3])
            except Exception:
                return None
        if slot < 0:
            return None
        idx = slot % len(units)
        return units[idx]

    def _decode_action(self) -> tuple[StrategicIntent, TacticalOption, int, int]:
        if self.pending_action is None:
            return StrategicIntent.CAPTURE, TacticalOption.HOLD, 0, 0
        strategy_idx = int(self.pending_action[0])
        option_idx = int(self.pending_action[1])
        attack_mode = int(self.pending_action[2])
        unit_slot = int(self.pending_action[3]) if len(self.pending_action) >= 4 else 0
        strategy = StrategicIntent(strategy_idx)
        option = TacticalOption(option_idx)
        return strategy, option, attack_mode, unit_slot

    def _objective_tracked_side(self) -> str | None:
        outcomes = getattr(getattr(self.sim_env, "scenario", None), "victory_outcomes", None) or {}
        metric = str(outcomes.get("metric", "")).strip()
        timing = str(outcomes.get("timing", "")).strip()
        tracked = str(outcomes.get("tracked_side", "")).strip().upper()
        if metric == "objectives_captured" and timing == "end_of_last_turn" and tracked:
            return tracked
        return None

    def _option_from_action_tag(self, action, fallback: TacticalOption) -> TacticalOption:
        tagged = str(getattr(action, "rl_l2_option", "") or "").strip().upper()
        if not tagged:
            return fallback
        try:
            return TacticalOption[tagged]
        except KeyError:
            return fallback

    def act(self, state, side, unit, obs):
        if side == self.rl_side:
            sampled_strategy, sampled_option, attack_mode, _unit_slot = self._decode_action()
            turn_now = int(getattr(state, "turn", 0))
            if self._locked_strategy is None or self._locked_strategy_turn != turn_now:
                self._locked_strategy = sampled_strategy
                self._locked_strategy_turn = turn_now
            effective_strategy = self._locked_strategy
            resolved_option = sampled_option

            action = self.executor.execute(
                state=state,
                unit=unit,
                option=resolved_option,
                attack_mode=attack_mode,
                strategy=effective_strategy,
                objective_tracked_side=self._objective_tracked_side(),
            )
            if action is None:
                action = WaitAction(unit.unit_id)

            resolved_from_action = self._option_from_action_tag(action, resolved_option)
            executed_option = self.action_bridge.infer_executed_option(action, resolved_from_action)
            self.current_option_sampled = sampled_option
            self.current_option_resolved = resolved_from_action
            self.current_option = executed_option
            self.current_attack_mode = attack_mode if executed_option == TacticalOption.ATTACK else 0
            self.current_strategy = type("Strategy", (), {"name": effective_strategy.name})()
            self.last_decision_trace = self.action_bridge.build_trace(
                sampled_option=sampled_option,
                resolved_option=resolved_from_action,
                executed_option=executed_option,
                strategy_name=effective_strategy.name,
            )
            self.pending_action = None

            action.unit_id = unit.unit_id
            self.sim_env.runtime.activated_units.add(unit.unit_id)
            return action

        # Enemy heuristic behavior.
        for opt in (
            TacticalOption.ATTACK,
            TacticalOption.FLANK,
            TacticalOption.ADVANCE,
            TacticalOption.RETREAT,
            TacticalOption.HOLD,
        ):
            action = self.heuristic.choose_action(state, unit, opt)
            if action is not None:
                action.unit_id = unit.unit_id
                self.sim_env.runtime.activated_units.add(unit.unit_id)
                return action

        action = WaitAction(unit.unit_id)
        action.unit_id = unit.unit_id
        self.sim_env.runtime.activated_units.add(unit.unit_id)
        return action


class GymAssaultEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        sim_config_path: Path | None = None,
        env_config_path: Path | None = None,
        scenario: str | None = None,
        rl_side: str | None = None,
        seed: int | None = None,
        max_decisions: int = 400,
        zero_damage_penalty: float = 0.6,
        extra_good_trade_bonus: float = 0.2,
    ):
        super().__init__()

        repo_root = Path(__file__).resolve().parents[2]
        self.sim_config_path = sim_config_path or (repo_root / "assault_sim" / "config" / "sim_config.yaml")
        self.env_config_path = env_config_path or (repo_root / "assault_sim" / "config" / "env_config.json")
        self.scenario = scenario or PPOConfig.SCENARIO
        self.rl_side = rl_side or PPOConfig.RL_SIDE
        self.base_seed = seed if seed is not None else PPOConfig.SEED
        self.max_decisions = max_decisions
        self.zero_damage_penalty = float(zero_damage_penalty)
        self.extra_good_trade_bonus = float(extra_good_trade_bonus)

        self._decision_count = 0

        self._build_runtime(seed=self.base_seed)
        obs = self._runner.reset()
        self._last_obs = np.asarray(obs, dtype=np.float32)
        obs_dim = int(self._last_obs.shape[0])

        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_dim,),
            dtype=np.float32,
        )
        # [L3 strategy, L2 option, attack_mode, unit_slot]
        self.max_unit_slots = max(1, len(getattr(self._train_env.sim.game_state, "units", []) or []))
        self.action_space = spaces.MultiDiscrete([len(StrategicIntent), len(TacticalOption), 2, self.max_unit_slots])

    def _build_runtime(self, seed: int):
        self._train_env = make_env(
            config_path=self.sim_config_path,
            env_config_path=self.env_config_path,
            rl_side=self.rl_side,
            scenario=self.scenario,
            reward_fn=ShapedReward(
                rl_side=self.rl_side,
                zero_damage_penalty=self.zero_damage_penalty,
                extra_good_trade_bonus=self.extra_good_trade_bonus,
            ),
            seed=seed,
        )
        # MatchRunner/ActivationManager require an initialized game_state.
        self._train_env.reset()
        self._controller = _GymActionController(self.rl_side, self._train_env.sim)
        self._runner = MatchRunner(self._train_env, controller=self._controller)

    def _decision_alignment_info(self) -> dict[str, Any]:
        trace = self._controller.last_decision_trace
        if trace is None:
            return {}
        return {
            "trace_schema_version": trace.schema_version,
            "sampled_option": trace.sampled_option,
            "resolved_option": trace.resolved_option,
            "executed_option": trace.executed_option,
            "forced": bool(trace.was_forced),
        }

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        effective_seed = self.base_seed if seed is None else int(seed)
        self._build_runtime(seed=effective_seed)
        self._controller.reset()
        self._decision_count = 0

        obs = self._runner.reset()
        self._last_obs = np.asarray(obs, dtype=np.float32)
        info = {
            "rl_side": self.rl_side,
            "scenario": self.scenario,
            "decision_count": self._decision_count,
        }
        return self._last_obs, info

    def step(self, action):
        strategy_idx = int(action[0])
        option_idx = int(action[1])
        attack_mode = int(action[2])
        unit_slot = int(action[3]) if len(action) >= 4 else 0
        self._controller.set_action((strategy_idx, option_idx, attack_mode, unit_slot))

        total_reward = 0.0
        terminated = False
        truncated = False
        step_info: dict[str, Any] = {}

        rl_consumed = False
        obs = self._last_obs
        # advance match until one RL activation is consumed or episode ends
        while not terminated and not rl_consumed:
            step = self._runner.step(self._controller, obs)
            obs = np.asarray(step["obs"], dtype=np.float32)
            total_reward += float(step.get("reward", 0.0))
            terminated = bool(step.get("done", False))
            step_info = dict(step.get("info", {}) or {})
            rl_consumed = step.get("side") == self.rl_side

        self._last_obs = obs
        self._decision_count += 1
        if self._decision_count >= self.max_decisions and not terminated:
            truncated = True

        info = {
            **step_info,
            **self._decision_alignment_info(),
            "decision_count": self._decision_count,
        }
        return obs, total_reward, terminated, truncated, info

