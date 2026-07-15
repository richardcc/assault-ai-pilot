from __future__ import annotations

import json
import os
import time
import uuid
import multiprocessing as mp
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path
from statistics import mean

import torch

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.inference_service import InferenceService
from agents.efficientzero_v2.core.interop import (
    EventBus,
    JsonlWriter,
    MuZeroVOECAdapter,
    RunManifest,
    load_efficientzero_config,
)
from agents.efficientzero_v2.train.trainer import EfficientZeroV2Trainer
from agents.efficientzero_v2.core.replay import ReplayBuffer
from agents.efficientzero_v2.core.selfplay import (
    play_episode,
    resolve_effective_step_budget,
)
from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator

_PROCESS_ACTOR_STATE: dict = {}


def _process_actor_init(
    voec_assets,
    model_spec: dict,
    model_state_dict: dict,
    selfplay_cfg: dict,
    scenario_id: str,
) -> None:
    sim = VOECSimulator(assets=voec_assets)
    adapter = MuZeroVOECAdapter(sim)
    model = EfficientZeroV2Network(
        observation_dim=int(model_spec["observation_dim"]),
        hidden_dim=int(model_spec["hidden_dim"]),
        action_dim=int(model_spec["action_dim"]),
        encoder_type=str(model_spec["encoder_type"]),
        observation_channels=int(model_spec["observation_channels"]),
        observation_height=int(model_spec["observation_height"]),
        observation_width=int(model_spec["observation_width"]),
        dynamics_blocks=int(model_spec["dynamics_blocks"]),
        prediction_blocks=int(model_spec["prediction_blocks"]),
    )
    model.load_state_dict(model_state_dict)
    model.eval()
    _PROCESS_ACTOR_STATE.clear()
    _PROCESS_ACTOR_STATE.update(
        {
            "adapter": adapter,
            "model": model,
            "selfplay_cfg": dict(selfplay_cfg),
            "scenario_id": str(scenario_id),
            "weights_version": 0,
        }
    )


def _process_actor_run_episode(ep_seed: int) -> list:
    state = _PROCESS_ACTOR_STATE
    cfg = dict(state["selfplay_cfg"])
    with torch.inference_mode():
        return play_episode(
            adapter=state["adapter"],
            scenario_id=str(state["scenario_id"]),
            seed=int(ep_seed),
            max_steps=int(cfg["max_steps"]),
            max_steps_override=int(cfg["max_steps_override"]),
            max_turns_override=int(cfg.get("max_turns_override", 0)),
            action_dim=int(cfg["action_dim"]),
            model=state["model"],
            mcts_simulations=int(cfg["mcts_simulations"]),
            mcts_c_puct=float(cfg["mcts_c_puct"]),
            mcts_unroll_steps=int(cfg["mcts_unroll_steps"]),
            mcts_discount=float(cfg["mcts_discount"]),
            mcts_temperature=float(cfg["mcts_temperature"]),
            mcts_dirichlet_alpha=float(cfg["mcts_dirichlet_alpha"]),
            mcts_dirichlet_epsilon=float(cfg["mcts_dirichlet_epsilon"]),
            inference_cache_limit=int(cfg["inference_cache_limit"]),
            timeout_penalty=float(cfg["timeout_penalty"]),
            reward_shaping=dict(cfg["reward_shaping"]),
            objective_opportunity_near_vp_max_dist=float(
                cfg.get("objective_opportunity_near_vp_max_dist", 2.0)
            ),
            collect_xai=bool(cfg.get("collect_xai", False)),
        )


def _process_actor_update_weights(model_state_dict: dict, version: int) -> int:
    state = _PROCESS_ACTOR_STATE
    current = int(state.get("weights_version", 0))
    new_version = int(version)
    if new_version <= current:
        return int(os.getpid())
    model = state["model"]
    model.load_state_dict(model_state_dict)
    model.eval()
    state["weights_version"] = new_version
    return int(os.getpid())


def _start_mlflow_run(experiment_name: str, run_name: str):
    try:
        import mlflow  # type: ignore
    except Exception:
        return None, nullcontext()
    mlflow.set_experiment(str(experiment_name))
    ctx = mlflow.start_run(run_name=str(run_name) if str(run_name).strip() else None)
    return mlflow, ctx


def _mlflow_log_params(mlflow_mod, params: dict) -> None:
    if mlflow_mod is None:
        return
    for k, v in (params or {}).items():
        try:
            mlflow_mod.log_param(str(k), str(v))
        except Exception:
            continue


def _mlflow_log_metrics(mlflow_mod, metrics: dict, step: int = 0) -> None:
    if mlflow_mod is None:
        return
    for k, v in (metrics or {}).items():
        if isinstance(v, (int, float)):
            try:
                mlflow_mod.log_metric(str(k), float(v), step=step)
            except Exception:
                continue


def _resolve_device(device_cfg: str) -> str:
    raw = str(device_cfg or "auto").strip().lower()
    if raw == "cpu":
        return "cpu"
    if raw == "cuda":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _collect_config_preflight_warnings(config_path: str | Path) -> list[str]:
    try:
        import yaml
    except Exception:
        return []
    try:
        loaded = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    except Exception:
        return ["config_unreadable_or_invalid_yaml"]
    raw = dict(loaded or {}) if isinstance(loaded, dict) else {}
    train_cfg = dict(raw.get("train", {}) or {})
    selfplay_cfg = dict(raw.get("selfplay", {}) or {})
    warnings: list[str] = []
    if "reward_shaping" not in selfplay_cfg:
        warnings.append("missing.selfplay.reward_shaping")
    if "objective_signal" not in train_cfg:
        warnings.append("missing.train.objective_signal")
    if "objective_head" not in train_cfg:
        warnings.append("missing.train.objective_head")
    if "objective_reporting" not in train_cfg:
        warnings.append("missing.train.objective_reporting")
    return warnings


def _atomic_torch_save(
    state_dict: dict,
    target_path: Path,
    retries: int = 3,
    retry_sleep_s: float = 0.25,
) -> None:
    """
    Write checkpoint atomically to reduce partial-write failures on Windows.
    """
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    last_err: Exception | None = None
    for _ in range(max(1, int(retries))):
        try:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            torch.save(state_dict, tmp_path)
            # Atomic replace once the temporary file is fully written.
            os.replace(str(tmp_path), str(target_path))
            return
        except Exception as exc:
            last_err = exc
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            time.sleep(float(retry_sleep_s))
    if last_err is not None:
        raise last_err


def _assault_advantage_bucket(
    chosen_prob: float,
    margin: float,
    legal_count: int,
    *,
    prob_threshold: float = 0.55,
    margin_threshold: float = 0.20,
    legal_count_threshold: int = 6,
    min_score: int = 2,
) -> str:
    score = 0
    if float(chosen_prob) >= float(prob_threshold):
        score += 1
    if float(margin) >= float(margin_threshold):
        score += 1
    if int(legal_count) >= int(legal_count_threshold):
        score += 1
    return "favorable" if score >= int(min_score) else "unfavorable"


