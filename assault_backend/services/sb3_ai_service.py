from __future__ import annotations

from pathlib import Path
import numpy as np
import os

from assault_model.actions.status import WaitAction
from assault_model.actions.action_catalog import ActionCatalog
from assault_sim.config.ppo_config import PPOConfig
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.state_encoder import encode_state
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.strategic_intents import StrategicIntent


class SB3AIService:
    """
    Backend inference wrapper to drive /api/game/ai-turn with SB3 PPO.
    """

    def __init__(self, model_path: Path | None = None):
        try:
            from stable_baselines3 import PPO
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "stable-baselines3 is required for SB3AIService"
            ) from exc

        self.default_rl_side = PPOConfig.RL_SIDE
        self.heuristic = TacticalPathHeuristic()
        self.executor = OptionExecutor(self.heuristic, avoid_bad_trades=False, adv_threshold=-0.5)
        self.repo_root = Path(__file__).resolve().parents[2]
        self._explicit_model_path = model_path
        self._models_by_side: dict[str, object] = {}
        self._model_path_by_side: dict[str, Path] = {}
        self._strategy_lock_by_side: dict[str, tuple[int, StrategicIntent]] = {}
        self._vecnorm_by_side: dict[str, object] = {}

        any_default = self._resolve_model_path_for_side(self.default_rl_side)
        if any_default is None:
            raise FileNotFoundError(
                "No SB3 checkpoint found. Expected side-specific checkpoints, e.g.: "
                f"{self.repo_root / 'models' / 'sb3_latest_<SIDE>.zip'} or "
                f"{self.repo_root / 'models' / 'sb3_best_<SIDE>' / 'best_model.zip'}"
            )
        # Backward-compatible attribute used by backend startup logs.
        self.model_path = any_default

    def _resolve_model_path_for_side(self, side: str | None) -> Path | None:
        normalized_side = (side or "").strip().upper()
        candidates = [
            self._explicit_model_path,
            self.repo_root / "models" / f"sb3_latest_{normalized_side}.zip" if normalized_side else None,
            self.repo_root / "models" / f"sb3_best_{normalized_side}" / "best_model.zip" if normalized_side else None,
        ]
        return next((p for p in candidates if p is not None and p.exists()), None)

    def _get_model_for_side(self, side: str | None):
        normalized_side = (side or "").strip().upper()
        if normalized_side in self._models_by_side:
            return self._models_by_side[normalized_side]
        chosen = self._resolve_model_path_for_side(normalized_side)
        if chosen is None:
            return None
        try:
            from stable_baselines3 import PPO
            model = PPO.load(str(chosen), device="cpu")
        except Exception:
            return None
        self._models_by_side[normalized_side] = model
        self._model_path_by_side[normalized_side] = chosen
        return model

    def can_control_side(self, side: str | None) -> bool:
        return self._get_model_for_side(side) is not None

    def _resolve_vecnormalize_path_for_side(self, side: str | None) -> Path | None:
        normalized_side = (side or "").strip().upper()
        candidates = [
            self.repo_root / "models" / f"sb3_vecnormalize_{normalized_side}.pkl" if normalized_side else None,
            self.repo_root / "models" / "sb3_vecnormalize.pkl",
        ]
        return next((p for p in candidates if p is not None and p.exists()), None)

    def _build_obs_normalizer_for_side(self, side: str | None):
        normalized_side = (side or "").strip().upper()
        if normalized_side in self._vecnorm_by_side:
            return self._vecnorm_by_side[normalized_side]
        vecnorm_path = self._resolve_vecnormalize_path_for_side(normalized_side)
        if vecnorm_path is None:
            self._vecnorm_by_side[normalized_side] = None
            return None
        try:
            from stable_baselines3.common.monitor import Monitor
            from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
            from assault_sim.envs.gym_assault_env import GymAssaultEnv
        except Exception:
            self._vecnorm_by_side[normalized_side] = None
            return None
        try:
            # Seed is only required to build a shape-compatible env for loading stats.
            def _make_env():
                return Monitor(
                    GymAssaultEnv(
                        scenario=getattr(PPOConfig, "SCENARIO", None),
                        rl_side=normalized_side or PPOConfig.RL_SIDE,
                        seed=int(os.getenv("ASSAULT_UI_SB3_SEED", "42")),
                    )
                )
            norm_env = DummyVecEnv([_make_env])
            vecnorm = VecNormalize.load(str(vecnorm_path), norm_env)
            vecnorm.training = False
            vecnorm.norm_reward = False
            self._vecnorm_by_side[normalized_side] = vecnorm
            return vecnorm
        except Exception:
            self._vecnorm_by_side[normalized_side] = None
            return None

    def _normalize_obs(self, side: str | None, obs: np.ndarray) -> np.ndarray:
        vecnorm = self._build_obs_normalizer_for_side(side)
        if vecnorm is None:
            return obs
        arr = np.asarray(obs, dtype=np.float32)
        return vecnorm.normalize_obs(arr.reshape(1, -1))[0]

    def _objective_tracked_side(self, env) -> str | None:
        outcomes = getattr(getattr(env, "scenario", None), "victory_outcomes", None) or {}
        metric = str(outcomes.get("metric", "")).strip()
        timing = str(outcomes.get("timing", "")).strip()
        tracked = str(outcomes.get("tracked_side", "")).strip().upper()
        if metric == "objectives_captured" and timing == "end_of_last_turn" and tracked:
            return tracked
        return None

    def _fmt_ax(self, q, r) -> str:
        if q is None or r is None:
            return "[]"
        try:
            return f"[{chr(65 + int(q))}{int(r) + 1}]"
        except Exception:
            return "[]"

    def _ax_from_action_id(self, action_id: str) -> str:
        try:
            parts = str(action_id or "").split(":")
            if len(parts) < 4:
                return "[]"
            q = int(parts[-2])
            r = int(parts[-1])
            return self._fmt_ax(q, r)
        except Exception:
            return "[]"

    def _is_non_displacement_move(self, action, unit) -> bool:
        if action is None or unit is None:
            return False
        unit_pos = getattr(unit, "position", None)
        if unit_pos is None:
            return False
        path = getattr(action, "move_path", None) or getattr(action, "path", None)
        if not path:
            return False
        end = path[-1]
        if end is None:
            return False
        return (
            getattr(end, "q", None) == getattr(unit_pos, "q", None)
            and getattr(end, "r", None) == getattr(unit_pos, "r", None)
        )

    def _catalog_fallback_for_unit(self, state, unit):
        try:
            legal_actions = ActionCatalog(
                state,
                unit,
                terrain_config=state.game_map.terrain_config,
            ).actions()
        except Exception:
            return WaitAction(getattr(unit, "unit_id", "SYSTEM"))
        if not legal_actions:
            return WaitAction(getattr(unit, "unit_id", "SYSTEM"))

        def _is_uncaptured_vp_hex_for_side(end_pos) -> bool:
            if end_pos is None:
                return False
            side = getattr(unit, "side", None)
            if state is None or not side:
                return False
            coords = (getattr(end_pos, "q", None), getattr(end_pos, "r", None))
            if coords[0] is None or coords[1] is None:
                return False
            points = getattr(getattr(state, "victory", None), "points", []) or []
            vp_coords = {tuple(getattr(vp, "hex_coords", (None, None))) for vp in points}
            if coords not in vp_coords:
                return False
            side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
            own_ownership = side_to_ownership.get(str(side).upper())
            hs = getattr(state, "hex_states", {}).get(coords)
            if hs is None:
                return False
            return getattr(hs, "ownership", None) != own_ownership

        def _score(a):
            aid = str(getattr(a, "action_id", "") or "").upper()
            name = str(getattr(a, "__class__", type("X", (), {})).__name__ or "").upper()
            is_attack = ("ATTACK" in name) or ("FIRE" in name) or ("RANGED" in aid)
            path = getattr(a, "move_path", None) or getattr(a, "path", None)
            end = path[-1] if path else None
            if path and _is_uncaptured_vp_hex_for_side(end):
                # Prioritize immediate VP capture if currently legal.
                return (4, 0)
            if is_attack:
                return (3, 0)
            if self._is_non_displacement_move(a, unit):
                return (0, -999)
            if aid.startswith("WAIT:") or "WAIT" in name:
                return (1, 0)
            return (2, 0)

        return max(legal_actions, key=_score)

    def choose_unit_and_action(self, env, side: str | None, planner_context=None):
        rl_side = (side or "").upper()
        state = env.game_state
        model = self._get_model_for_side(rl_side)
        if model is None:
            return None, None, "WAIT_NO_MODEL"
        candidates = sorted(
            [
                u for u in getattr(state, "units", [])
                if getattr(u, "alive", False)
                and str(getattr(u, "side", "")).upper() == rl_side
                and getattr(u, "unit_id", None) not in getattr(env.runtime, "activated_units", set())
            ],
            key=lambda u: str(getattr(u, "unit_id", "")),
        )
        if not candidates:
            return None, WaitAction("SYSTEM"), "WAIT_NO_CANDIDATES"
        scenario = getattr(env, "scenario", None)
        max_turns = getattr(scenario, "max_turns", None)
        obs = encode_state(state, unit=None, rl_side=rl_side, max_turns=max_turns, scenario=scenario)
        obs = self._normalize_obs(rl_side, obs)
        action_pair, _ = model.predict(obs, deterministic=True)
        action_vec = np.asarray(action_pair).reshape(-1)
        if action_vec.size not in (3, 4):
            raise RuntimeError(
                f"Expected action [strategy, option, attack_mode(, unit_slot)], got shape={action_vec.shape}"
            )
        strategy_idx = int(action_vec[0])
        option_idx = int(action_vec[1])
        attack_mode = int(action_vec[2])
        unit_slot = int(action_vec[3]) if action_vec.size >= 4 else 0
        unit = candidates[unit_slot % len(candidates)]

        sampled_strategy = StrategicIntent(strategy_idx)
        turn_now = int(getattr(state, "turn", 0))
        prev = self._strategy_lock_by_side.get(rl_side)
        if prev is None or prev[0] != turn_now:
            self._strategy_lock_by_side[rl_side] = (turn_now, sampled_strategy)
            strategy = sampled_strategy
        else:
            strategy = prev[1]
        option = TacticalOption(option_idx)
        option_name = option.name
        planner_stage = str(getattr(planner_context, "stage", "") or "").upper()
        if planner_stage == "STEP_IN":
            strategy = StrategicIntent.CAPTURE
            if option in (TacticalOption.HOLD, TacticalOption.RETREAT):
                option = TacticalOption.ADVANCE
                option_name = option.name
        elif planner_stage == "HOLD" and option == TacticalOption.RETREAT:
            option = TacticalOption.HOLD
            option_name = option.name
        action = self.executor.execute(
            state=state,
            unit=unit,
            option=option,
            attack_mode=attack_mode,
            strategy=strategy,
            objective_tracked_side=self._objective_tracked_side(env),
            planner_context=planner_context,
        )
        proposed_action_id = str(getattr(action, "action_id", "") or "")
        final_reason = "ok"
        if action is None:
            action = WaitAction(unit.unit_id)
            final_reason = "executor_returned_none"
        else:
            # SB3 path must still return a catalog-valid action for current state.
            try:
                legal_actions = ActionCatalog(
                    state,
                    unit,
                    terrain_config=state.game_map.terrain_config,
                ).actions()
                legal_ids = {str(getattr(a, "action_id", "") or "") for a in legal_actions}
                aid = str(getattr(action, "action_id", "") or "")
                if not aid or aid not in legal_ids or self._is_non_displacement_move(action, unit):
                    action = self._catalog_fallback_for_unit(state, unit)
                    option_name = "SB3_CATALOG_FALLBACK"
                    if not aid:
                        final_reason = "empty_action_id"
                    elif aid not in legal_ids:
                        final_reason = "not_in_catalog"
                    else:
                        final_reason = "non_displacement"
            except Exception:
                action = self._catalog_fallback_for_unit(state, unit)
                option_name = "SB3_CATALOG_FALLBACK"
                final_reason = "catalog_validation_error"
        action.unit_id = unit.unit_id
        final_action_id = str(getattr(action, "action_id", "") or "")
        if final_action_id != proposed_action_id or option_name == "SB3_CATALOG_FALLBACK" or final_reason != "ok":
            tag = "\x1b[35m[SB3 DEBUG]\x1b[0m"
            print(
                f"{tag}"
                f" side={rl_side}"
                f" unit={getattr(unit, 'unit_id', None)}"
                f" proposed={proposed_action_id or 'None'}"
                f" proposed_ax={self._ax_from_action_id(proposed_action_id)}"
                f" final={final_action_id or 'None'}"
                f" final_ax={self._ax_from_action_id(final_action_id)}"
                f" mode={option_name}"
                f" reason={final_reason}"
                f" planner_stage={str(getattr(planner_context, 'stage', '') or '')}"
            )
        return unit, action, option_name

    def choose_action(self, env, unit, planner_context=None):
        rl_side = unit.side
        state = env.game_state
        scenario = getattr(env, "scenario", None)
        max_turns = getattr(scenario, "max_turns", None)
        model = self._get_model_for_side(rl_side)
        if model is None:
            action = WaitAction(unit.unit_id)
            action.unit_id = unit.unit_id
            return action, "WAIT_NO_MODEL"
        obs = encode_state(state, unit=unit, rl_side=rl_side, max_turns=max_turns, scenario=scenario)
        obs = self._normalize_obs(rl_side, obs)
        action_pair, _ = model.predict(obs, deterministic=True)
        action_vec = np.asarray(action_pair).reshape(-1)
        if action_vec.size not in (3, 4):
            raise RuntimeError(
                f"Expected action [strategy, option, attack_mode(, unit_slot)], got shape={action_vec.shape}"
            )
        strategy_idx = int(action_vec[0])
        option_idx = int(action_vec[1])
        attack_mode = int(action_vec[2])

        sampled_strategy = StrategicIntent(strategy_idx)
        turn_now = int(getattr(state, "turn", 0))
        prev = self._strategy_lock_by_side.get(rl_side)
        if prev is None or prev[0] != turn_now:
            self._strategy_lock_by_side[rl_side] = (turn_now, sampled_strategy)
            strategy = sampled_strategy
        else:
            strategy = prev[1]
        option = TacticalOption(option_idx)

        action = self.executor.execute(
            state=state,
            unit=unit,
            option=option,
            attack_mode=attack_mode,
            strategy=strategy,
            objective_tracked_side=self._objective_tracked_side(env),
            planner_context=planner_context,
        )
        if action is None:
            action = WaitAction(unit.unit_id)
        action.unit_id = unit.unit_id
        return action, option.name

