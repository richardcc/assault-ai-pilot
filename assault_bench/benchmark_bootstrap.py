from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def bootstrap_checkpoint_runtime(
    *,
    cfg_benchmark: Dict[str, object],
    checkpoint_path: str,
    cfg_muzero_path: str,
    model_kind_hint: str,
    bench_device: str,
    mcts_q_clip_abs: float,
    mcts_q_root_normalization_mode: str,
    mcts_q_root_normalization_strength: float,
    mcts_value_rescale_mode: str,
    mcts_value_rescale_temperature: float,
    mcts_success_prob_enabled: bool,
    mcts_success_prob_alpha: float,
    mcts_success_prob_center: float,
    mcts_success_prob_scale: float,
    mcts_success_prob_centered_clip_abs: float,
    mcts_dirichlet_alpha: float,
    mcts_dirichlet_epsilon: float,
    mcts_min_root_visits_per_action: int,
    mcts_min_root_visits_top_n: int,
    unit_prefilter_enabled: bool,
    unit_prefilter_replan_enabled: bool,
    unit_prefilter_top_k: int,
    unit_prefilter_vp_progress_weight: float,
    unit_prefilter_capture_opportunity_weight: float,
    unit_prefilter_threat_weight: float,
    load_muzero_config_fn,
    load_state_dict_fn,
    muzero_network_cls,
    efficientzero_v2_network_cls,
) -> Dict[str, Any]:
    model = None
    model_kind = str(model_kind_hint or "")
    muz_cfg = None
    ckpt = None
    action_dim = 32
    mcts_unroll_steps = 1
    mcts_discount = 0.997
    reward_shaping_cfg: Dict[str, object] = {}
    if checkpoint_path:
        ckpt_run_id = ""
        try:
            ckpt_tmp = Path(checkpoint_path)
            if not ckpt_tmp.is_absolute():
                ckpt_tmp = (Path.cwd() / ckpt_tmp).resolve()
            ckpt_run_id = str(ckpt_tmp.parent.parent.name)
        except Exception:
            ckpt_run_id = ""
        model_kind = (
            "efficientzero_v2" if ckpt_run_id.startswith("efficientzero_v2_") else model_kind_hint
        )
        muz_cfg = load_muzero_config_fn(Path(cfg_muzero_path))
        reward_shaping_cfg = dict(muz_cfg.selfplay.get("reward_shaping", {}) or {})
        action_dim = int(muz_cfg.model["action_dim"])
        mcts_unroll_steps = int(muz_cfg.selfplay.get("mcts_unroll_steps", 1))
        mcts_discount = float(muz_cfg.selfplay.get("mcts_discount", 0.997))
        if "mcts_q_clip_abs" not in dict(cfg_benchmark):
            mcts_q_clip_abs = float(muz_cfg.selfplay.get("mcts_q_clip_abs", mcts_q_clip_abs))
        if "mcts_q_root_normalization_mode" not in dict(cfg_benchmark):
            mcts_q_root_normalization_mode = str(
                muz_cfg.selfplay.get(
                    "mcts_q_root_normalization_mode",
                    mcts_q_root_normalization_mode,
                )
            )
        if "mcts_q_root_normalization_strength" not in dict(cfg_benchmark):
            mcts_q_root_normalization_strength = float(
                muz_cfg.selfplay.get(
                    "mcts_q_root_normalization_strength",
                    mcts_q_root_normalization_strength,
                )
            )
        if "mcts_value_rescale_mode" not in dict(cfg_benchmark):
            mcts_value_rescale_mode = str(
                muz_cfg.selfplay.get("mcts_value_rescale_mode", mcts_value_rescale_mode)
            )
        if "mcts_value_rescale_temperature" not in dict(cfg_benchmark):
            mcts_value_rescale_temperature = float(
                muz_cfg.selfplay.get(
                    "mcts_value_rescale_temperature",
                    mcts_value_rescale_temperature,
                )
            )
        if "mcts_success_prob_enabled" not in dict(cfg_benchmark):
            mcts_success_prob_enabled = bool(
                muz_cfg.selfplay.get("mcts_success_prob_enabled", mcts_success_prob_enabled)
            )
        if "mcts_success_prob_alpha" not in dict(cfg_benchmark):
            mcts_success_prob_alpha = float(
                muz_cfg.selfplay.get("mcts_success_prob_alpha", mcts_success_prob_alpha)
            )
        if "mcts_success_prob_center" not in dict(cfg_benchmark):
            mcts_success_prob_center = float(
                muz_cfg.selfplay.get("mcts_success_prob_center", mcts_success_prob_center)
            )
        if "mcts_success_prob_scale" not in dict(cfg_benchmark):
            mcts_success_prob_scale = float(
                muz_cfg.selfplay.get("mcts_success_prob_scale", mcts_success_prob_scale)
            )
        if "mcts_success_prob_centered_clip_abs" not in dict(cfg_benchmark):
            mcts_success_prob_centered_clip_abs = float(
                muz_cfg.selfplay.get(
                    "mcts_success_prob_centered_clip_abs",
                    mcts_success_prob_centered_clip_abs,
                )
            )
        if "mcts_dirichlet_alpha" not in dict(cfg_benchmark):
            mcts_dirichlet_alpha = float(
                muz_cfg.selfplay.get("mcts_dirichlet_alpha", mcts_dirichlet_alpha)
            )
        if "mcts_dirichlet_epsilon" not in dict(cfg_benchmark):
            mcts_dirichlet_epsilon = float(
                muz_cfg.selfplay.get("mcts_dirichlet_epsilon", mcts_dirichlet_epsilon)
            )
        if "mcts_min_root_visits_per_action" not in dict(cfg_benchmark):
            mcts_min_root_visits_per_action = int(
                muz_cfg.selfplay.get(
                    "mcts_min_root_visits_per_action",
                    mcts_min_root_visits_per_action,
                )
                or mcts_min_root_visits_per_action
            )
        if "mcts_min_root_visits_top_n" not in dict(cfg_benchmark):
            mcts_min_root_visits_top_n = int(
                muz_cfg.selfplay.get(
                    "mcts_min_root_visits_top_n",
                    mcts_min_root_visits_top_n,
                )
                or mcts_min_root_visits_top_n
            )
        if "unit_prefilter_enabled" not in dict(cfg_benchmark):
            unit_prefilter_enabled = bool(muz_cfg.selfplay.get("unit_prefilter_enabled", unit_prefilter_enabled))
        if "unit_prefilter_replan_enabled" not in dict(cfg_benchmark):
            unit_prefilter_replan_enabled = bool(
                muz_cfg.selfplay.get("unit_prefilter_replan_enabled", unit_prefilter_replan_enabled)
            )
        if "unit_prefilter_top_k" not in dict(cfg_benchmark):
            unit_prefilter_top_k = int(
                muz_cfg.selfplay.get("unit_prefilter_top_k", unit_prefilter_top_k) or unit_prefilter_top_k
            )
        if "unit_prefilter_vp_progress_weight" not in dict(cfg_benchmark):
            unit_prefilter_vp_progress_weight = float(
                muz_cfg.selfplay.get(
                    "unit_prefilter_vp_progress_weight",
                    unit_prefilter_vp_progress_weight,
                )
            )
        if "unit_prefilter_capture_opportunity_weight" not in dict(cfg_benchmark):
            unit_prefilter_capture_opportunity_weight = float(
                muz_cfg.selfplay.get(
                    "unit_prefilter_capture_opportunity_weight",
                    unit_prefilter_capture_opportunity_weight,
                )
            )
        if "unit_prefilter_threat_weight" not in dict(cfg_benchmark):
            unit_prefilter_threat_weight = float(
                muz_cfg.selfplay.get("unit_prefilter_threat_weight", unit_prefilter_threat_weight)
            )
        model_cls = efficientzero_v2_network_cls if model_kind == "efficientzero_v2" else muzero_network_cls
        model = model_cls(
            observation_dim=int(muz_cfg.model["observation_dim"]),
            hidden_dim=int(muz_cfg.model["hidden_dim"]),
            action_dim=action_dim,
            encoder_type=str(muz_cfg.model.get("encoder_type", "mlp")),
            observation_channels=int(muz_cfg.model.get("observation_channels", 8)),
            observation_height=int(muz_cfg.model.get("observation_height", 16)),
            observation_width=int(muz_cfg.model.get("observation_width", 16)),
            dynamics_blocks=int(muz_cfg.model.get("dynamics_blocks", 1)),
            prediction_blocks=int(muz_cfg.model.get("prediction_blocks", 1)),
        )
        ckpt = Path(checkpoint_path)
        if not ckpt.is_absolute():
            ckpt = (Path.cwd() / ckpt).resolve()
        state_dict = load_state_dict_fn(ckpt, bench_device)
        model.load_state_dict(state_dict, strict=False)
        if bench_device == "cuda":
            model = model.to("cuda")
        model.eval()

    return {
        "model": model,
        "model_kind": model_kind,
        "muz_cfg": muz_cfg,
        "ckpt": ckpt,
        "action_dim": action_dim,
        "mcts_unroll_steps": mcts_unroll_steps,
        "mcts_discount": mcts_discount,
        "reward_shaping_cfg": reward_shaping_cfg,
        "mcts_q_clip_abs": mcts_q_clip_abs,
        "mcts_q_root_normalization_mode": mcts_q_root_normalization_mode,
        "mcts_q_root_normalization_strength": mcts_q_root_normalization_strength,
        "mcts_value_rescale_mode": mcts_value_rescale_mode,
        "mcts_value_rescale_temperature": mcts_value_rescale_temperature,
        "mcts_success_prob_enabled": mcts_success_prob_enabled,
        "mcts_success_prob_alpha": mcts_success_prob_alpha,
        "mcts_success_prob_center": mcts_success_prob_center,
        "mcts_success_prob_scale": mcts_success_prob_scale,
        "mcts_success_prob_centered_clip_abs": mcts_success_prob_centered_clip_abs,
        "mcts_dirichlet_alpha": mcts_dirichlet_alpha,
        "mcts_dirichlet_epsilon": mcts_dirichlet_epsilon,
        "mcts_min_root_visits_per_action": mcts_min_root_visits_per_action,
        "mcts_min_root_visits_top_n": mcts_min_root_visits_top_n,
        "unit_prefilter_enabled": unit_prefilter_enabled,
        "unit_prefilter_replan_enabled": unit_prefilter_replan_enabled,
        "unit_prefilter_top_k": unit_prefilter_top_k,
        "unit_prefilter_vp_progress_weight": unit_prefilter_vp_progress_weight,
        "unit_prefilter_capture_opportunity_weight": unit_prefilter_capture_opportunity_weight,
        "unit_prefilter_threat_weight": unit_prefilter_threat_weight,
    }

