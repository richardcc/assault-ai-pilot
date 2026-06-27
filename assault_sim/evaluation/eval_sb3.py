from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import json
import os
import numpy as np

from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import safe_hex_distance
from assault_sim.config.train_config import load_train_config
from assault_sim.config.ppo_config import PPOConfig
from assault_sim.decision.action_bridge import ActionBridge
from assault_sim.decision.action_finalizer import catalog_priority_action, finalize_action
from assault_sim.decision.mission_planner import MissionPlanner
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.engine.env_factory import make_env
from assault_sim.evaluation.eval_dashboard import EvalDashboard
from assault_sim.evaluation.evaluator import Evaluator
from assault_sim.evaluation.results_analyzer import ResultsAnalyzer
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.rl.state_encoder import encode_state
from assault_sim.rewards.shaped_reward import ShapedReward


def _ansi(text: str, color: str | None = None, bold: bool = False) -> str:
    if os.getenv("NO_COLOR") is not None:
        return text
    palette = {
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "magenta": "35",
        "cyan": "36",
        "gray": "90",
    }
    codes = []
    if bold:
        codes.append("1")
    if color in palette:
        codes.append(palette[color])
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


class SB3EvalController:
    def __init__(
        self,
        model,
        rl_side: str,
        sim_env,
        obs_normalizer=None,
        capture_guardrails_enabled: bool = True,
        diagnostic_force_capture_only: bool = False,
        diagnostic_min_overrides: bool = False,
        finalizer_override_profile: str = "strict",
    ):
        self.model = model
        self.rl_side = rl_side
        self.sim_env = sim_env
        self.obs_normalizer = obs_normalizer
        self.heuristic = TacticalPathHeuristic()
        self.executor = OptionExecutor(
            self.heuristic,
            avoid_bad_trades=False,
            adv_threshold=-0.5,
            capture_guardrails_enabled=capture_guardrails_enabled,
            diagnostic_force_capture_only=diagnostic_force_capture_only,
        )
        self.diagnostic_min_overrides = bool(diagnostic_min_overrides)
        profile = str(finalizer_override_profile or "strict").strip().lower()
        self.finalizer_override_profile = profile if profile in {"strict", "soft"} else "strict"
        self.action_bridge = ActionBridge()
        self.mission_planner = MissionPlanner()

        self.current_option = None
        self.current_option_sampled = None
        self.current_option_resolved = None
        self.current_attack_mode = 0
        self.last_decision_trace = None
        self.current_strategy = None
        self.training_mode = False
        self._strategy_stub = type("SB3Strategy", (), {})
        self._cached_action_vec_by_turn = {}
        # R4 skeleton: step-in mask telemetry for legal VP-entry opportunities.
        self.current_stepin_legal = False
        self.current_stepin_forced_option = False
        self.finalizer_debug = str(os.getenv("ASSAULT_DEBUG_FINALIZER", "0")).strip().lower() in {"1", "true", "yes", "on"}
        self._finalizer_debug_budget = 40

    def reset(self):
        self.current_option = None
        self.current_option_sampled = None
        self.current_option_resolved = None
        self.current_attack_mode = 0
        self.last_decision_trace = None
        self._cached_action_vec_by_turn = {}
        self.current_stepin_legal = False
        self.current_stepin_forced_option = False
        self.mission_planner.reset()

    def _predict_action_vec(self, state, obs=None):
        model_obs = obs
        if model_obs is None:
            model_obs = encode_state(
                state,
                unit=None,
                rl_side=self.rl_side,
                max_turns=getattr(getattr(self.sim_env, "scenario", None), "max_turns", None),
                scenario=getattr(self.sim_env, "scenario", None),
            )
        if self.obs_normalizer is not None:
            model_obs = self.obs_normalizer(model_obs)
        action_pair, _ = self.model.predict(model_obs, deterministic=True)
        return np.asarray(action_pair).reshape(-1)

    def _candidate_units_for_side(self, side, state, blocked_units):
        blocked = blocked_units or set()
        side_norm = str(side).upper()
        units = [
            u for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and str(getattr(u, "side", "")).upper() == side_norm
            and getattr(u, "unit_id", None) not in blocked
        ]
        return sorted(units, key=lambda u: str(getattr(u, "unit_id", "")))

    def _capture_unit_sort_key(self, state, unit):
        try:
            can_stepin = self.executor._best_step_into_uncaptured_vp(state, unit) is not None
        except Exception:
            can_stepin = False
        try:
            nearest_vp_d = self.executor._nearest_uncaptured_vp_dist(state, unit)
        except Exception:
            nearest_vp_d = None
        dist = float(nearest_vp_d) if nearest_vp_d is not None else 999.0
        uid = str(getattr(unit, "unit_id", ""))
        return (0 if can_stepin else 1, dist, uid)

    def _defense_intercept_unit(self, state, candidates):
        """
        Local CAPTURE-only defense selector:
        when an owned VP is threatened (enemy at distance <=1), pick the closest
        available unit to that VP for one activation (no global strategy override).
        """
        try:
            threatened = self.executor._threatened_owned_vp_hexes(state, self.rl_side, threat_radius=1)
        except Exception:
            threatened = set()
        if not threatened or not candidates:
            return None
        best = None
        best_key = None
        for u in candidates:
            pos = getattr(u, "position", None)
            if pos is None:
                continue
            d_threat = min(
                safe_hex_distance(pos, vp)
                for vp in threatened
            )
            key = (d_threat, str(getattr(u, "unit_id", "")))
            if best_key is None or key < best_key:
                best_key = key
                best = u
        if best is not None and best_key is not None and best_key[0] <= 3:
            return best
        return None

    def select_best_unit(self, side, state, blocked_units):
        if str(side).upper() != str(self.rl_side).upper():
            return None
        candidates = self._candidate_units_for_side(side, state, blocked_units)
        if not candidates:
            return None
        action_vec = self._predict_action_vec(state, obs=None)
        turn_now = int(getattr(state, "turn", 0))
        self._cached_action_vec_by_turn[turn_now] = action_vec
        if action_vec.size < 4:
            return None
        unit_slot = int(action_vec[3])
        strategy = None
        if action_vec.size >= 1:
            try:
                strategy = StrategicIntent(int(action_vec[0]))
            except Exception:
                strategy = None
        if strategy == StrategicIntent.CAPTURE:
            intercept = self._defense_intercept_unit(state, candidates)
            if intercept is not None:
                return intercept
            ranked = sorted(candidates, key=lambda u: self._capture_unit_sort_key(state, u))
            top_k = min(3, len(ranked))
            return ranked[unit_slot % top_k]
        return candidates[unit_slot % len(candidates)]

    def _enemy_action(self, state, unit):
        for opt in (
            TacticalOption.ATTACK,
            TacticalOption.FLANK,
            TacticalOption.ADVANCE,
            TacticalOption.RETREAT,
            TacticalOption.HOLD,
        ):
            action = self.heuristic.choose_action(state, unit, opt)
            if action is not None:
                return action
        return WaitAction(unit.unit_id)

    def _objective_tracked_side(self) -> str | None:
        outcomes = getattr(getattr(self.sim_env, "scenario", None), "victory_outcomes", None) or {}
        metric = str(outcomes.get("metric", "")).strip()
        timing = str(outcomes.get("timing", "")).strip()
        tracked = str(outcomes.get("tracked_side", "")).strip().upper()
        if metric == "objectives_captured" and timing == "end_of_last_turn" and tracked:
            return tracked
        return None

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

    def _is_uncaptured_vp_hex_for_side(self, state, side: str | None, end_pos) -> bool:
        if state is None or not side or end_pos is None:
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

    def _catalog_priority_action(self, state, unit):
        return catalog_priority_action(
            state,
            unit,
            is_non_displacement_move=self._is_non_displacement_move,
            is_uncaptured_vp_hex_for_side=self._is_uncaptured_vp_hex_for_side,
        )

    def _finalize_rl_action(self, state, unit, action):
        action_out, reason, budget = finalize_action(
            state,
            unit,
            action,
            is_non_displacement_move=self._is_non_displacement_move,
            is_uncaptured_vp_hex_for_side=self._is_uncaptured_vp_hex_for_side,
            finalizer_override_profile=self.finalizer_override_profile,
            finalizer_debug=self.finalizer_debug,
            finalizer_debug_budget=self._finalizer_debug_budget,
            decision_context={
                "strategy": getattr(getattr(self, "current_strategy", None), "name", None),
                "sampled": getattr(self.current_option_sampled, "name", None),
                "resolved": getattr(self.current_option_resolved, "name", None),
                "executed": getattr(self.current_option, "name", None),
            },
        )
        self._finalizer_debug_budget = int(budget)
        return action_out, reason

    def _option_from_action_tag(self, action, fallback: TacticalOption) -> TacticalOption:
        tagged = str(getattr(action, "rl_l2_option", "") or "").strip().upper()
        if not tagged:
            return fallback
        try:
            return TacticalOption[tagged]
        except KeyError:
            return fallback

    def act(self, state, side, unit, obs):
        if side != self.rl_side:
            action = self._enemy_action(state, unit)
            action.unit_id = unit.unit_id
            self.sim_env.runtime.activated_units.add(unit.unit_id)
            return action

        turn_now = int(getattr(state, "turn", 0))
        action_vec = self._cached_action_vec_by_turn.pop(turn_now, None)
        if action_vec is None:
            action_vec = self._predict_action_vec(state, obs=obs)
        if action_vec.size not in (3, 4):
            raise RuntimeError(
                f"Expected action [strategy, option, attack_mode(, unit_slot)], got shape={action_vec.shape}"
            )
        strategy_idx = int(action_vec[0])
        option_idx = int(action_vec[1])
        attack_mode = int(action_vec[2])
        sampled_strategy = StrategicIntent(strategy_idx)
        # Evaluate strategy per activation to avoid turn-wide lock-in.
        effective_strategy = sampled_strategy
        sampled_option = TacticalOption(option_idx)
        resolved_option = sampled_option
        self.current_stepin_legal = False
        self.current_stepin_forced_option = False
        # Diagnostic mode to isolate "SB3-kept" behavior:
        # keeps legal finalization but disables planner-like strategic coercions.
        if not self.diagnostic_min_overrides:
            # R4 skeleton: "entry head" proxy for eval parity.
            if effective_strategy == StrategicIntent.CAPTURE:
                try:
                    legal_stepin = self.executor._best_step_into_uncaptured_vp(state, unit) is not None
                except Exception:
                    legal_stepin = False
                self.current_stepin_legal = bool(legal_stepin)
                if legal_stepin and resolved_option != TacticalOption.ADVANCE:
                    resolved_option = TacticalOption.ADVANCE
                    self.current_stepin_forced_option = True
            # Mission-priority override during eval parity:
            # if objectives are pending and no emergency, force CAPTURE intent.
            try:
                objectives_pending = self.executor._has_uncaptured_objective_for_side(state, unit.side)
                capture_emergency = self.executor._is_capture_emergency(state, unit)
                nearest_vp_d = self.executor._nearest_uncaptured_vp_dist(state, unit)
            except Exception:
                objectives_pending = False
                capture_emergency = False
                nearest_vp_d = None
            near_objective_pressure = nearest_vp_d is not None and float(nearest_vp_d) <= 2.0
            if (
                objectives_pending
                and not capture_emergency
                and effective_strategy != StrategicIntent.CAPTURE
                and (self.current_stepin_legal or near_objective_pressure)
            ):
                effective_strategy = StrategicIntent.CAPTURE
                if resolved_option in (TacticalOption.RETREAT, TacticalOption.HOLD):
                    resolved_option = TacticalOption.ADVANCE
        strategy_name = effective_strategy.name
        self.current_strategy = self._strategy_stub()
        self.current_strategy.name = strategy_name

        planner_context = self.mission_planner.build_context(state, unit, side)
        action = self.executor.execute(
            state=state,
            unit=unit,
            option=resolved_option,
            attack_mode=attack_mode,
            strategy=effective_strategy,
            objective_tracked_side=self._objective_tracked_side(),
            planner_context=planner_context,
        )
        action, finalize_reason = self._finalize_rl_action(state, unit, action)
        try:
            setattr(action, "rl_eval_finalized_reason", str(finalize_reason))
        except Exception:
            pass
        try:
            self.mission_planner.register_outcome(state, planner_context, action)
        except Exception:
            pass

        resolved_from_action = self._option_from_action_tag(action, resolved_option)
        executed_option = self.action_bridge.infer_executed_option(action, resolved_from_action)
        self.current_option_sampled = sampled_option
        self.current_option_resolved = resolved_from_action
        self.current_option = executed_option
        self.current_attack_mode = attack_mode if executed_option == TacticalOption.ATTACK else 0
        self.last_decision_trace = self.action_bridge.build_trace(
            sampled_option=sampled_option,
            resolved_option=resolved_from_action,
            executed_option=executed_option,
            strategy_name=strategy_name,
        )
        try:
            setattr(action, "rl_stepin_legal_mask", bool(self.current_stepin_legal))
            setattr(action, "rl_stepin_forced_option", bool(self.current_stepin_forced_option))
        except Exception:
            pass

        action.unit_id = unit.unit_id
        self.sim_env.runtime.activated_units.add(unit.unit_id)
        return action