def _episode_phase29_from_samples(
    samples: list,
    *,
    conversion_window_steps: int = 2,
    assault_prob_threshold: float = 0.55,
    assault_margin_threshold: float = 0.20,
    assault_legal_count_threshold: int = 6,
    assault_min_score: int = 2,
) -> dict[str, float]:
    bucket = {
        "reaction_window_count": 0.0,
        "reaction_fire_count": 0.0,
        "reaction_fire_skipped_count": 0.0,
        "reaction_fire_kill_conversions": 0.0,
        "reaction_fire_damage_sum": 0.0,
        "melee_attempts": 0.0,
        "melee_success_count": 0.0,
        "melee_kills_sum": 0.0,
        "melee_damage_sum": 0.0,
        "assault_favorable_count": 0.0,
        "assault_unfavorable_count": 0.0,
        "xai_decision_steps": 0.0,
        "xai_policy_confidence_sum": 0.0,
        "xai_policy_margin_sum": 0.0,
        "xai_latent_signal_steps": 0.0,
        "xai_vp_capture_opportunity_steps": 0.0,
        "xai_vp_capture_taken_steps": 0.0,
        "conversion_progress_steps": 0.0,
        "conversion_total_steps": 0.0,
        "conversion_within_2_after_progress": 0.0,
        "terminal_steps": 0.0,
        "timeout_steps": 0.0,
    }
    last_progress_step = -10**9
    for idx, s in enumerate(list(samples or [])):
        info = dict(getattr(s, "info", {}) or {})
        bucket["xai_decision_steps"] += 1.0
        chosen_prob = float(info.get("chosen_action_prob", 0.0) or 0.0)
        margin = float(info.get("mcts_margin", 0.0) or 0.0)
        legal_count = int(info.get("legal_action_count", 0) or 0)
        bucket["xai_policy_confidence_sum"] += chosen_prob
        bucket["xai_policy_margin_sum"] += margin
        latent_idx = list(info.get("latent_top_indices", []) or [])
        if latent_idx:
            bucket["xai_latent_signal_steps"] += 1.0
        legal_caps = int(info.get("legal_capture_options", 0) or 0)
        if legal_caps > 0:
            bucket["xai_vp_capture_opportunity_steps"] += 1.0
        converted = int(info.get("objective_converted", 0) or 0) > 0
        if converted:
            bucket["xai_vp_capture_taken_steps"] += 1.0
            bucket["conversion_total_steps"] += 1.0
        progress_delta = float(info.get("objective_progress_delta", 0.0) or 0.0)
        if progress_delta > 0.0:
            bucket["conversion_progress_steps"] += 1.0
            last_progress_step = int(idx)
        if converted and int(idx) - int(last_progress_step) <= int(conversion_window_steps):
            bucket["conversion_within_2_after_progress"] += 1.0
        reaction_opts = int(info.get("legal_reaction_options", 0) or 0)
        if reaction_opts > 0:
            bucket["reaction_window_count"] += 1.0
        action_kind = str(info.get("action_kind", "") or "").strip().upper()
        damage = float(info.get("damage_dealt", 0.0) or 0.0)
        kills = float(info.get("kills_dealt", 0.0) or 0.0)
        if action_kind == "OPPORTUNITY_FIRE":
            bucket["reaction_fire_count"] += 1.0
            bucket["reaction_fire_damage_sum"] += damage
            if kills > 0.0:
                bucket["reaction_fire_kill_conversions"] += 1.0
        elif action_kind == "OPPORTUNITY_SKIP":
            bucket["reaction_fire_skipped_count"] += 1.0
        if ("ASSAULT" in action_kind) or (action_kind in {"MELEE", "ASSAULT_MELEE"}):
            bucket["melee_attempts"] += 1.0
            bucket["melee_damage_sum"] += damage
            bucket["melee_kills_sum"] += kills
            if damage > 0.0 or kills > 0.0:
                bucket["melee_success_count"] += 1.0
            adv_bucket = _assault_advantage_bucket(
                chosen_prob=chosen_prob,
                margin=margin,
                legal_count=legal_count,
                prob_threshold=assault_prob_threshold,
                margin_threshold=assault_margin_threshold,
                legal_count_threshold=assault_legal_count_threshold,
                min_score=assault_min_score,
            )
            bucket[f"assault_{adv_bucket}_count"] += 1.0
        if bool(info.get("timeout", False)):
            bucket["timeout_steps"] += 1.0
        if str(info.get("terminal_reason", "")).strip():
            bucket["terminal_steps"] += 1.0
    return bucket


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vv = sorted(float(v) for v in values)
    pos = max(0, min(len(vv) - 1, int(round((len(vv) - 1) * float(q)))))
    return float(vv[pos])


def _episode_length_diagnostics(rows: list[dict], threshold: int) -> dict:
    lengths = [int(r.get("length", 0) or 0) for r in list(rows or [])]
    if not lengths:
        return {
            "episodes": 0,
            "short_threshold": int(threshold),
            "short_episode_rate": 0.0,
            "length_min": 0.0,
            "length_p25": 0.0,
            "length_p50": 0.0,
            "length_p75": 0.0,
            "length_max": 0.0,
            "length_mean": 0.0,
            "short_by_outcome": {},
            "short_by_reason": {},
        }
    short_flags = [1 if l < int(threshold) else 0 for l in lengths]
    by_outcome: dict[str, dict] = {}
    by_reason: dict[str, dict] = {}
    for row, is_short in zip(rows, short_flags):
        outcome = str(row.get("outcome_bucket", "unknown") or "unknown")
        reason = str(row.get("reason", "unknown") or "unknown")
        out_entry = by_outcome.setdefault(outcome, {"count": 0, "short_count": 0})
        out_entry["count"] += 1
        out_entry["short_count"] += int(is_short)
        rs_entry = by_reason.setdefault(reason, {"count": 0, "short_count": 0})
        rs_entry["count"] += 1
        rs_entry["short_count"] += int(is_short)
    for bucket in list(by_outcome.values()):
        bucket["short_rate"] = float(bucket["short_count"]) / float(max(1, bucket["count"]))
    for bucket in list(by_reason.values()):
        bucket["short_rate"] = float(bucket["short_count"]) / float(max(1, bucket["count"]))
    return {
        "episodes": int(len(lengths)),
        "short_threshold": int(threshold),
        "short_episode_rate": float(sum(short_flags)) / float(max(1, len(short_flags))),
        "length_min": float(min(lengths)),
        "length_p25": float(_percentile(lengths, 0.25)),
        "length_p50": float(_percentile(lengths, 0.50)),
        "length_p75": float(_percentile(lengths, 0.75)),
        "length_max": float(max(lengths)),
        "length_mean": float(mean(lengths)),
        "short_by_outcome": by_outcome,
        "short_by_reason": by_reason,
    }


