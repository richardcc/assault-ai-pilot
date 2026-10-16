from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.muzero.core.network import MuZeroNetwork
from agents.muzero.core.selfplay import MuZeroVOECAdapter
from voec_sim.core.simulator import VOECSimulator

_MODEL_CACHE: dict[str, Any] = {}


def _model_cache_key(*, payload: dict, bench_device: str) -> str:
    model_kind = str(payload.get("model_kind", "muzero")).strip().lower()
    ckpt_path = str(payload.get("checkpoint_path", "") or "").strip()
    model_cfg = dict(payload.get("model", {}) or {})
    return "|".join(
        [
            model_kind,
            bench_device,
            ckpt_path,
            str(model_cfg.get("observation_dim", "")),
            str(model_cfg.get("hidden_dim", "")),
            str(model_cfg.get("action_dim", "")),
            str(model_cfg.get("encoder_type", "")),
            str(model_cfg.get("observation_channels", "")),
            str(model_cfg.get("observation_height", "")),
            str(model_cfg.get("observation_width", "")),
            str(model_cfg.get("dynamics_blocks", "")),
            str(model_cfg.get("prediction_blocks", "")),
        ]
    )


def execute_benchmark_seed_task(
    *,
    payload: dict,
    load_state_dict_fn: Callable[[str, str], dict],
    run_episode_with_policy_fn: Callable[..., Any],
) -> Any:
    t_total_started = time.perf_counter()
    model_load_s = 0.0
    from voec_sim.assets_bridge.importers import AssetPaths

    assets = AssetPaths(
        root=Path(payload["assets"]["root"]),
        unit_catalog=Path(payload["assets"]["unit_catalog"]),
        map_piece_catalog=Path(payload["assets"]["map_piece_catalog"]),
        scenarios_dir=Path(payload["assets"]["scenarios_dir"]),
    )
    sim = VOECSimulator(assets=assets)
    adapter = MuZeroVOECAdapter(sim)
    model = payload.get("shared_model_proxy", None)
    bench_device = str(payload.get("bench_device", "cpu")).strip().lower()
    if model is None and payload.get("checkpoint_path"):
        t_model_load_started = time.perf_counter()
        cache_key = _model_cache_key(payload=payload, bench_device=bench_device)
        cached_model = _MODEL_CACHE.get(cache_key, None)
        if cached_model is not None:
            model = cached_model
        else:
            model_kind = str(payload.get("model_kind", "muzero")).strip().lower()
            model_cls = (
                EfficientZeroV2Network if model_kind == "efficientzero_v2" else MuZeroNetwork
            )
            model = model_cls(
                observation_dim=int(payload["model"]["observation_dim"]),
                hidden_dim=int(payload["model"]["hidden_dim"]),
                action_dim=int(payload["model"]["action_dim"]),
                encoder_type=str(payload["model"].get("encoder_type", "mlp")),
                observation_channels=int(payload["model"].get("observation_channels", 8)),
                observation_height=int(payload["model"].get("observation_height", 16)),
                observation_width=int(payload["model"].get("observation_width", 16)),
                dynamics_blocks=int(payload["model"].get("dynamics_blocks", 1)),
                prediction_blocks=int(payload["model"].get("prediction_blocks", 1)),
            )
            state_dict = load_state_dict_fn(payload["checkpoint_path"], bench_device)
            model.load_state_dict(state_dict)
            if bench_device == "cuda":
                model = model.to("cuda")
            model.eval()
            _MODEL_CACHE[cache_key] = model
        model_load_s = float(max(0.0, time.perf_counter() - t_model_load_started))
    t0 = time.perf_counter()
    out = run_episode_with_policy_fn(
        adapter=adapter,
        scenario_id=payload["scenario_id"],
        seed=payload["seed"],
        policy_name=payload["policy_name"],
        policy_by_side=dict(payload.get("policy_by_side", {}) or {}),
        max_steps=payload["max_steps"],
        max_steps_override=int(payload.get("max_steps_override", 0)),
        mcts_simulations=payload["mcts_simulations"],
        mcts_c_puct=payload["mcts_c_puct"],
        mcts_temperature=payload["mcts_temperature"],
        mcts_dirichlet_alpha=float(payload.get("mcts_dirichlet_alpha", 0.3)),
        mcts_dirichlet_epsilon=float(payload.get("mcts_dirichlet_epsilon", 0.0)),
        mcts_q_clip_abs=float(payload.get("mcts_q_clip_abs", 10.0)),
        mcts_q_root_normalization_mode=str(
            payload.get("mcts_q_root_normalization_mode", "adaptive_minmax")
        ),
        mcts_q_root_normalization_strength=float(
            payload.get("mcts_q_root_normalization_strength", 0.35)
        ),
        mcts_value_rescale_mode=str(payload.get("mcts_value_rescale_mode", "tanh")),
        mcts_value_rescale_temperature=float(
            payload.get("mcts_value_rescale_temperature", 10.0)
        ),
        mcts_success_prob_enabled=bool(payload.get("mcts_success_prob_enabled", False)),
        mcts_success_prob_alpha=float(payload.get("mcts_success_prob_alpha", 0.0)),
        mcts_success_prob_center=float(payload.get("mcts_success_prob_center", 0.5)),
        mcts_success_prob_scale=float(payload.get("mcts_success_prob_scale", 0.5)),
        mcts_success_prob_centered_clip_abs=float(
            payload.get("mcts_success_prob_centered_clip_abs", 1.0)
        ),
        mcts_min_root_visits_per_action=int(
            payload.get("mcts_min_root_visits_per_action", 0)
        ),
        mcts_min_root_visits_top_n=int(payload.get("mcts_min_root_visits_top_n", 0)),
        model=model,
        action_dim=int(payload.get("action_dim", 32)),
        mcts_unroll_steps=int(payload.get("mcts_unroll_steps", 1)),
        mcts_discount=float(payload.get("mcts_discount", 0.997)),
        collect_flow_metrics=bool(payload.get("collect_flow_metrics", True)),
        decision_top_k=payload.get("decision_top_k", None),
        unit_prefilter_enabled=bool(payload.get("unit_prefilter_enabled", False)),
        unit_prefilter_replan_enabled=bool(
            payload.get("unit_prefilter_replan_enabled", False)
        ),
        unit_prefilter_top_k=int(payload.get("unit_prefilter_top_k", 1)),
        unit_prefilter_vp_progress_weight=float(
            payload.get("unit_prefilter_vp_progress_weight", 1.0)
        ),
        unit_prefilter_capture_opportunity_weight=float(
            payload.get("unit_prefilter_capture_opportunity_weight", 2.0)
        ),
        unit_prefilter_threat_weight=float(
            payload.get("unit_prefilter_threat_weight", 0.25)
        ),
        reward_shaping=dict(payload.get("reward_shaping", {}) or {}),
        trace_detail_level=str(payload.get("trace_detail_level", "core") or "core"),
    )
    episode_s = float(max(0.0, time.perf_counter() - t0))
    total_s = float(max(0.0, time.perf_counter() - t_total_started))
    timing_meta = {
        "startup_s": float(max(0.0, total_s - episode_s)),
        "model_load_s": float(max(0.0, model_load_s)),
        "episode_s": float(episode_s),
        "total_s": float(total_s),
    }
    if isinstance(out, tuple):
        return tuple(list(out) + [total_s, timing_meta])
    if isinstance(out, list):
        return list(out) + [total_s, timing_meta]
    return out