def _resolve_model_path_for_side(repo_root: Path, rl_side: str, models_subdir: str = "") -> Path | None:
    models_dir = (repo_root / "models" / models_subdir) if models_subdir else (repo_root / "models")
    side = (rl_side or "").strip().upper()
    candidates = [
        models_dir / f"sb3_latest_{side}.zip",
        models_dir / f"sb3_best_{side}" / "best_model.zip",
    ]
    return next((p for p in candidates if p.exists()), None)


def _resolve_vecnorm_path_for_side(repo_root: Path, rl_side: str, models_subdir: str = "") -> Path | None:
    models_dir = (repo_root / "models" / models_subdir) if models_subdir else (repo_root / "models")
    side = (rl_side or "").strip().upper()
    candidates = [
        models_dir / f"sb3_vecnormalize_{side}.pkl",
    ]
    exact = next((p for p in candidates if p.exists()), None)
    if exact is not None:
        return exact

    # Fallback discovery for renamed/moved artifacts.
    alt_candidates = sorted(models_dir.glob(f"*vecnormalize*{side}*.pkl"))
    if alt_candidates:
        return alt_candidates[0]
    return None


def _scenario_sides(repo_root: Path, scenario_id: str) -> set[str]:
    scenario_path = repo_root / "assault_sim" / "assets" / "scenarios" / f"{scenario_id}.json"
    if not scenario_path.exists():
        return set()
    try:
        with open(scenario_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return set()
    units = payload.get("units", [])
    return {
        str(u.get("side", "")).upper()
        for u in units
        if isinstance(u, dict) and u.get("side")
    }


def _safe_name(value: str) -> str:
    return "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in value)


def _dedupe_schedule_by_scenario_id(schedule):
    seen: set[str] = set()
    deduped = []
    for phase in schedule:
        sid = str(getattr(phase, "id", "") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        deduped.append(phase)
    return deduped


def evaluate_sb3(
    episodes: int = 100,
    seed: int | None = None,
    out_dir: str | None = None,
    diagnostic_min_overrides: bool = False,
    config: str | None = None,
):
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.monitor import Monitor
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "stable-baselines3 is not installed. Install with: pip install stable-baselines3 gymnasium"
        ) from exc

    repo_root = Path(__file__).resolve().parents[2]
    reports_dir = Path(out_dir) if out_dir else (repo_root / "assault_sim" / "session" / "reports" / "sb3_eval")
    reports_dir.mkdir(parents=True, exist_ok=True)
    train_config_path = (
        Path(config).expanduser().resolve()
        if config
        else (repo_root / "assault_sim" / "config" / "train_config.json")
    )
    cfg = load_train_config(train_config_path)
    os.environ["ASSAULT_P4_ADVANCED_PLANNER"] = "1" if bool(getattr(cfg, "p4_advanced_planner_enabled", False)) else "0"
    os.environ["ASSAULT_P4_ADVANCED_HORIZON"] = str(int(getattr(cfg, "p4_advanced_planner_horizon", 2) or 2))
    scenario_schedule = _dedupe_schedule_by_scenario_id(list(cfg.scenario_schedule))
    rl_sides = list(cfg.rl_sides)
    eval_seed = int(PPOConfig.SEED if seed is None else seed)
    if not rl_sides:
        rl_sides = [PPOConfig.RL_SIDE]

    all_reports: dict[str, dict[str, dict]] = {}
    all_models = {}
    comparison_rows = []

    allow_unnormalized_eval = os.getenv("ASSAULT_ALLOW_EVAL_WITHOUT_VECNORM", "0") == "1"
    for rl_side in rl_sides:
        all_reports[rl_side] = {}
        all_models[rl_side] = {}

        for phase in scenario_schedule:
            scenario = phase.id
            models_subdir = cfg.resolve_models_subdir(
                scenario_id=scenario,
                side=rl_side,
            )
            model_path = _resolve_model_path_for_side(repo_root, rl_side, models_subdir=models_subdir)
            if model_path is None:
                print(
                    f"[WARN] SB3 model not found for side={rl_side} scenario={scenario} "
                    f"(models_subdir='{models_subdir or '.'}'); skipping."
                )
                continue
            vecnorm_path = _resolve_vecnorm_path_for_side(repo_root, rl_side, models_subdir=models_subdir)
            if vecnorm_path is None and not allow_unnormalized_eval:
                raise RuntimeError(
                    f"VecNormalize stats not found for side={rl_side} scenario={scenario}. "
                    "Refusing unnormalized eval. Set ASSAULT_ALLOW_EVAL_WITHOUT_VECNORM=1 to override."
                )
            model = PPO.load(str(model_path), device="cpu")
            all_models[rl_side][scenario] = str(model_path)
            sides_in_scenario = _scenario_sides(repo_root, scenario)
            if rl_side not in sides_in_scenario:
                print(
                    f"[WARN] Skip eval side={rl_side} scenario={scenario}: "
                    f"side not present in scenario units (found={sorted(sides_in_scenario)})"
                )
                continue

            print(_ansi(
                f"\n=== EVAL side={rl_side} scenario={scenario} episodes={episodes} ===",
                color="cyan",
                bold=True,
            ))
            env = make_env(
                config_path=repo_root / "assault_sim" / "config" / "sim_config.yaml",
                env_config_path=repo_root / "assault_sim" / "config" / "env_config.json",
                rl_side=rl_side,
                scenario=scenario,
                reward_fn=ShapedReward(rl_side=rl_side),
                seed=eval_seed,
            )
            # Fail fast on observation-shape mismatch to avoid noisy per-episode errors.
            model_obs_shape = tuple(getattr(getattr(model, "observation_space", None), "shape", ()) or ())
            env_obs = env.reset()
            env_obs_shape = tuple(np.asarray(env_obs, dtype=np.float32).shape)
            if model_obs_shape and env_obs_shape and model_obs_shape != env_obs_shape:
                raise RuntimeError(
                    "Observation shape mismatch between model and current encoder. "
                    f"model_obs_shape={model_obs_shape}, env_obs_shape={env_obs_shape}. "
                    "This usually means the observation vector changed (e.g. 70 -> 74). "
                    "Retrain model and VecNormalize with current code before running eval."
                )

            obs_normalizer = None
            if vecnorm_path is not None and vecnorm_path.exists():
                try:
                    from assault_sim.envs.gym_assault_env import GymAssaultEnv

                    def make_norm_env():
                        return Monitor(
                            GymAssaultEnv(
                                scenario=scenario,
                                rl_side=rl_side,
                                seed=eval_seed,
                            )
                        )

                    norm_env = DummyVecEnv([make_norm_env])
                    vecnorm = VecNormalize.load(str(vecnorm_path), norm_env)
                    vecnorm.training = False
                    vecnorm.norm_reward = False

                    def _normalize_obs(obs):
                        arr = np.asarray(obs, dtype=np.float32)
                        return vecnorm.normalize_obs(arr.reshape(1, -1))[0]

                    obs_normalizer = _normalize_obs
                    print(f"Loaded VecNormalize stats for {rl_side}: {vecnorm_path}")
                except Exception as e:
                    print(f"[WARN] Could not load VecNormalize stats ({rl_side}), continuing without normalization: {e}")
            else:
                print(f"[WARN] VecNormalize stats not found for {rl_side}, evaluating without obs normalization")

            controller = SB3EvalController(
                model,
                rl_side,
                env.sim,
                obs_normalizer=obs_normalizer,
                capture_guardrails_enabled=bool(getattr(cfg, "capture_guardrails_enabled", True)),
                diagnostic_force_capture_only=bool(getattr(cfg, "diagnostic_force_capture_only", False)),
                diagnostic_min_overrides=bool(diagnostic_min_overrides),
                finalizer_override_profile=str(getattr(cfg, "finalizer_override_profile", "strict") or "strict"),
            )
            evaluator = Evaluator(
                env=env,
                rl_controller=controller,
                rl_side=rl_side,
            )
            results = evaluator.evaluate(episodes)

            analyzer = ResultsAnalyzer(results, rl_side)
            analyzer.print_report()

            dashboard = EvalDashboard()
            for r in results:
                dashboard.add_episode(r)
            csv_name = f"metrics_sb3_{_safe_name(rl_side)}_{_safe_name(scenario)}.csv"
            csv_path = reports_dir / csv_name
            dashboard.save_csv(str(csv_path))

            side_report = {
                "meta": {
                    "episodes": episodes,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "model": str(model_path),
                    "scenario": scenario,
                    "rl_side": rl_side,
                    "vecnormalize_path": str(vecnorm_path) if vecnorm_path is not None and vecnorm_path.exists() else None,
                    "obs_normalized": bool(obs_normalizer is not None),
                    "diagnostic_min_overrides": bool(diagnostic_min_overrides),
                    "finalizer_override_profile": str(getattr(cfg, "finalizer_override_profile", "strict") or "strict"),
                    "models_subdir": models_subdir,
                    "csv": str(csv_path),
                },
                "summary": analyzer.summary(),
                "combat": analyzer.combat_metrics(),
                "advanced": analyzer.advanced_metrics(),
                "policy_alignment": analyzer.policy_alignment(),
                "mission": analyzer.mission_metrics(),
                "action_execution": analyzer.action_execution(),
                "units": analyzer.unit_analysis(),
                "strategy": analyzer.strategy_analysis(),
            }
            all_reports[rl_side][scenario] = side_report
            comparison_rows.append({
                "rl_side": rl_side,
                "scenario": scenario,
                "episodes": side_report["summary"].get("episodes", 0),
                "win_rate": side_report["summary"].get("win_rate", 0.0),
                "win_score_rate": side_report["summary"].get("win_score_rate", side_report["summary"].get("win_rate", 0.0)),
                "true_win_rate": side_report["summary"].get("true_win_rate", 0.0),
                "draw_rate": side_report["summary"].get("draw_rate", 0.0),
                "loss_rate": side_report["summary"].get("loss_rate", 0.0),
                "draws": side_report["summary"].get("draws", 0),
                "losses": side_report["summary"].get("losses", 0),
                "avg_vp": side_report["summary"].get("avg_vp", 0.0),
                "avg_steps": side_report["summary"].get("avg_steps", 0.0),
                "end_reason_counts": side_report["summary"].get("end_reason_counts", {}),
                "win_rate_by_end_reason": side_report["summary"].get("win_rate_by_end_reason", {}),
                "rl_result_counts": side_report["summary"].get("rl_result_counts", {}),
                "tracked_result_counts": side_report["summary"].get("tracked_result_counts", {}),
                "trade_mean": side_report["combat"].get("trade_mean", 0.0),
                "damage_ratio": side_report["combat"].get("damage_ratio", 0.0),
            })

    if not comparison_rows:
        raise SystemExit(
            "No valid side/scenario evaluations were produced. "
            "Likely missing model artifact(s) for current train_config (sb3_latest_<SIDE>.zip)."
        )

    print(_ansi("\n=== COMPARATIVE SUMMARY (SIDE x SCENARIO) ===", color="cyan", bold=True))
    if not comparison_rows:
        print("(no valid side/scenario combinations evaluated)")
    else:
        for row in comparison_rows:
            reason_counts = row.get("end_reason_counts", {})
            reason_rates = row.get("win_rate_by_end_reason", {})
            reasons_str = ", ".join(
                f"{reason}:{reason_rates.get(reason, 0.0):.2f} ({count})"
                for reason, count in reason_counts.items()
            ) or "-"
            rl_results_str = ", ".join(
                f"{k}:{v}" for k, v in row.get("rl_result_counts", {}).items()
            ) or "-"
            print(
                f"side={row['rl_side']} scenario={row['scenario']} "
                f"score_win_rate_objective(draw=0.5)={row.get('win_score_rate', row['win_rate']):.3f} "
                f"true_win_rate_objective(only_vittoria)={row.get('true_win_rate', 0.0):.3f} "
                f"draw_rate={row.get('draw_rate', 0.0):.3f} "
                f"loss_rate={row.get('loss_rate', 0.0):.3f} "
                f"avg_vp={row['avg_vp']:.3f} "
                f"avg_steps={row['avg_steps']:.1f} trade_mean={row['trade_mean']:.3f} "
                f"damage_ratio={row['damage_ratio']:.3f} draws={row['draws']} "
                f"reasons=[{reasons_str}] rl_results=[{rl_results_str}] "
            )

    report = {
        "meta": {
            "episodes": episodes,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "seed": eval_seed,
            "output_dir": str(reports_dir),
            "scenario_schedule": [
                {"id": p.id, "episodes": p.episodes}
                for p in scenario_schedule
            ],
            "rl_sides": rl_sides,
            "models": all_models,
            "train_config_path": str(train_config_path),
            "diagnostic_min_overrides": bool(diagnostic_min_overrides),
            "finalizer_override_profile": str(getattr(cfg, "finalizer_override_profile", "strict") or "strict"),
            "models_subdir": str(getattr(cfg, "sb3_models_subdir", "") or "").strip(),
            "models_subdir_template": str(getattr(cfg, "sb3_models_subdir_template", "") or "").strip(),
        },
        "by_side_and_scenario": all_reports,
        "comparison": comparison_rows,
    }
    out_name = f"metrics_sb3_report_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path = reports_dir / out_name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved multi-side SB3 report -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate SB3 model(s) and print report.")
    parser.add_argument("--episodes", type=int, default=100, help="Number of episodes per side/scenario")
    parser.add_argument("--seed", type=int, default=None, help="Evaluation seed override")
    parser.add_argument("--out-dir", type=str, default=None, help="Directory to store report and CSV outputs")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional path to train_config.json (defaults to assault_sim/config/train_config.json)",
    )
    parser.add_argument(
        "--diagnostic-min-overrides",
        action="store_true",
        help="Disable planner-like eval coercions (step-in/mission-priority overrides) while keeping legality finalization",
    )
    args = parser.parse_args()
    evaluate_sb3(
        episodes=args.episodes,
        seed=args.seed,
        out_dir=args.out_dir,
        diagnostic_min_overrides=bool(args.diagnostic_min_overrides),
        config=args.config,
    )