def _build_units_sides_contract(
    *,
    samples: list,
    latest_metrics: dict,
    scenario_id: str,
    run_id: str,
) -> dict:
    side_turn_counts: dict[str, int] = {}
    unit_counts: dict[str, int] = {}
    unit_side: dict[str, str] = {}
    action_kind_counts: Counter[str] = Counter()
    action_kind_by_side: dict[str, Counter[str]] = {}
    vp_actions_by_side: dict[str, int] = {}
    vp_captures_by_side: dict[str, int] = {}
    tracked_captures_by_side: dict[str, int] = {}
    terminal_reasons: Counter[str] = Counter()
    timeout_count = 0
    outcome_by_side: dict[str, Counter[str]] = {}
    for s in list(samples or []):
        info = dict(getattr(s, "info", {}) or {})
        side = str(info.get("unit_side", "")).strip() or "unknown"
        unit_id = str(info.get("unit_id", "")).strip()
        action_kind = str(info.get("action_kind", "")).strip() or "UNKNOWN"
        reason = str(info.get("terminal_reason", "")).strip() or ""
        outcome = str(info.get("objective_outcome_bucket_actor", "")).strip() or "unknown"
        side_turn_counts[side] = int(side_turn_counts.get(side, 0)) + 1
        action_kind_counts[action_kind] += 1
        action_kind_by_side.setdefault(side, Counter())[action_kind] += 1
        if unit_id:
            unit_counts[unit_id] = int(unit_counts.get(unit_id, 0)) + 1
            unit_side[unit_id] = side
        if ("CAPTURE" in action_kind.upper()) or (int(info.get("legal_capture_options", 0) or 0) > 0):
            vp_actions_by_side[side] = int(vp_actions_by_side.get(side, 0)) + 1
        vp_cap = int(info.get("vp_captures", 0) or 0)
        if vp_cap > 0:
            vp_captures_by_side[side] = int(vp_captures_by_side.get(side, 0)) + vp_cap
            tracked_captures_by_side[side] = int(tracked_captures_by_side.get(side, 0)) + vp_cap
        if bool(info.get("timeout", False)):
            timeout_count += 1
        if reason:
            terminal_reasons[reason] += 1
        outcome_by_side.setdefault(side, Counter())[outcome] += 1
    transition_events = int(len(samples or []))
    units_total = max(1, transition_events)
    top_units = sorted(unit_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
    units_by_side: dict[str, list] = {}
    for uid, count in top_units:
        side = str(unit_side.get(uid, "unknown") or "unknown")
        units_by_side.setdefault(side, []).append(
            {
                "unit_id": str(uid),
                "side": side,
                "count": int(count),
                "rate_in_side": float(count) / float(max(1, side_turn_counts.get(side, 0))),
            }
        )
    return {
        "schema_version": "units_sides_v1",
        "engine": "efficientzero_v2",
        "run_id": str(run_id),
        "scenario_id": str(scenario_id),
        "transition_events": transition_events,
        "side_turn_counts": {k: int(v) for k, v in side_turn_counts.items()},
        "side_turn_rates": {
            k: float(v) / float(units_total) for k, v in side_turn_counts.items()
        },
        "top_action_units": [
            {
                "unit_id": str(uid),
                "side": str(unit_side.get(uid, "unknown") or "unknown"),
                "count": int(cnt),
                "rate_global": float(cnt) / float(units_total),
            }
            for uid, cnt in top_units
        ],
        "units_by_side": units_by_side,
        "global_actions": {
            "total_actions": int(sum(action_kind_counts.values())),
            "kinds": [
                {
                    "action_kind": str(kind),
                    "count": int(cnt),
                    "rate_global": float(cnt) / float(units_total),
                }
                for kind, cnt in action_kind_counts.most_common()
            ],
            "kinds_by_side": {
                side: [
                    {
                        "action_kind": str(kind),
                        "count": int(cnt),
                        "rate_in_side": float(cnt)
                        / float(max(1, side_turn_counts.get(side, 0))),
                    }
                    for kind, cnt in counts.most_common()
                ]
                for side, counts in action_kind_by_side.items()
            },
        },
        "vp_summary": {
            "vp_related_actions_total": int(sum(vp_actions_by_side.values())),
            "vp_captures_total": int(sum(vp_captures_by_side.values())),
            "by_side": {
                side: {
                    "vp_related_actions": int(vp_actions_by_side.get(side, 0)),
                    "vp_captures": int(vp_captures_by_side.get(side, 0)),
                    "tracked_captured": int(tracked_captures_by_side.get(side, 0)),
                }
                for side in sorted(set(list(side_turn_counts.keys()) + list(vp_actions_by_side.keys())))
            },
        },
        "strategy_summary": {
            "terminal_reasons": {k: int(v) for k, v in terminal_reasons.items()},
            "timeouts": int(timeout_count),
            "outcome_by_side": {
                side: {k: int(v) for k, v in buckets.items()}
                for side, buckets in outcome_by_side.items()
            },
            "phase_2_9_train_kpis": dict(latest_metrics.get("phase_2_9_train_kpis", {}) or {}),
            "short_episode_diagnostics": dict(latest_metrics.get("short_episode_diagnostics", {}) or {}),
            "inference_service_kpis": dict(latest_metrics.get("inference_service_kpis", {}) or {}),
        },
    }


def run_training(
    config_path: str,
    mlflow_experiment: str = "assault_efficientzero_v2",
    mlflow_run_name: str = "",
) -> dict:
    config_preflight_warnings = _collect_config_preflight_warnings(config_path)
    if config_preflight_warnings:
        print(
            "[EfficientZeroV2][WARN] objective/reward config preflight: "
            f"{', '.join(config_preflight_warnings)}"
        )
    cfg = load_efficientzero_config(Path(config_path))
    voec_cfg = load_voec_config(Path(cfg.paths["voec_config"]))

    scenario_id = str(cfg.scenario["id"])
    seed = int(cfg.scenario["seed"])
    iterations = int(cfg.train["iterations"])
    episodes_per_iter = int(cfg.train["episodes_per_iter"])
    batch_size = int(cfg.train["batch_size"])

    action_dim = int(cfg.model["action_dim"])
    observation_dim = int(cfg.model["observation_dim"])
    hidden_dim = int(cfg.model["hidden_dim"])
    encoder_type = str(cfg.model.get("encoder_type", "mlp"))
    observation_channels = int(cfg.model.get("observation_channels", 8))
    observation_height = int(cfg.model.get("observation_height", 16))
    observation_width = int(cfg.model.get("observation_width", 16))
    dynamics_blocks = int(cfg.model.get("dynamics_blocks", 1))
    prediction_blocks = int(cfg.model.get("prediction_blocks", 1))

    num_workers = int(cfg.selfplay.get("num_workers", 1))
    max_steps = int(cfg.selfplay["max_steps"])
    max_steps_override = int(cfg.selfplay.get("max_steps_override", 0))
    max_turns_override = int(cfg.selfplay.get("max_turns_override", 0))
    mcts_simulations = int(cfg.selfplay["mcts_simulations"])
    mcts_c_puct = float(cfg.selfplay["mcts_c_puct"])
    mcts_unroll_steps = int(cfg.selfplay.get("mcts_unroll_steps", 1))
    mcts_discount = float(cfg.selfplay.get("mcts_discount", 0.997))
    mcts_temperature = float(cfg.selfplay.get("mcts_temperature", 1.0))
    mcts_dirichlet_alpha = float(cfg.selfplay.get("mcts_dirichlet_alpha", 0.3))
    mcts_dirichlet_epsilon = float(cfg.selfplay.get("mcts_dirichlet_epsilon", 0.0))
    inference_cache_limit = int(cfg.selfplay.get("inference_cache_limit", 2048))
    timeout_penalty = float(cfg.selfplay.get("timeout_penalty", -0.1))
    reward_shaping = dict(cfg.selfplay.get("reward_shaping", {}) or {})

    objective_loss_weight = float(cfg.train.get("objective_loss_weight", 0.12))
    consistency_loss_weight = float(cfg.train.get("consistency_loss_weight", 0.0))
    consistency_unroll_steps = int(cfg.train.get("consistency_unroll_steps", 1))
    consistency_unroll_steps = max(1, consistency_unroll_steps)
    reanalysis_ratio = float(cfg.train.get("reanalysis_ratio", 0.0))
    reanalysis_value_mix = float(cfg.train.get("reanalysis_value_mix", 0.5))
    reanalysis_policy_mix = float(cfg.train.get("reanalysis_policy_mix", 0.3))
    value_bootstrap_steps = int(cfg.train.get("value_bootstrap_steps", 3))
    value_bootstrap_steps = max(1, value_bootstrap_steps)
    value_bootstrap_discount = float(cfg.train.get("value_bootstrap_discount", 0.997))
    amp_enabled = bool(cfg.train.get("amp_enabled", True))
    amp_dtype = str(cfg.train.get("amp_dtype", "auto"))
    compile_model = bool(cfg.train.get("compile_model", False))
    compile_mode = str(cfg.train.get("compile_mode", "reduce-overhead"))
    matmul_precision = str(cfg.train.get("matmul_precision", "high"))
    train_updates_per_iter = int(cfg.train.get("train_updates_per_iter", 1))
    train_updates_per_iter = max(1, train_updates_per_iter)
    checkpoint_every = int(cfg.train.get("checkpoint_every", 5))
    checkpoint_every = max(1, checkpoint_every)
    objective_target_mode = str(cfg.train.get("objective_target_mode", "progress")).strip().lower()
    objective_pos_weight = float(cfg.train.get("objective_pos_weight", 5.0))
    objective_opportunity_max_dist = float(cfg.train.get("objective_opportunity_max_dist", 2.0))
    objective_signal_cfg = dict(cfg.train.get("objective_signal", {}) or {})
    objective_head_cfg = dict(cfg.train.get("objective_head", {}) or {})
    objective_reporting_cfg = dict(cfg.train.get("objective_reporting", {}) or {})
    objective_opportunity_near_vp_max_dist = float(
        objective_signal_cfg.get("opportunity_near_vp_max_dist", objective_opportunity_max_dist)
    )
    objective_progress_positive_threshold = float(
        objective_head_cfg.get("progress_positive_threshold", 0.0)
    )
    objective_conversion_window_steps = int(
        objective_reporting_cfg.get("conversion_window_steps_after_progress", 2)
    )
    objective_assault_advantage_prob_threshold = float(
        objective_reporting_cfg.get("assault_advantage_prob_threshold", 0.55)
    )
    objective_assault_advantage_margin_threshold = float(
        objective_reporting_cfg.get("assault_advantage_margin_threshold", 0.20)
    )
    objective_assault_advantage_legal_count_threshold = int(
        objective_reporting_cfg.get("assault_advantage_legal_count_threshold", 6)
    )
    objective_assault_advantage_min_score = int(
        objective_reporting_cfg.get("assault_advantage_min_score", 2)
    )
    enable_post_train_analytics = bool(cfg.train.get("enable_post_train_analytics", False))
    collect_xai = bool(cfg.selfplay.get("collect_xai", cfg.train.get("collect_xai", False)))
    short_episode_threshold = int(cfg.train.get("short_episode_threshold", 80))

    device = _resolve_device(str(cfg.model.get("device", "auto")))
    selfplay_device = str(
        cfg.selfplay.get("device", ("cpu" if str(device) == "cuda" else str(device)))
    ).strip().lower()
    if selfplay_device not in {"cpu", "cuda"}:
        selfplay_device = "cpu" if str(device) == "cuda" else str(device)
    run_root = Path(str(cfg.paths["run_root"]))
    run_id = f"efficientzero_v2_{uuid.uuid4().hex[:8]}"
    run_dir = run_root / run_id

    print(f"[EfficientZeroV2] run_id={run_id}")
    print(f"[EfficientZeroV2] config={config_path}")
    print(f"[EfficientZeroV2] scenario={scenario_id} seed={seed}")
    print(f"[EfficientZeroV2] device={device}")
    print(f"[EfficientZeroV2] selfplay_device={selfplay_device}")
    print(f"[EfficientZeroV2] selfplay_workers={num_workers}")

    model = EfficientZeroV2Network(
        observation_dim=observation_dim,
        hidden_dim=hidden_dim,
        action_dim=action_dim,
        encoder_type=encoder_type,
        observation_channels=observation_channels,
        observation_height=observation_height,
        observation_width=observation_width,
        dynamics_blocks=dynamics_blocks,
        prediction_blocks=prediction_blocks,
    )
    if str(device) == "cuda":
        try:
            torch.set_float32_matmul_precision(matmul_precision)
        except Exception:
            pass
        try:
            torch.backends.cudnn.benchmark = True
        except Exception:
            pass
    if bool(compile_model):
        try:
            model = torch.compile(model, mode=compile_mode)
            print(f"[EfficientZeroV2] torch.compile enabled mode={compile_mode}")
        except Exception as exc:
            print(f"[EfficientZeroV2] torch.compile disabled (fallback): {exc}")
    trainer = EfficientZeroV2Trainer(
        model=model,
        lr=float(cfg.model["learning_rate"]),
        device=device,
        objective_loss_weight=objective_loss_weight,
        objective_target_mode=objective_target_mode,
        objective_pos_weight=objective_pos_weight,
        objective_opportunity_max_dist=objective_opportunity_max_dist,
        objective_progress_positive_threshold=objective_progress_positive_threshold,
        consistency_loss_weight=consistency_loss_weight,
        consistency_unroll_steps=consistency_unroll_steps,
        reanalysis_ratio=reanalysis_ratio,
        reanalysis_value_mix=reanalysis_value_mix,
        reanalysis_policy_mix=reanalysis_policy_mix,
        value_bootstrap_steps=value_bootstrap_steps,
        value_bootstrap_discount=value_bootstrap_discount,
        amp_enabled=amp_enabled,
        amp_dtype=amp_dtype,
    )
    model = trainer.model
    replay = ReplayBuffer(
        capacity=int(cfg.train["replay_capacity"]),
        recent_fraction=float(cfg.train.get("replay_recent_fraction", 0.7)),
        recent_window_ratio=float(cfg.train.get("replay_recent_window_ratio", 0.3)),
    )
    seq_sim = None
    seq_adapter = None
    if int(num_workers) <= 1:
        # Stable sequential path: reuse a single simulator/adapter across episodes.
        seq_sim = VOECSimulator(assets=voec_cfg.assets)
        seq_adapter = MuZeroVOECAdapter(seq_sim)
    budget_turn_limit = -1
    budget_unit_count = -1
    try:
        probe_adapter = (
            seq_adapter
            if seq_adapter is not None
            else MuZeroVOECAdapter(VOECSimulator(assets=voec_cfg.assets))
        )
        probe_obs = probe_adapter.initial_state(scenario_id=scenario_id, seed=int(seed))
        budget_unit_count = int(len(getattr(probe_obs, "units", []) or []))
        sim_probe = seq_sim if seq_sim is not None else getattr(probe_adapter, "sim", None)
        if sim_probe is not None and hasattr(sim_probe, "scenario_max_turns"):
            budget_turn_limit = int(sim_probe.scenario_max_turns() or 0)
    except Exception:
        budget_turn_limit = -1
        budget_unit_count = -1

    logged_effective_budget, logged_budget_source = resolve_effective_step_budget(
        max_steps=int(max_steps),
        max_steps_override=int(max_steps_override),
        max_turns_override=int(max_turns_override),
        unit_count=int(budget_unit_count),
        scenario_turn_limit=int(budget_turn_limit),
    )

    events_writer = None
    if bool(enable_post_train_analytics):
        (run_dir / "events").mkdir(parents=True, exist_ok=True)
        events_writer = JsonlWriter(run_dir / "events" / "train_events.jsonl")
    event_bus = EventBus(enabled=enable_post_train_analytics)
    latest_metrics: dict = {}
    iter_timing_rows: list[dict] = []
    run_phase29_totals: dict[str, float] = {}
    all_run_samples: list = []
    short_episode_rows: list[dict] = []
    iter_diagnostics_rows: list[dict] = []

    mlflow_mod, mlflow_ctx = _start_mlflow_run(
        experiment_name=str(mlflow_experiment),
        run_name=(str(mlflow_run_name).strip() or run_id),
    )
    _mlflow_log_params(
        mlflow_mod,
        {
            "run_id": run_id,
            "config_path": str(config_path),
            "device": device,
            "iterations": iterations,
            "episodes_per_iter": episodes_per_iter,
            "mcts_simulations": mcts_simulations,
            "consistency_loss_weight": consistency_loss_weight,
            "consistency_unroll_steps": consistency_unroll_steps,
            "reanalysis_ratio": reanalysis_ratio,
            "reanalysis_value_mix": reanalysis_value_mix,
            "reanalysis_policy_mix": reanalysis_policy_mix,
            "value_bootstrap_steps": value_bootstrap_steps,
            "value_bootstrap_discount": value_bootstrap_discount,
            "amp_enabled": amp_enabled,
            "amp_dtype": amp_dtype,
            "compile_model": compile_model,
            "compile_mode": compile_mode,
            "matmul_precision": matmul_precision,
            "selfplay_device": selfplay_device,
            "collect_xai": collect_xai,
            "short_episode_threshold": short_episode_threshold,
            "objective_loss_weight": objective_loss_weight,
            "objective_pos_weight": objective_pos_weight,
            "objective_opportunity_max_dist": objective_opportunity_max_dist,
            "objective_signal": {
                "opportunity_near_vp_max_dist": objective_opportunity_near_vp_max_dist,
            },
            "objective_head": {
                "progress_positive_threshold": objective_progress_positive_threshold,
            },
            "objective_reporting": {
                "conversion_window_steps_after_progress": objective_conversion_window_steps,
                "assault_advantage_prob_threshold": objective_assault_advantage_prob_threshold,
                "assault_advantage_margin_threshold": objective_assault_advantage_margin_threshold,
                "assault_advantage_legal_count_threshold": (
                    objective_assault_advantage_legal_count_threshold
                ),
                "assault_advantage_min_score": objective_assault_advantage_min_score,
            },
        },
    )

    parallel_selfplay_enabled = int(num_workers) > 1 and str(selfplay_device) == "cpu"
    parallel_backend = str(cfg.selfplay.get("parallel_backend", "thread")).strip().lower()
    if parallel_backend not in {"thread", "process"}:
        parallel_backend = "thread"
    use_process_actors = bool(parallel_selfplay_enabled and parallel_backend == "process")
    use_inference_service = bool(
        parallel_selfplay_enabled and str(device) == "cuda" and not use_process_actors
    )
    inference_service = None
    process_pool = None
    if use_inference_service:
        infer_max_batch_size = int(
            cfg.selfplay.get("inference_max_batch_size", max(4, min(64, num_workers * 8)))
        )
        infer_batch_wait_ms = float(cfg.selfplay.get("inference_batch_wait_ms", 2.0))
        inference_service = InferenceService(
            model=model,
            device=str(device),
            max_batch_size=infer_max_batch_size,
            batch_wait_ms=infer_batch_wait_ms,
        )
        inference_service.start()
        print(
            "[EfficientZeroV2] inference_service "
            f"max_batch={infer_max_batch_size} wait_ms={infer_batch_wait_ms:.2f}"
        )
    if use_process_actors:
        process_weight_sync_every_iters = int(
            cfg.selfplay.get("process_weight_sync_every_iters", 1)
        )
        process_weight_sync_every_iters = max(1, process_weight_sync_every_iters)
        model_spec = {
            "observation_dim": observation_dim,
            "hidden_dim": hidden_dim,
            "action_dim": action_dim,
            "encoder_type": encoder_type,
            "observation_channels": observation_channels,
            "observation_height": observation_height,
            "observation_width": observation_width,
            "dynamics_blocks": dynamics_blocks,
            "prediction_blocks": prediction_blocks,
        }
        selfplay_cfg = {
            "max_steps": max_steps,
            "max_steps_override": max_steps_override,
            "max_turns_override": max_turns_override,
            "action_dim": action_dim,
            "mcts_simulations": mcts_simulations,
            "mcts_c_puct": mcts_c_puct,
            "mcts_unroll_steps": mcts_unroll_steps,
            "mcts_discount": mcts_discount,
            "mcts_temperature": mcts_temperature,
            "mcts_dirichlet_alpha": mcts_dirichlet_alpha,
            "mcts_dirichlet_epsilon": mcts_dirichlet_epsilon,
            "inference_cache_limit": inference_cache_limit,
            "timeout_penalty": timeout_penalty,
            "reward_shaping": reward_shaping,
            "objective_opportunity_near_vp_max_dist": objective_opportunity_near_vp_max_dist,
            "collect_xai": collect_xai,
        }
        model_state_dict_cpu = {
            k: v.detach().to(device="cpu").contiguous() for k, v in model.state_dict().items()
        }
        mp_ctx = mp.get_context("spawn")
        process_pool = ProcessPoolExecutor(
            max_workers=int(num_workers),
            mp_context=mp_ctx,
            initializer=_process_actor_init,
            initargs=(
                voec_cfg.assets,
                model_spec,
                model_state_dict_cpu,
                selfplay_cfg,
                scenario_id,
            ),
        )
        print(
            "[EfficientZeroV2] process actors pool started "
            f"workers={int(num_workers)} (persistent)"
        )

    t_total = time.perf_counter()
    try:
        with mlflow_ctx:
            for it in range(iterations):
                print(f"[EfficientZeroV2] iteration {it+1}/{iterations} - selfplay")
                iter_t0 = time.perf_counter()
                model.eval()
                if use_process_actors and process_pool is not None and it > 0:
                    if (it % process_weight_sync_every_iters) == 0:
                        sync_t0 = time.perf_counter()
                        model_state_dict_cpu = {
                            k: v.detach().to(device="cpu").contiguous()
                            for k, v in model.state_dict().items()
                        }
                        target_version = int(it)
                        futs = [
                            process_pool.submit(
                                _process_actor_update_weights,
                                model_state_dict_cpu,
                                target_version,
                            )
                            for _ in range(int(num_workers))
                        ]
                        updated_pids = set()
                        for fut in as_completed(futs):
                            updated_pids.add(int(fut.result()))
                        sync_s = float(time.perf_counter() - sync_t0)
                        print(
                            "[EfficientZeroV2]   process actor weights synced "
                            f"version={target_version} workers={len(updated_pids)} sync_s={sync_s:.2f}"
                        )

                def _run_episode(ep_seed: int):
                    local_adapter = seq_adapter
                    if local_adapter is None:
                        # Parallel path keeps per-task adapter isolation.
                        local_sim = VOECSimulator(assets=voec_cfg.assets)
                        local_adapter = MuZeroVOECAdapter(local_sim)
                    model_for_episode = (
                        inference_service.create_proxy()
                        if inference_service is not None
                        else model
                    )
                    with torch.inference_mode():
                        return play_episode(
                            adapter=local_adapter,
                            scenario_id=scenario_id,
                            seed=ep_seed,
                            max_steps=max_steps,
                            max_steps_override=max_steps_override,
                            max_turns_override=max_turns_override,
                            action_dim=action_dim,
                            model=model_for_episode,
                            mcts_simulations=mcts_simulations,
                            mcts_c_puct=mcts_c_puct,
                            mcts_unroll_steps=mcts_unroll_steps,
                            mcts_discount=mcts_discount,
                            mcts_temperature=mcts_temperature,
                            mcts_dirichlet_alpha=mcts_dirichlet_alpha,
                            mcts_dirichlet_epsilon=mcts_dirichlet_epsilon,
                            inference_cache_limit=inference_cache_limit,
                            timeout_penalty=timeout_penalty,
                            reward_shaping=reward_shaping,
                            objective_opportunity_near_vp_max_dist=objective_opportunity_near_vp_max_dist,
                            collect_xai=collect_xai,
                        )

                def _consume_episode(ep_idx: int, ep_seed: int, samples):
                    # EfficientZero temporal consistency requires consecutive observations.
                    # Populate next_observation for each replay sample from episode rollouts.
                    def _compress_obs_for_replay(obs):
                        if isinstance(obs, torch.Tensor):
                            # Replay lives in host RAM; store compressed tensors to reduce CPU memory.
                            return obs.detach().to(device="cpu", dtype=torch.float16).contiguous()
                        return obs

                    if samples:
                        n = len(samples)
                        episode_action_idx = []
                        for s in samples:
                            pol = list(getattr(s, "policy_target", []) or [])
                            if pol:
                                aidx = int(max(range(len(pol)), key=lambda i: float(pol[i])))
                            else:
                                aidx = -1
                            episode_action_idx.append(aidx)
                        for i, s in enumerate(samples):
                            s.observation = _compress_obs_for_replay(s.observation)
                            nxt_obs = samples[i + 1].observation if i + 1 < n else s.observation
                            fut_obs = []
                            fut_actions = []
                            fut_rewards = []
                            fut_dones = []
                            rollout_horizon = max(consistency_unroll_steps, value_bootstrap_steps)
                            k_lim = min(rollout_horizon, max(0, n - i - 1))
                            for k in range(1, k_lim + 1):
                                fut_obs.append(_compress_obs_for_replay(samples[i + k].observation))
                                fut_actions.append(int(episode_action_idx[i + k - 1]))
                                fut_rewards.append(float(getattr(samples[i + k - 1], "reward_target", 0.0)))
                                fut_dones.append(bool((samples[i + k - 1].info or {}).get("done", False)))
                            info = s.info
                            if info is None:
                                s.info = {
                                    "next_observation": _compress_obs_for_replay(nxt_obs),
                                    "future_observations": fut_obs,
                                    "future_actions": fut_actions,
                                    "future_rewards": fut_rewards,
                                    "future_dones": fut_dones,
                                }
                            else:
                                info["next_observation"] = _compress_obs_for_replay(nxt_obs)
                                info["future_observations"] = fut_obs
                                info["future_actions"] = fut_actions
                                info["future_rewards"] = fut_rewards
                                info["future_dones"] = fut_dones
                    replay.extend(samples)
                    all_run_samples.extend(list(samples or []))
                    print(
                        f"[EfficientZeroV2]   episode {ep_idx+1}/{episodes_per_iter} "
                        f"samples={len(samples)} replay_size={len(replay)}"
                    )
                    if len(samples) < int(short_episode_threshold) and samples:
                        tail = dict(samples[-1].info or {})
                        print(
                            "[EfficientZeroV2]   short_episode "
                            f"seed={ep_seed} samples={len(samples)} "
                            f"turn={int(tail.get('game_turn', -1) or -1)} "
                            f"to_play={str(tail.get('to_play', '') or '')} "
                            f"reason={str(tail.get('terminal_reason', '') or 'n/a')} "
                            f"timeout={bool(tail.get('timeout', False))} "
                            f"captured={int(tail.get('objective_converted', 0) or 0)}"
                        )
                    if samples:
                        tail = dict(samples[-1].info or {})
                        short_episode_rows.append(
                            {
                                "iteration": int(it),
                                "seed": int(ep_seed),
                                "length": int(len(samples)),
                                "is_short": bool(len(samples) < int(short_episode_threshold)),
                                "reason": str(tail.get("terminal_reason", "") or "unknown"),
                                "timeout": bool(tail.get("timeout", False)),
                                "outcome_bucket": str(
                                    tail.get("objective_outcome_bucket_actor", "") or "unknown"
                                ),
                            }
                        )
                    episode_bucket = _episode_phase29_from_samples(
                        samples,
                        conversion_window_steps=objective_conversion_window_steps,
                        assault_prob_threshold=objective_assault_advantage_prob_threshold,
                        assault_margin_threshold=objective_assault_advantage_margin_threshold,
                        assault_legal_count_threshold=objective_assault_advantage_legal_count_threshold,
                        assault_min_score=objective_assault_advantage_min_score,
                    )
                    for k, v in episode_bucket.items():
                        run_phase29_totals[k] = float(run_phase29_totals.get(k, 0.0)) + float(v)

                episode_plan = []
                for ep in range(episodes_per_iter):
                    ep_seed = int(seed + it * episodes_per_iter + ep)
                    episode_plan.append((ep, ep_seed))
                    budget_label = (
                        f"source={logged_budget_source} effective_max_steps={int(logged_effective_budget)} "
                        f"(max_turns_override={int(max_turns_override)} "
                        f"max_steps_override={int(max_steps_override)} "
                        f"scenario_turn_limit={int(budget_turn_limit)} units={int(budget_unit_count)} "
                        f"max_steps={int(max_steps)})"
                    )
                    print(
                        f"[EfficientZeroV2]   episode {ep+1}/{episodes_per_iter} "
                        f"starting (seed={ep_seed}, sims={mcts_simulations}, budget={budget_label})"
                    )

                parallel_selfplay = bool(parallel_selfplay_enabled)
                if parallel_selfplay:
                    print(
                        f"[EfficientZeroV2]   parallel selfplay cpu workers={int(num_workers)} "
                        f"(backend={parallel_backend}, train_device={device}, "
                        f"inference_service={bool(inference_service)})"
                    )
                    completed: dict[int, tuple[int, list]] = {}
                    if use_process_actors:
                        if process_pool is None:
                            raise RuntimeError("Process actors pool not initialized")
                        fut_to_job = {
                            process_pool.submit(_process_actor_run_episode, ep_seed): (ep_idx, ep_seed)
                            for ep_idx, ep_seed in episode_plan
                        }
                        for fut in as_completed(fut_to_job):
                            ep_idx, ep_seed = fut_to_job[fut]
                            completed[ep_idx] = (ep_seed, fut.result())
                    else:
                        with ThreadPoolExecutor(max_workers=int(num_workers)) as ex:
                            fut_to_job = {
                                ex.submit(_run_episode, ep_seed): (ep_idx, ep_seed)
                                for ep_idx, ep_seed in episode_plan
                            }
                            for fut in as_completed(fut_to_job):
                                ep_idx, ep_seed = fut_to_job[fut]
                                completed[ep_idx] = (ep_seed, fut.result())
                    # Keep deterministic replay insertion order by episode index.
                    for ep_idx, ep_seed in episode_plan:
                        done_seed, samples = completed.get(ep_idx, (ep_seed, []))
                        _consume_episode(ep_idx, done_seed, samples)
                else:
                    if int(num_workers) > 1 and str(selfplay_device) != "cpu":
                        print(
                            "[EfficientZeroV2]   parallel selfplay requires selfplay.device=cpu; "
                            "using sequential selfplay"
                        )
                    for ep_idx, ep_seed in episode_plan:
                        samples = _run_episode(ep_seed)
                        _consume_episode(ep_idx, ep_seed, samples)
                selfplay_elapsed_s = float(time.perf_counter() - iter_t0)

                train_t0 = time.perf_counter()
                update_metrics: list[dict] = []
                replay_age_mean_vals: list[float] = []
                replay_age_max_vals: list[float] = []
                for _ in range(train_updates_per_iter):
                    batch = replay.sample(batch_size)
                    metrics = trainer.train_batch(batch)
                    m = metrics.to_dict()
                    update_metrics.append(m)
                    replay_age_values = []
                    current_add_idx = int(replay.add_index)
                    for s in list(batch):
                        add_idx = int((s.info or {}).get("replay_add_index", current_add_idx))
                        replay_age_values.append(max(0, current_add_idx - 1 - add_idx))
                    replay_age_mean_vals.append(
                        float(sum(replay_age_values)) / float(max(1, len(replay_age_values)))
                        if replay_age_values
                        else 0.0
                    )
                    replay_age_max_vals.append(float(max(replay_age_values)) if replay_age_values else 0.0)
                latest_metrics = {}
                if update_metrics:
                    metric_keys = [
                        "loss",
                        "policy_loss",
                        "value_loss",
                        "reward_loss",
                        "objective_loss",
                        "consistency_loss",
                        "reanalysis_coverage",
                        "reanalysis_target_drift",
                        "reanalysis_policy_drift",
                        "consistency_pairs",
                        "grad_norm",
                    ]
                    for k in metric_keys:
                        vals = [float(x.get(k, 0.0)) for x in update_metrics]
                        latest_metrics[k] = float(sum(vals) / float(max(1, len(vals))))
                latest_metrics["replay_age_mean"] = float(
                    sum(replay_age_mean_vals) / float(max(1, len(replay_age_mean_vals)))
                )
                latest_metrics["replay_age_max"] = (
                    float(max(replay_age_max_vals)) if replay_age_max_vals else 0.0
                )
                latest_metrics["train_updates_per_iter"] = int(train_updates_per_iter)
                iter_rows = [r for r in short_episode_rows if int(r.get("iteration", -1)) == int(it)]
                iter_short_diag = _episode_length_diagnostics(
                    rows=iter_rows,
                    threshold=short_episode_threshold,
                )
                latest_metrics["short_episode_rate"] = float(iter_short_diag.get("short_episode_rate", 0.0))
                latest_metrics["episode_length_p50"] = float(iter_short_diag.get("length_p50", 0.0))
                latest_metrics["episode_length_p75"] = float(iter_short_diag.get("length_p75", 0.0))
                latest_metrics["episode_length_max"] = float(iter_short_diag.get("length_max", 0.0))
                latest_metrics["short_episode_diagnostics_iter"] = dict(iter_short_diag)
                iter_diagnostics_rows.append({"iteration": int(it), **dict(iter_short_diag)})

                train_elapsed_s = float(time.perf_counter() - train_t0)
                iter_elapsed_s = float(time.perf_counter() - iter_t0)
                latest_metrics["timing_selfplay_s"] = selfplay_elapsed_s
                latest_metrics["timing_train_s"] = train_elapsed_s
                latest_metrics["timing_iter_s"] = iter_elapsed_s
                xai_den = max(1.0, float(run_phase29_totals.get("xai_decision_steps", 0.0)))
                cap_den = max(1.0, float(run_phase29_totals.get("xai_vp_capture_opportunity_steps", 0.0)))
                reaction_den = max(
                    1.0,
                    float(run_phase29_totals.get("reaction_fire_count", 0.0))
                    + float(run_phase29_totals.get("reaction_fire_skipped_count", 0.0)),
                )
                melee_den = max(1.0, float(run_phase29_totals.get("melee_attempts", 0.0)))
                conv_den = max(1.0, float(run_phase29_totals.get("conversion_total_steps", 0.0)))
                conv_prog_den = max(1.0, float(run_phase29_totals.get("conversion_progress_steps", 0.0)))
                phase29_train_kpis = {
                    "reaction_window_count": float(run_phase29_totals.get("reaction_window_count", 0.0)),
                    "reaction_fire_count": float(run_phase29_totals.get("reaction_fire_count", 0.0)),
                    "reaction_fire_skipped_count": float(run_phase29_totals.get("reaction_fire_skipped_count", 0.0)),
                    "reaction_fire_kill_conversions": float(run_phase29_totals.get("reaction_fire_kill_conversions", 0.0)),
                    "reaction_fire_damage_sum": float(run_phase29_totals.get("reaction_fire_damage_sum", 0.0)),
                    "reaction_fire_activation_rate": (
                        float(run_phase29_totals.get("reaction_fire_count", 0.0)) / reaction_den
                    ),
                    "reaction_fire_kill_conversion_rate": (
                        float(run_phase29_totals.get("reaction_fire_kill_conversions", 0.0))
                        / max(1.0, float(run_phase29_totals.get("reaction_fire_count", 0.0)))
                    ),
                    "reaction_fire_damage_induced_proxy": (
                        float(run_phase29_totals.get("reaction_fire_damage_sum", 0.0))
                        / max(1.0, float(run_phase29_totals.get("reaction_fire_count", 0.0)))
                    ),
                    "reaction_fire_damage_prevented_proxy": (
                        float(run_phase29_totals.get("reaction_fire_kill_conversions", 0.0))
                        / max(1.0, float(run_phase29_totals.get("reaction_fire_count", 0.0)))
                    ),
                    "assault_melee_action_family_count": float(run_phase29_totals.get("melee_attempts", 0.0)),
                    "melee_attempts": float(run_phase29_totals.get("melee_attempts", 0.0)),
                    "melee_success_count": float(run_phase29_totals.get("melee_success_count", 0.0)),
                    "melee_kills_sum": float(run_phase29_totals.get("melee_kills_sum", 0.0)),
                    "melee_damage_sum": float(run_phase29_totals.get("melee_damage_sum", 0.0)),
                    "melee_success_rate": float(run_phase29_totals.get("melee_success_count", 0.0)) / melee_den,
                    "melee_kills_per_attempt": float(run_phase29_totals.get("melee_kills_sum", 0.0)) / melee_den,
                    "melee_damage_per_attempt": float(run_phase29_totals.get("melee_damage_sum", 0.0)) / melee_den,
                    "converted_from_progress_rate": (
                        float(run_phase29_totals.get("conversion_total_steps", 0.0)) / conv_prog_den
                    ),
                    "converted_rate_near_vp": (
                        float(run_phase29_totals.get("xai_vp_capture_taken_steps", 0.0)) / cap_den
                    ),
                    "conversion_within_2_turns_after_progress": (
                        float(run_phase29_totals.get("conversion_within_2_after_progress", 0.0)) / conv_den
                    ),
                    "xai_decision_steps": float(run_phase29_totals.get("xai_decision_steps", 0.0)),
                    "xai_policy_confidence_mean": (
                        float(run_phase29_totals.get("xai_policy_confidence_sum", 0.0)) / xai_den
                    ),
                    "xai_policy_margin_mean": (
                        float(run_phase29_totals.get("xai_policy_margin_sum", 0.0)) / xai_den
                    ),
                    "xai_latent_signal_coverage": (
                        float(run_phase29_totals.get("xai_latent_signal_steps", 0.0)) / xai_den
                    ),
                    "xai_vp_capture_opportunity_steps": float(
                        run_phase29_totals.get("xai_vp_capture_opportunity_steps", 0.0)
                    ),
                    "xai_vp_capture_taken_steps": float(
                        run_phase29_totals.get("xai_vp_capture_taken_steps", 0.0)
                    ),
                    "xai_vp_capture_take_rate": (
                        float(run_phase29_totals.get("xai_vp_capture_taken_steps", 0.0)) / cap_den
                    ),
                    "vp_conversion_efficiency": (
                        float(run_phase29_totals.get("xai_vp_capture_taken_steps", 0.0)) / xai_den
                    ),
                    "timeout_rate_proxy": (
                        float(run_phase29_totals.get("timeout_steps", 0.0)) / xai_den
                    ),
                    "terminal_rate_proxy": (
                        float(run_phase29_totals.get("terminal_steps", 0.0)) / xai_den
                    ),
                }
                latest_metrics["phase_2_9_train_kpis"] = dict(phase29_train_kpis)
                if inference_service is not None:
                    inf_metrics = dict(inference_service.metrics_snapshot() or {})
                    latest_metrics["inference_service_kpis"] = inf_metrics
                    for key in (
                        "inference_latency_p50_ms",
                        "inference_latency_p95_ms",
                        "inference_queue_depth",
                        "inference_queue_depth_max",
                        "inference_staleness_proxy_steps",
                    ):
                        latest_metrics[key] = float(inf_metrics.get(key, 0.0))
                latest_metrics["xai_vp_capture_take_rate_train"] = float(
                    phase29_train_kpis["xai_vp_capture_take_rate"]
                )
                latest_metrics["vp_conversion_efficiency_train"] = float(
                    phase29_train_kpis["vp_conversion_efficiency"]
                )
                _mlflow_log_metrics(mlflow_mod, latest_metrics, step=int(it))
                event_bus.emit("TrainStepEvent", {"iteration": int(it), **latest_metrics})
                if events_writer is not None:
                    events_writer.append(
                        {"event_type": "TrainStepEvent", "payload": {"iteration": int(it), **latest_metrics}}
                    )

                ckpt_dir = run_dir / "checkpoints"
                ckpt_dir.mkdir(parents=True, exist_ok=True)
                ckpt_path = None
                should_save_iter = ((it + 1) % checkpoint_every == 0) or (it == iterations - 1)
                if should_save_iter:
                    ckpt_path = ckpt_dir / f"iter_{it}.pt"
                    _atomic_torch_save(model.state_dict(), ckpt_path)
                print(
                    "[EfficientZeroV2]   train "
                    f"loss={latest_metrics.get('loss', 0.0):.4f} "
                    f"policy={latest_metrics.get('policy_loss', 0.0):.4f} "
                    f"value={latest_metrics.get('value_loss', 0.0):.4f} "
                    f"reward={latest_metrics.get('reward_loss', 0.0):.4f} "
                    f"objective={latest_metrics.get('objective_loss', 0.0):.4f} "
                    f"consistency={latest_metrics.get('consistency_loss', 0.0):.6f}"
                )
                print(
                    f"[EfficientZeroV2]   timing selfplay_s={selfplay_elapsed_s:.2f} "
                    f"train_s={train_elapsed_s:.2f} iter_s={iter_elapsed_s:.2f}"
                )
                if ckpt_path is not None:
                    print(f"[EfficientZeroV2]   checkpoint={ckpt_path}")
                iter_timing_rows.append(
                    {
                        "iteration": int(it),
                        "selfplay_s": float(selfplay_elapsed_s),
                        "train_s": float(train_elapsed_s),
                        "iter_s": float(iter_elapsed_s),
                    }
                )

        total_elapsed_s = float(time.perf_counter() - t_total)
        latest_metrics["timing_summary"] = {
            "total_elapsed_s": total_elapsed_s,
            "selfplay_total_s": float(sum(r["selfplay_s"] for r in iter_timing_rows)),
            "train_total_s": float(sum(r["train_s"] for r in iter_timing_rows)),
            "iter_total_s": float(sum(r["iter_s"] for r in iter_timing_rows)),
            "iter_avg_s": float(sum(r["iter_s"] for r in iter_timing_rows) / max(1, len(iter_timing_rows))),
            "selfplay_avg_s": float(sum(r["selfplay_s"] for r in iter_timing_rows) / max(1, len(iter_timing_rows))),
            "train_avg_s": float(sum(r["train_s"] for r in iter_timing_rows) / max(1, len(iter_timing_rows))),
            "iterations": int(len(iter_timing_rows)),
        }
        latest_metrics["timing_by_iteration"] = list(iter_timing_rows)
        latest_metrics["short_episode_diagnostics"] = _episode_length_diagnostics(
            rows=short_episode_rows,
            threshold=short_episode_threshold,
        )
        latest_metrics["short_episode_rows_count"] = int(len(short_episode_rows))
        latest_metrics["iter_short_episode_diagnostics"] = list(iter_diagnostics_rows)
        latest_metrics["train_runtime_profile"] = {
            "post_train_analytics_enabled": bool(enable_post_train_analytics),
            "mode": "lean" if not enable_post_train_analytics else "full",
            "engine": "efficientzero_v2",
        }

        (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
        if bool(enable_post_train_analytics):
            (run_dir / "xai").mkdir(parents=True, exist_ok=True)
            (run_dir / "events").mkdir(parents=True, exist_ok=True)
        final_ckpt_path = run_dir / "checkpoints" / "final.pt"
        _atomic_torch_save(model.state_dict(), final_ckpt_path)
        # Keep only the final checkpoint to reduce disk usage.
        for iter_ckpt in (run_dir / "checkpoints").glob("iter_*.pt"):
            try:
                iter_ckpt.unlink()
            except Exception:
                pass
        (run_dir / "metrics" / "summary.json").write_text(
            json.dumps(latest_metrics, indent=2), encoding="utf-8"
        )
        (run_dir / "metrics" / "iter_short_episode_diagnostics.json").write_text(
            json.dumps(iter_diagnostics_rows, indent=2), encoding="utf-8"
        )
        units_sides = _build_units_sides_contract(
            samples=all_run_samples,
            latest_metrics=latest_metrics,
            scenario_id=scenario_id,
            run_id=run_id,
        )
        (run_dir / "metrics" / "units_sides.json").write_text(
            json.dumps(units_sides, indent=2),
            encoding="utf-8",
        )

        manifest = RunManifest(
            run_id=run_id,
            scenario_id=scenario_id,
            seed=seed,
            config={
                "iterations": iterations,
                "episodes_per_iter": episodes_per_iter,
                "batch_size": batch_size,
                "objective_loss_weight": objective_loss_weight,
                "objective_target_mode": objective_target_mode,
                "objective_pos_weight": objective_pos_weight,
                "objective_opportunity_max_dist": objective_opportunity_max_dist,
                "objective_signal": {
                    **dict(objective_signal_cfg),
                    "opportunity_near_vp_max_dist": objective_opportunity_near_vp_max_dist,
                },
                "objective_head": {
                    **dict(objective_head_cfg),
                    "progress_positive_threshold": objective_progress_positive_threshold,
                },
                "objective_reporting": {
                    **dict(objective_reporting_cfg),
                    "conversion_window_steps_after_progress": objective_conversion_window_steps,
                    "assault_advantage_prob_threshold": objective_assault_advantage_prob_threshold,
                    "assault_advantage_margin_threshold": objective_assault_advantage_margin_threshold,
                    "assault_advantage_legal_count_threshold": (
                        objective_assault_advantage_legal_count_threshold
                    ),
                    "assault_advantage_min_score": objective_assault_advantage_min_score,
                },
                "consistency_loss_weight": consistency_loss_weight,
                "consistency_unroll_steps": consistency_unroll_steps,
                "reanalysis_ratio": reanalysis_ratio,
                "reanalysis_value_mix": reanalysis_value_mix,
                "reanalysis_policy_mix": reanalysis_policy_mix,
                "value_bootstrap_steps": value_bootstrap_steps,
                "value_bootstrap_discount": value_bootstrap_discount,
                "amp_enabled": amp_enabled,
                "amp_dtype": amp_dtype,
                "compile_model": compile_model,
                "compile_mode": compile_mode,
                "matmul_precision": matmul_precision,
                "train_updates_per_iter": train_updates_per_iter,
                "checkpoint_every": checkpoint_every,
                "collect_xai": collect_xai,
                "short_episode_threshold": short_episode_threshold,
                "model": {
                    "encoder_type": encoder_type,
                    "observation_channels": observation_channels,
                    "observation_height": observation_height,
                    "observation_width": observation_width,
                    "hidden_dim": hidden_dim,
                    "action_dim": action_dim,
                    "dynamics_blocks": dynamics_blocks,
                    "prediction_blocks": prediction_blocks,
                    "device": device,
                },
                "selfplay": {
                    "device": selfplay_device,
                    "num_workers": num_workers,
                    "max_steps": max_steps,
                    "max_steps_override": max_steps_override,
                    "max_turns_override": max_turns_override,
                    "mcts_simulations": mcts_simulations,
                    "mcts_c_puct": mcts_c_puct,
                    "mcts_unroll_steps": mcts_unroll_steps,
                    "mcts_discount": mcts_discount,
                    "mcts_temperature": mcts_temperature,
                    "mcts_dirichlet_alpha": mcts_dirichlet_alpha,
                    "mcts_dirichlet_epsilon": mcts_dirichlet_epsilon,
                    "inference_cache_limit": inference_cache_limit,
                    "timeout_penalty": timeout_penalty,
                    "reward_shaping": dict(reward_shaping),
                    "collect_xai": collect_xai,
                },
                "config_preflight_warnings": list(config_preflight_warnings),
            },
        )
        manifest.write(run_dir / "run_manifest.json")
        print(f"[EfficientZeroV2] final_checkpoint={final_ckpt_path}")
        print(f"[EfficientZeroV2] completed run_dir={run_dir}")
        return {"run_id": run_id, "metrics": latest_metrics, "engine_mode": "efficient_core"}
    finally:
        if process_pool is not None:
            process_pool.shutdown(wait=True, cancel_futures=True)
        if inference_service is not None:
            inference_service.stop()

