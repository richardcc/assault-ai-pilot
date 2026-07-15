from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import nullcontext
import json
import os
import time
import uuid
from pathlib import Path

import torch

from agents.muzero.configs.config_loader import load_muzero_config
from agents.muzero.adapter_voec import MuZeroVOECAdapter
from agents.muzero.core.network import MuZeroNetwork
from agents.muzero.core.replay import ReplayBuffer
from agents.muzero.core.selfplay import play_episode
from agents.muzero.obs.event_bus import EventBus
from agents.muzero.obs.contracts import (
    DecisionEvent,
    SearchEvent,
    TrainStepEvent,
    TransitionEvent,
)
from agents.muzero.obs.jsonl_writer import JsonlWriter
from agents.muzero.obs.run_manifest import RunManifest
from agents.muzero.train.trainer import MuZeroTrainer
from agents.muzero.xai.decision_report import build_decision_report
from agents.muzero.xai.episode_narrative import build_episode_narrative
from agents.muzero.xai.search_tree_snapshot import build_search_snapshot
from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator


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


def _tracked_side_from_scenario(scenarios_dir: Path, scenario_id: str) -> str:
    scenario_path = (Path(scenarios_dir) / f"{str(scenario_id).strip()}.json").resolve()
    if not scenario_path.exists():
        return ""
    try:
        payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    victory = dict(payload.get("victory_outcomes", {}) or {})
    return str(victory.get("tracked_side", "")).strip().upper()


def _channel_name(index: int) -> str:
    names = {
        0: "ally_presence",
        1: "enemy_presence",
        2: "ally_hp_norm",
        3: "enemy_hp_norm",
        4: "ally_alive",
        5: "enemy_alive",
        6: "turn_norm",
        7: "done_flag",
        8: "ally_infantry",
        9: "enemy_infantry",
        10: "ally_support",
        11: "enemy_support",
        12: "map_playable",
        13: "vp_mask",
        14: "vp_owner_relative",
        15: "terrain_move_cost_norm",
        16: "terrain_cover_norm",
        17: "terrain_los_block",
        18: "vp_distance_inv",
        19: "q_coord_norm",
        20: "r_coord_norm",
        21: "has_vp_owner",
        22: "ally_mobility_norm",
        23: "enemy_mobility_norm",
        24: "ally_direct_range_norm",
        25: "enemy_direct_range_norm",
        26: "ally_indirect_range_norm",
        27: "enemy_indirect_range_norm",
        28: "ally_attack_power_norm",
        29: "enemy_attack_power_norm",
        30: "ally_defense_power_norm",
        31: "enemy_defense_power_norm",
    }
    return names.get(index, f"channel_{index}")


def _assault_advantage_bucket(
    *,
    chosen_action_prob: float,
    mcts_margin: float,
    legal_attack_options: int,
    attack_target_cover_mean: float,
    prob_threshold: float = 0.55,
    margin_threshold: float = 0.20,
    cover_max: float = 0.35,
    min_score: int = 3,
) -> str:
    score = 0
    if float(chosen_action_prob) >= float(prob_threshold):
        score += 1
    if float(mcts_margin) >= float(margin_threshold):
        score += 1
    if int(legal_attack_options) >= 1:
        score += 1
    cover = float(attack_target_cover_mean)
    if cover >= 0.0 and cover <= float(cover_max):
        score += 1
    return "favorable" if score >= int(min_score) else "unfavorable"


def _selfplay_worker_task(payload: dict):
    from voec_sim.assets_bridge.importers import AssetPaths

    assets = AssetPaths(
        root=Path(payload["assets"]["root"]),
        unit_catalog=Path(payload["assets"]["unit_catalog"]),
        map_piece_catalog=Path(payload["assets"]["map_piece_catalog"]),
        scenarios_dir=Path(payload["assets"]["scenarios_dir"]),
    )
    sim = VOECSimulator(assets=assets)
    adapter = MuZeroVOECAdapter(sim)

    model = MuZeroNetwork(
        observation_dim=payload["model"]["observation_dim"],
        hidden_dim=payload["model"]["hidden_dim"],
        action_dim=payload["model"]["action_dim"],
        encoder_type=payload["model"].get("encoder_type", "mlp"),
        observation_channels=payload["model"].get("observation_channels", 8),
        observation_height=payload["model"].get("observation_height", 16),
        observation_width=payload["model"].get("observation_width", 16),
        dynamics_blocks=payload["model"].get("dynamics_blocks", 1),
        prediction_blocks=payload["model"].get("prediction_blocks", 1),
    )
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    samples = play_episode(
        adapter=adapter,
        scenario_id=payload["scenario_id"],
        seed=payload["seed"],
        max_steps=payload["selfplay"]["max_steps"],
        max_steps_override=payload["selfplay"].get("max_steps_override", 0),
        action_dim=payload["model"]["action_dim"],
        model=model,
        mcts_simulations=payload["selfplay"]["mcts_simulations"],
        mcts_c_puct=payload["selfplay"]["mcts_c_puct"],
        mcts_unroll_steps=payload["selfplay"]["mcts_unroll_steps"],
        mcts_discount=payload["selfplay"]["mcts_discount"],
        mcts_temperature=payload["selfplay"]["mcts_temperature"],
        mcts_dirichlet_alpha=payload["selfplay"]["mcts_dirichlet_alpha"],
        mcts_dirichlet_epsilon=payload["selfplay"]["mcts_dirichlet_epsilon"],
        inference_cache_limit=int(payload["selfplay"].get("inference_cache_limit", 2048)),
        progress_log_every=int(payload["selfplay"].get("progress_log_every", 0)),
        log_episode_end=bool(payload["selfplay"].get("log_episode_end", False)),
        timeout_penalty=payload["selfplay"]["timeout_penalty"],
        log_units_snapshot=bool(payload["selfplay"].get("log_units_snapshot", False)),
        reward_shaping=payload["selfplay"]["reward_shaping"],
        objective_opportunity_near_vp_max_dist=float(
            payload["selfplay"].get("objective_opportunity_near_vp_max_dist", 2.0)
        ),
        collect_xai=bool(payload["selfplay"].get("collect_xai", True)),
    )
    return payload["ep_index"], samples


def _resolve_device(device_cfg: str) -> str:
    val = str(device_cfg).strip().lower()
    if val == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if val == "cuda" and not torch.cuda.is_available():
        print("[MuZero] requested cuda but unavailable, falling back to cpu")
        return "cpu"
    return "cuda" if val == "cuda" else "cpu"


def _benchmark_model_device(
    observation_dim: int,
    hidden_dim: int,
    action_dim: int,
    encoder_type: str = "mlp",
    observation_channels: int = 8,
    observation_height: int = 16,
    observation_width: int = 16,
    dynamics_blocks: int = 1,
    prediction_blocks: int = 1,
    steps: int = 30,
) -> str:
    if not torch.cuda.is_available():
        print("[MuZero] auto-device: cuda unavailable -> cpu")
        return "cpu"

    def run_once(device: str) -> float:
        model = MuZeroNetwork(
            observation_dim=observation_dim,
            hidden_dim=hidden_dim,
            action_dim=action_dim,
            encoder_type=encoder_type,
            observation_channels=observation_channels,
            observation_height=observation_height,
            observation_width=observation_width,
            dynamics_blocks=dynamics_blocks,
            prediction_blocks=prediction_blocks,
        ).to(device)
        if str(encoder_type).lower() == "cnn":
            obs = torch.randn(
                1,
                int(observation_channels),
                int(observation_height),
                int(observation_width),
                device=device,
            )
        else:
            obs = torch.randn(1, observation_dim, device=device)
        action = torch.zeros(1, action_dim, device=device)
        action[0, 0] = 1.0

        # Warmup
        with torch.no_grad():
            hidden, _, _, _ = model.initial_inference(obs)
            model.recurrent_inference(hidden, action)

        if device == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            for _ in range(steps):
                hidden, _, _, _ = model.initial_inference(obs)
                model.recurrent_inference(hidden, action)
        if device == "cuda":
            torch.cuda.synchronize()
        return time.perf_counter() - t0

    cpu_t = run_once("cpu")
    cuda_t = run_once("cuda")
    chosen = "cuda" if cuda_t < cpu_t else "cpu"
    print(
        "[MuZero] auto-device benchmark "
        f"cpu_s={cpu_t:.4f} cuda_s={cuda_t:.4f} -> {chosen}"
    )
    return chosen


def run_training(
    config_path: str = "agents/muzero/configs/muzero_config.yaml",
    mlflow_experiment: str = "assault_muzero",
    mlflow_run_name: str = "",
) -> dict:
    cfg = load_muzero_config(Path(config_path))
    voec_cfg_path = Path(cfg.paths["voec_config"])
    voec_cfg = load_voec_config(voec_cfg_path)

    scenario_id = str(cfg.scenario["id"])
    seed = int(cfg.scenario["seed"])
    objective_tracked_side = _tracked_side_from_scenario(
        Path(voec_cfg.assets.scenarios_dir), scenario_id
    )
    iterations = int(cfg.train["iterations"])
    episodes_per_iter = int(cfg.train["episodes_per_iter"])
    batch_size = int(cfg.train["batch_size"])

    action_dim = int(cfg.model["action_dim"])
    observation_dim = int(cfg.model["observation_dim"])
    encoder_type = str(cfg.model.get("encoder_type", "mlp"))
    observation_channels = int(cfg.model.get("observation_channels", 8))
    observation_height = int(cfg.model.get("observation_height", 16))
    observation_width = int(cfg.model.get("observation_width", 16))
    hidden_dim = int(cfg.model["hidden_dim"])
    dynamics_blocks = int(cfg.model.get("dynamics_blocks", 1))
    prediction_blocks = int(cfg.model.get("prediction_blocks", 1))
    num_workers = int(cfg.selfplay.get("num_workers", 1))
    device_cfg = str(cfg.model.get("device", "auto"))
    device = _resolve_device(device_cfg)
    if device_cfg.strip().lower() == "auto":
        bench_steps = int(cfg.model.get("device_benchmark_steps", 30))
        device = _benchmark_model_device(
            observation_dim=observation_dim,
            hidden_dim=hidden_dim,
            action_dim=action_dim,
            encoder_type=encoder_type,
            observation_channels=observation_channels,
            observation_height=observation_height,
            observation_width=observation_width,
            dynamics_blocks=dynamics_blocks,
            prediction_blocks=prediction_blocks,
            steps=bench_steps,
        )
    max_steps = int(cfg.selfplay["max_steps"])
    max_steps_override = int(cfg.selfplay.get("max_steps_override", 0))
    mcts_simulations = int(cfg.selfplay["mcts_simulations"])
    mcts_c_puct = float(cfg.selfplay["mcts_c_puct"])
    mcts_unroll_steps = int(cfg.selfplay.get("mcts_unroll_steps", 1))
    mcts_discount = float(cfg.selfplay.get("mcts_discount", 0.997))
    mcts_temperature = float(cfg.selfplay.get("mcts_temperature", 1.0))
    mcts_dirichlet_alpha = float(cfg.selfplay.get("mcts_dirichlet_alpha", 0.3))
    mcts_dirichlet_epsilon = float(cfg.selfplay.get("mcts_dirichlet_epsilon", 0.0))
    inference_cache_limit = int(cfg.selfplay.get("inference_cache_limit", 2048))
    progress_log_every = int(cfg.selfplay.get("progress_log_every", 0))
    log_episode_end = bool(cfg.selfplay.get("log_episode_end", False))
    timeout_penalty = float(cfg.selfplay.get("timeout_penalty", -0.1))
    log_units_snapshot = bool(cfg.selfplay.get("log_units_snapshot", False))
    reward_shaping = dict(cfg.selfplay.get("reward_shaping", {}) or {})
    enable_post_train_analytics = bool(cfg.train.get("enable_post_train_analytics", False))
    checkpoint_every = int(cfg.train.get("checkpoint_every", 1))
    checkpoint_every = max(1, checkpoint_every)
    objective_loss_weight = float(cfg.train.get("objective_loss_weight", 0.30))
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
    objective_near_vp_max_dist = float(
        objective_reporting_cfg.get("near_vp_max_dist", objective_opportunity_near_vp_max_dist)
    )
    objective_strong_progress_delta_threshold = float(
        objective_reporting_cfg.get("strong_progress_delta_threshold", 2.0)
    )
    objective_high_confidence_prob_threshold = float(
        objective_reporting_cfg.get("high_confidence_prob_threshold", 0.60)
    )
    objective_high_confidence_margin_threshold = float(
        objective_reporting_cfg.get("high_confidence_margin_threshold", 0.25)
    )
    assault_advantage_prob_threshold = float(
        objective_reporting_cfg.get("assault_advantage_prob_threshold", 0.55)
    )
    assault_advantage_margin_threshold = float(
        objective_reporting_cfg.get("assault_advantage_margin_threshold", 0.20)
    )
    assault_advantage_cover_max = float(
        objective_reporting_cfg.get("assault_advantage_cover_max", 0.35)
    )
    assault_advantage_min_score = int(
        objective_reporting_cfg.get("assault_advantage_min_score", 3)
    )
    decision_flip_legal_count_tolerance = int(
        objective_reporting_cfg.get("decision_flip_legal_count_tolerance", 2)
    )

    run_root = Path(str(cfg.paths["run_root"]))
    run_id = f"muzero_{uuid.uuid4().hex[:8]}"
    run_dir = run_root / run_id
    print(f"[MuZero] run_id={run_id}")
    print(f"[MuZero] config={config_path}")
    print(f"[MuZero] scenario={scenario_id} seed={seed}")
    print(f"[MuZero] device={device}")
    print(f"[MuZero] selfplay_workers={num_workers}")
    events_writer = None
    if bool(enable_post_train_analytics):
        (run_dir / "events").mkdir(parents=True, exist_ok=True)
        events_writer = JsonlWriter(run_dir / "events" / "train_events.jsonl")
    event_bus = EventBus(enabled=enable_post_train_analytics)

    sim = VOECSimulator(assets=voec_cfg.assets)
    adapter = MuZeroVOECAdapter(sim)
    model = MuZeroNetwork(
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
    trainer = MuZeroTrainer(
        model=model,
        lr=float(cfg.model["learning_rate"]),
        device=device,
        objective_loss_weight=objective_loss_weight,
        objective_target_mode=objective_target_mode,
        objective_pos_weight=objective_pos_weight,
        objective_opportunity_max_dist=objective_opportunity_max_dist,
        objective_progress_positive_threshold=objective_progress_positive_threshold,
    )
    model = trainer.model
    replay = ReplayBuffer(
        capacity=int(cfg.train["replay_capacity"]),
        recent_fraction=float(cfg.train.get("replay_recent_fraction", 0.7)),
        recent_window_ratio=float(cfg.train.get("replay_recent_window_ratio", 0.3)),
    )
    resume_checkpoint = str(cfg.train.get("resume_checkpoint", "")).strip()
    if resume_checkpoint:
        ckpt_path = Path(resume_checkpoint)
        if not ckpt_path.is_absolute():
            ckpt_path = (Path.cwd() / ckpt_path).resolve()
        if not ckpt_path.exists():
            raise FileNotFoundError(f"Resume checkpoint not found: {ckpt_path}")
        state_dict = torch.load(ckpt_path, map_location="cpu")
        model.load_state_dict(state_dict)
        print(f"[MuZero] resumed_from={ckpt_path}")

    manifest = RunManifest(
        run_id=run_id,
        scenario_id=scenario_id,
        seed=seed,
        config={
            "iterations": iterations,
            "episodes_per_iter": episodes_per_iter,
            "batch_size": batch_size,
            "checkpoint_every": checkpoint_every,
            "resume_checkpoint": resume_checkpoint,
            "objective_loss_weight": float(objective_loss_weight),
            "objective_target_mode": str(objective_target_mode),
            "objective_pos_weight": float(objective_pos_weight),
            "objective_opportunity_max_dist": float(objective_opportunity_max_dist),
            "objective_signal": {
                "opportunity_near_vp_max_dist": float(objective_opportunity_near_vp_max_dist),
            },
            "objective_head": {
                "progress_positive_threshold": float(objective_progress_positive_threshold),
            },
            "objective_reporting": {
                "near_vp_max_dist": float(objective_near_vp_max_dist),
                "strong_progress_delta_threshold": float(objective_strong_progress_delta_threshold),
                "high_confidence_prob_threshold": float(objective_high_confidence_prob_threshold),
                "high_confidence_margin_threshold": float(objective_high_confidence_margin_threshold),
                "assault_advantage_prob_threshold": float(assault_advantage_prob_threshold),
                "assault_advantage_margin_threshold": float(assault_advantage_margin_threshold),
                "assault_advantage_cover_max": float(assault_advantage_cover_max),
                "assault_advantage_min_score": int(assault_advantage_min_score),
                "decision_flip_legal_count_tolerance": int(decision_flip_legal_count_tolerance),
            },
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
                "num_workers": num_workers,
                "mcts_simulations": mcts_simulations,
                "mcts_c_puct": mcts_c_puct,
                "mcts_temperature": mcts_temperature,
            },
            "reaction_fire_enabled": str(
                os.getenv("ASSAULT_ENABLE_REACTION_FIRE", "1")
            ).strip(),
            "objective_tracked_side": str(objective_tracked_side),
        },
    )
    manifest.write(run_dir / "run_manifest.json")
    mlflow_mod, mlflow_ctx = _start_mlflow_run(
        experiment_name=str(mlflow_experiment),
        run_name=(str(mlflow_run_name).strip() or run_id),
    )
    _mlflow_log_params(
        mlflow_mod,
        {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "seed": seed,
            "config_path": config_path,
            "device": device,
            "iterations": iterations,
            "episodes_per_iter": episodes_per_iter,
            "batch_size": batch_size,
            "checkpoint_every": checkpoint_every,
            "mcts_simulations": mcts_simulations,
            "mcts_c_puct": mcts_c_puct,
            "encoder_type": encoder_type,
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
            "near_vp_max_dist": objective_near_vp_max_dist,
            "strong_progress_delta_threshold": objective_strong_progress_delta_threshold,
            "high_confidence_prob_threshold": objective_high_confidence_prob_threshold,
            "high_confidence_margin_threshold": objective_high_confidence_margin_threshold,
            "assault_advantage_prob_threshold": assault_advantage_prob_threshold,
            "assault_advantage_margin_threshold": assault_advantage_margin_threshold,
            "assault_advantage_cover_max": assault_advantage_cover_max,
            "assault_advantage_min_score": assault_advantage_min_score,
            "decision_flip_legal_count_tolerance": decision_flip_legal_count_tolerance,
        },
            "objective_tracked_side": str(objective_tracked_side),
        },
    )

    latest_metrics = {}
    episode_rewards = []
    episode_actions = []
    run_t0 = time.perf_counter()
    iter_timing_rows: list[dict] = []
    for it in range(iterations):
        iter_t0 = time.perf_counter()
        selfplay_t0 = time.perf_counter()
        print(f"[MuZero] iteration {it + 1}/{iterations} - selfplay")
        if num_workers > 1 and device == "cpu":
            model_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
            payloads = []
            for ep in range(episodes_per_iter):
                payloads.append(
                    {
                        "ep_index": ep,
                        "scenario_id": scenario_id,
                        "seed": seed + it + ep,
                        "assets": {
                            "root": str(voec_cfg.assets.root),
                            "unit_catalog": str(voec_cfg.assets.unit_catalog),
                            "map_piece_catalog": str(voec_cfg.assets.map_piece_catalog),
                            "scenarios_dir": str(voec_cfg.assets.scenarios_dir),
                        },
                        "model": {
                            "observation_dim": observation_dim,
                            "hidden_dim": hidden_dim,
                            "action_dim": action_dim,
                            "encoder_type": encoder_type,
                            "observation_channels": observation_channels,
                            "observation_height": observation_height,
                            "observation_width": observation_width,
                            "dynamics_blocks": dynamics_blocks,
                            "prediction_blocks": prediction_blocks,
                        },
                        "model_state_dict": model_state,
                        "selfplay": {
                            "max_steps": max_steps,
                            "max_steps_override": max_steps_override,
                            "mcts_simulations": mcts_simulations,
                            "mcts_c_puct": mcts_c_puct,
                            "mcts_unroll_steps": mcts_unroll_steps,
                            "mcts_discount": mcts_discount,
                            "mcts_temperature": mcts_temperature,
                            "mcts_dirichlet_alpha": mcts_dirichlet_alpha,
                            "mcts_dirichlet_epsilon": mcts_dirichlet_epsilon,
                            "inference_cache_limit": inference_cache_limit,
                            "progress_log_every": progress_log_every,
                            "log_episode_end": bool(log_episode_end),
                            "timeout_penalty": timeout_penalty,
                            "log_units_snapshot": bool(log_units_snapshot),
                            "reward_shaping": reward_shaping,
                            "objective_opportunity_near_vp_max_dist": objective_opportunity_near_vp_max_dist,
                            "collect_xai": bool(enable_post_train_analytics),
                        },
                    }
                )
            results = {}
            with ProcessPoolExecutor(max_workers=num_workers) as ex:
                futures = [ex.submit(_selfplay_worker_task, p) for p in payloads]
                for fut in as_completed(futures):
                    ep_idx, samples = fut.result()
                    results[ep_idx] = samples
            for ep in range(episodes_per_iter):
                samples = results[ep]
                replay.extend(samples)
                episode_rewards.append(sum(s.reward_target for s in samples))
                episode_actions.append("episode_rollout")
                print(
                    f"[MuZero]   episode {ep + 1}/{episodes_per_iter} "
                    f"samples={len(samples)} replay_size={len(replay)}"
                )
                event_bus.emit(
                    "DecisionEvent",
                    DecisionEvent(
                        iteration=it,
                        episode=ep,
                        step=0,
                        chosen_action="episode_rollout",
                        top_actions=["episode_rollout"],
                        top_probs=[1.0],
                    ).to_payload(),
                )
                event_bus.emit(
                    "SearchEvent",
                    SearchEvent(
                        iteration=it,
                        episode=ep,
                        step=0,
                        node_count=max(len(samples), 1),
                        max_depth=min(len(samples), 60),
                    ).to_payload(),
                )
                for sample in samples:
                    event_bus.emit(
                        "TransitionEvent",
                        TransitionEvent(
                            iteration=it,
                            episode=ep,
                            step=int(sample.info.get("step", 0)),
                            game_turn=int(sample.info.get("game_turn", 0)),
                            action_id=str(sample.info.get("action_id", "")),
                            to_play=str(sample.info.get("to_play", "")),
                            reward_target=float(sample.reward_target),
                            done=bool(sample.info.get("done", False)),
                            terminal_reason=str(sample.info.get("terminal_reason", "")),
                            timeout=bool(sample.info.get("timeout", False)),
                            action_kind=str(sample.info.get("action_kind", "")),
                            unit_id=str(sample.info.get("unit_id", "")),
                            unit_side=str(sample.info.get("unit_side", "")),
                            unit_key=str(sample.info.get("unit_key", "")),
                            unit_label=str(sample.info.get("unit_label", "")),
                            damage_dealt=float(sample.info.get("damage_dealt", 0.0)),
                            kills_dealt=int(sample.info.get("kills_dealt", 0)),
                            vp_captures=int(sample.info.get("vp_captures", 0)),
                            vp_control_before_by_side=dict(sample.info.get("vp_control_before_by_side", {}) or {}),
                            vp_control_after_by_side=dict(sample.info.get("vp_control_after_by_side", {}) or {}),
                            vp_gain_by_side=dict(sample.info.get("vp_gain_by_side", {}) or {}),
                            vp_loss_by_side=dict(sample.info.get("vp_loss_by_side", {}) or {}),
                            reward_components=dict(sample.info.get("reward_components", {}) or {}),
                            eligible_unit_ids=list(sample.info.get("eligible_unit_ids", []) or []),
                            eligible_unit_count=int(sample.info.get("eligible_unit_count", 0)),
                            legal_action_count=int(sample.info.get("legal_action_count", 0)),
                            legal_attack_options=int(sample.info.get("legal_attack_options", 0)),
                            legal_capture_options=int(sample.info.get("legal_capture_options", 0)),
                            legal_reaction_options=int(sample.info.get("legal_reaction_options", 0)),
                            objective_had_opportunity=int(sample.info.get("objective_had_opportunity", 0)),
                            objective_distance_before=float(sample.info.get("objective_distance_before", -1.0)),
                            objective_distance_after=float(sample.info.get("objective_distance_after", -1.0)),
                            objective_min_dist_before=float(sample.info.get("objective_min_dist_before", -1.0)),
                            objective_min_dist_after=float(sample.info.get("objective_min_dist_after", -1.0)),
                            objective_progress_delta=float(sample.info.get("objective_progress_delta", 0.0)),
                            objective_converted=int(sample.info.get("objective_converted", 0)),
                            objective_best_vp_id=str(sample.info.get("objective_best_vp_id", "")),
                            vp_distance_vector=dict(sample.info.get("vp_distance_vector", {}) or {}),
                            vp_distance_vector_size=int(sample.info.get("vp_distance_vector_size", 0)),
                            objective_signal_definition_version=str(sample.info.get("objective_signal_definition_version", "")),
                            objective_vp_hexes_count=int(sample.info.get("objective_vp_hexes_count", 0)),
                            objective_vp_owner_count=int(sample.info.get("objective_vp_owner_count", 0)),
                            objective_side_norm=str(sample.info.get("objective_side_norm", "")),
                            mcts_entropy=float(sample.info.get("mcts_entropy", 0.0)),
                            mcts_margin=float(sample.info.get("mcts_margin", 0.0)),
                            chosen_action_prob=float(sample.info.get("chosen_action_prob", 0.0)),
                            predicted_value=float(sample.info.get("predicted_value", 0.0)),
                            mcts_total_visits=int(sample.info.get("mcts_total_visits", 0)),
                            mcts_active_actions=int(sample.info.get("mcts_active_actions", 0)),
                            attack_target_unit_id=str(sample.info.get("attack_target_unit_id", "")),
                            attack_target_class_attempt=str(sample.info.get("attack_target_class_attempt", "")),
                            attack_target_class_damage=dict(sample.info.get("attack_target_class_damage", {}) or {}),
                            attack_target_class_kills=dict(sample.info.get("attack_target_class_kills", {}) or {}),
                            attack_distance_mean=float(sample.info.get("attack_distance_mean", -1.0)),
                            attack_target_cover_mean=float(sample.info.get("attack_target_cover_mean", -1.0)),
                            attack_target_los_block_mean=float(sample.info.get("attack_target_los_block_mean", -1.0)),
                            policy_top_actions=list(sample.info.get("policy_top_actions", []) or []),
                            policy_top_probs=[float(x) for x in (sample.info.get("policy_top_probs", []) or [])],
                            latent_top_indices=[int(x) for x in (sample.info.get("latent_top_indices", []) or [])],
                            latent_top_values=[float(x) for x in (sample.info.get("latent_top_values", []) or [])],
                            latent_l2_norm=float(sample.info.get("latent_l2_norm", 0.0)),
                            predicted_value_root=float(sample.info.get("predicted_value_root", 0.0)),
                            dynamics_pred_reward=float(sample.info.get("dynamics_pred_reward", 0.0)),
                            dynamics_next_latent_l2=float(sample.info.get("dynamics_next_latent_l2", 0.0)),
                            dynamics_delta_l2=float(sample.info.get("dynamics_delta_l2", 0.0)),
                            acting_q=int(sample.info.get("acting_q", 0)),
                            acting_r=int(sample.info.get("acting_r", 0)),
                            target_q=int(sample.info.get("target_q", 0)),
                            target_r=int(sample.info.get("target_r", 0)),
                            units_snapshot=list(sample.info.get("units_snapshot", []) or []),
                        ).to_payload(),
                    )
        else:
            if num_workers > 1 and device != "cpu":
                print("[MuZero] parallel selfplay disabled for non-cpu device")
            for ep in range(episodes_per_iter):
                print(
                    f"[MuZero]   episode {ep + 1}/{episodes_per_iter} starting "
                    f"(seed={seed + it + ep}, sims={mcts_simulations}, max_steps={max_steps})"
                )
                samples = play_episode(
                    adapter=adapter,
                    scenario_id=scenario_id,
                    seed=seed + it + ep,
                    max_steps=max_steps,
                    max_steps_override=max_steps_override,
                    action_dim=action_dim,
                    model=model,
                    mcts_simulations=mcts_simulations,
                    mcts_c_puct=mcts_c_puct,
                    mcts_unroll_steps=mcts_unroll_steps,
                    mcts_discount=mcts_discount,
                    mcts_temperature=mcts_temperature,
                    mcts_dirichlet_alpha=mcts_dirichlet_alpha,
                    mcts_dirichlet_epsilon=mcts_dirichlet_epsilon,
                    inference_cache_limit=inference_cache_limit,
                    progress_log_every=progress_log_every,
                    log_episode_end=bool(log_episode_end),
                    timeout_penalty=timeout_penalty,
                    log_units_snapshot=bool(log_units_snapshot),
                    reward_shaping=reward_shaping,
                    objective_opportunity_near_vp_max_dist=objective_opportunity_near_vp_max_dist,
                    collect_xai=bool(enable_post_train_analytics),
                )
                replay.extend(samples)
                episode_rewards.append(sum(s.reward_target for s in samples))
                episode_actions.append("episode_rollout")
                print(
                    f"[MuZero]   episode {ep + 1}/{episodes_per_iter} "
                    f"samples={len(samples)} replay_size={len(replay)}"
                )
                event_bus.emit(
                    "DecisionEvent",
                    DecisionEvent(
                        iteration=it,
                        episode=ep,
                        step=0,
                        chosen_action="episode_rollout",
                        top_actions=["episode_rollout"],
                        top_probs=[1.0],
                    ).to_payload(),
                )
                event_bus.emit(
                    "SearchEvent",
                    SearchEvent(
                        iteration=it,
                        episode=ep,
                        step=0,
                        node_count=max(len(samples), 1),
                        max_depth=min(len(samples), 60),
                    ).to_payload(),
                )
                for sample in samples:
                    event_bus.emit(
                        "TransitionEvent",
                        TransitionEvent(
                            iteration=it,
                            episode=ep,
                            step=int(sample.info.get("step", 0)),
                            game_turn=int(sample.info.get("game_turn", 0)),
                            action_id=str(sample.info.get("action_id", "")),
                            to_play=str(sample.info.get("to_play", "")),
                            reward_target=float(sample.reward_target),
                            done=bool(sample.info.get("done", False)),
                            terminal_reason=str(sample.info.get("terminal_reason", "")),
                            timeout=bool(sample.info.get("timeout", False)),
                            action_kind=str(sample.info.get("action_kind", "")),
                            unit_id=str(sample.info.get("unit_id", "")),
                            unit_side=str(sample.info.get("unit_side", "")),
                            unit_key=str(sample.info.get("unit_key", "")),
                            unit_label=str(sample.info.get("unit_label", "")),
                            damage_dealt=float(sample.info.get("damage_dealt", 0.0)),
                            kills_dealt=int(sample.info.get("kills_dealt", 0)),
                            vp_captures=int(sample.info.get("vp_captures", 0)),
                            vp_control_before_by_side=dict(sample.info.get("vp_control_before_by_side", {}) or {}),
                            vp_control_after_by_side=dict(sample.info.get("vp_control_after_by_side", {}) or {}),
                            vp_gain_by_side=dict(sample.info.get("vp_gain_by_side", {}) or {}),
                            vp_loss_by_side=dict(sample.info.get("vp_loss_by_side", {}) or {}),
                            reward_components=dict(sample.info.get("reward_components", {}) or {}),
                            eligible_unit_ids=list(sample.info.get("eligible_unit_ids", []) or []),
                            eligible_unit_count=int(sample.info.get("eligible_unit_count", 0)),
                            legal_action_count=int(sample.info.get("legal_action_count", 0)),
                            legal_attack_options=int(sample.info.get("legal_attack_options", 0)),
                            legal_capture_options=int(sample.info.get("legal_capture_options", 0)),
                            legal_reaction_options=int(sample.info.get("legal_reaction_options", 0)),
                            objective_had_opportunity=int(sample.info.get("objective_had_opportunity", 0)),
                            objective_distance_before=float(sample.info.get("objective_distance_before", -1.0)),
                            objective_distance_after=float(sample.info.get("objective_distance_after", -1.0)),
                            objective_min_dist_before=float(sample.info.get("objective_min_dist_before", -1.0)),
                            objective_min_dist_after=float(sample.info.get("objective_min_dist_after", -1.0)),
                            objective_progress_delta=float(sample.info.get("objective_progress_delta", 0.0)),
                            objective_converted=int(sample.info.get("objective_converted", 0)),
                            objective_best_vp_id=str(sample.info.get("objective_best_vp_id", "")),
                            vp_distance_vector=dict(sample.info.get("vp_distance_vector", {}) or {}),
                            vp_distance_vector_size=int(sample.info.get("vp_distance_vector_size", 0)),
                            objective_signal_definition_version=str(sample.info.get("objective_signal_definition_version", "")),
                            objective_vp_hexes_count=int(sample.info.get("objective_vp_hexes_count", 0)),
                            objective_vp_owner_count=int(sample.info.get("objective_vp_owner_count", 0)),
                            objective_side_norm=str(sample.info.get("objective_side_norm", "")),
                            mcts_entropy=float(sample.info.get("mcts_entropy", 0.0)),
                            mcts_margin=float(sample.info.get("mcts_margin", 0.0)),
                            chosen_action_prob=float(sample.info.get("chosen_action_prob", 0.0)),
                            predicted_value=float(sample.info.get("predicted_value", 0.0)),
                            mcts_total_visits=int(sample.info.get("mcts_total_visits", 0)),
                            mcts_active_actions=int(sample.info.get("mcts_active_actions", 0)),
                            attack_target_unit_id=str(sample.info.get("attack_target_unit_id", "")),
                            attack_target_class_attempt=str(sample.info.get("attack_target_class_attempt", "")),
                            attack_target_class_damage=dict(sample.info.get("attack_target_class_damage", {}) or {}),
                            attack_target_class_kills=dict(sample.info.get("attack_target_class_kills", {}) or {}),
                            attack_distance_mean=float(sample.info.get("attack_distance_mean", -1.0)),
                            attack_target_cover_mean=float(sample.info.get("attack_target_cover_mean", -1.0)),
                            attack_target_los_block_mean=float(sample.info.get("attack_target_los_block_mean", -1.0)),
                            policy_top_actions=list(sample.info.get("policy_top_actions", []) or []),
                            policy_top_probs=[float(x) for x in (sample.info.get("policy_top_probs", []) or [])],
                            latent_top_indices=[int(x) for x in (sample.info.get("latent_top_indices", []) or [])],
                            latent_top_values=[float(x) for x in (sample.info.get("latent_top_values", []) or [])],
                            latent_l2_norm=float(sample.info.get("latent_l2_norm", 0.0)),
                            predicted_value_root=float(sample.info.get("predicted_value_root", 0.0)),
                            dynamics_pred_reward=float(sample.info.get("dynamics_pred_reward", 0.0)),
                            dynamics_next_latent_l2=float(sample.info.get("dynamics_next_latent_l2", 0.0)),
                            dynamics_delta_l2=float(sample.info.get("dynamics_delta_l2", 0.0)),
                            acting_q=int(sample.info.get("acting_q", 0)),
                            acting_r=int(sample.info.get("acting_r", 0)),
                            target_q=int(sample.info.get("target_q", 0)),
                            target_r=int(sample.info.get("target_r", 0)),
                            units_snapshot=list(sample.info.get("units_snapshot", []) or []),
                        ).to_payload(),
                    )
        selfplay_elapsed_s = float(time.perf_counter() - selfplay_t0)

        train_t0 = time.perf_counter()
        batch = replay.sample(batch_size=batch_size)
        replay_age_values = []
        current_add_idx = int(replay.add_index)
        for s in batch:
            add_idx = int((s.info or {}).get("replay_add_index", current_add_idx))
            replay_age_values.append(max(0, current_add_idx - 1 - add_idx))
        replay_age_mean = (
            float(sum(replay_age_values)) / float(max(1, len(replay_age_values)))
            if replay_age_values
            else 0.0
        )
        replay_age_max = float(max(replay_age_values)) if replay_age_values else 0.0
        metrics = trainer.train_batch(batch)
        latest_metrics = metrics.to_dict()
        latest_metrics["replay_age_mean"] = float(replay_age_mean)
        latest_metrics["replay_age_max"] = float(replay_age_max)
        print(
            "[MuZero]   train "
            f"loss={latest_metrics['loss']:.4f} "
            f"policy={latest_metrics['policy_loss']:.4f} "
            f"value={latest_metrics['value_loss']:.4f} "
            f"reward={latest_metrics['reward_loss']:.4f} "
            f"objective={latest_metrics.get('objective_loss', 0.0):.4f}"
        )
        _mlflow_log_metrics(mlflow_mod, latest_metrics, step=int(it))
        event_bus.emit(
            "TrainStepEvent",
            TrainStepEvent(iteration=it, **latest_metrics).to_payload(),
        )

        ckpt_dir = run_dir / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        ckpt_path = None
        should_save_iter = ((it + 1) % checkpoint_every == 0) or (it == iterations - 1)
        if should_save_iter:
            ckpt_path = ckpt_dir / f"iter_{it}.pt"
            torch.save(model.state_dict(), ckpt_path)
        train_elapsed_s = float(time.perf_counter() - train_t0)
        iter_elapsed_s = float(time.perf_counter() - iter_t0)
        latest_metrics["timing_selfplay_s"] = float(selfplay_elapsed_s)
        latest_metrics["timing_train_s"] = float(train_elapsed_s)
        latest_metrics["timing_iter_s"] = float(iter_elapsed_s)
        iter_timing_rows.append(
            {
                "iteration": int(it),
                "selfplay_s": float(selfplay_elapsed_s),
                "train_s": float(train_elapsed_s),
                "iter_s": float(iter_elapsed_s),
            }
        )
        _mlflow_log_metrics(
            mlflow_mod,
            {
                "timing_selfplay_s": float(selfplay_elapsed_s),
                "timing_train_s": float(train_elapsed_s),
                "timing_iter_s": float(iter_elapsed_s),
            },
            step=int(it),
        )
        print(
            "[MuZero]   timing "
            f"selfplay_s={selfplay_elapsed_s:.2f} "
            f"train_s={train_elapsed_s:.2f} "
            f"iter_s={iter_elapsed_s:.2f}"
        )
        if ckpt_path is not None:
            print(f"[MuZero]   checkpoint={ckpt_path}")

    if events_writer is not None:
        for event in event_bus.events:
            events_writer.append(event)

    transition_count = sum(1 for e in event_bus.events if e.get("type") == "TransitionEvent")
    train_step_count = sum(1 for e in event_bus.events if e.get("type") == "TrainStepEvent")
    integrity = {
        "decision_events": sum(1 for e in event_bus.events if e.get("type") == "DecisionEvent"),
        "search_events": sum(1 for e in event_bus.events if e.get("type") == "SearchEvent"),
        "transition_events": transition_count,
        "train_step_events": train_step_count,
        "expected_train_step_events": iterations,
        "valid": train_step_count == iterations and transition_count > 0,
    }
    (run_dir / "events" / "integrity.json").write_text(
        json.dumps(integrity, indent=2),
        encoding="utf-8",
    )
    total_elapsed_s = float(time.perf_counter() - run_t0)
    selfplay_total_s = float(sum(float(x.get("selfplay_s", 0.0)) for x in iter_timing_rows))
    train_total_s = float(sum(float(x.get("train_s", 0.0)) for x in iter_timing_rows))
    iter_total_s = float(sum(float(x.get("iter_s", 0.0)) for x in iter_timing_rows))
    latest_metrics["timing_summary"] = {
        "total_elapsed_s": float(total_elapsed_s),
        "selfplay_total_s": float(selfplay_total_s),
        "train_total_s": float(train_total_s),
        "iter_total_s": float(iter_total_s),
        "iter_avg_s": (float(iter_total_s) / float(max(1, len(iter_timing_rows)))),
        "selfplay_avg_s": (float(selfplay_total_s) / float(max(1, len(iter_timing_rows)))),
        "train_avg_s": (float(train_total_s) / float(max(1, len(iter_timing_rows)))),
        "iterations": int(len(iter_timing_rows)),
    }
    latest_metrics["timing_by_iteration"] = iter_timing_rows

    if not enable_post_train_analytics:
        latest_metrics["train_runtime_profile"] = {
            "post_train_analytics_enabled": False,
            "mode": "lean",
        }
        metrics_path = run_dir / "metrics" / "summary.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(latest_metrics, indent=2), encoding="utf-8")
        if mlflow_mod is not None:
            try:
                mlflow_mod.log_artifact(str(metrics_path))
                mlflow_mod.log_artifact(str(run_dir / "run_manifest.json"))
                mlflow_mod.end_run()
            except Exception:
                pass
        print("[MuZero] post-train analytics disabled (lean mode)")
        print(f"[MuZero] completed run_dir={run_dir}")
        return {"run_id": run_id, "metrics": latest_metrics}

    # Aggregated units/sides metrics are first-class runner outputs
    # consumed by dashboard tabs (no UI-side guesswork).
    side_turn_counts: dict[str, int] = {}
    unit_action_counts: dict[str, int] = {}
    unit_attack_counts: dict[str, int] = {}
    unit_side_map: dict[str, str] = {}
    unit_key_map: dict[str, str] = {}
    unit_label_map: dict[str, str] = {}
    side_unit_counts: dict[str, dict[str, int]] = {}
    unit_damage: dict[str, float] = {}
    unit_kills: dict[str, int] = {}
    unit_turns_eligible: dict[str, int] = {}
    unit_turns_activated: dict[str, int] = {}
    unit_blocked_before_activation_turns: dict[str, int] = {}
    unit_eligible_turn_keys: dict[str, set[tuple[int, int, int]]] = {}
    unit_activated_turn_keys: dict[str, set[tuple[int, int, int]]] = {}
    action_kind_counts: dict[str, int] = {}
    action_kind_counts_by_side: dict[str, dict[str, int]] = {}
    strategy_counts: dict[str, int] = {}
    strategy_counts_by_side: dict[str, dict[str, int]] = {}
    vp_actions_by_side: dict[str, int] = {}
    capture_actions_by_side: dict[str, int] = {}
    vp_captures_by_side: dict[str, int] = {}
    vp_initial_by_side: dict[str, int] = {}
    vp_final_by_side: dict[str, int] = {}
    vp_gain_sum_by_side: dict[str, int] = {}
    vp_loss_sum_by_side: dict[str, int] = {}
    episode_first_vp_by_key: dict[tuple[int, int], dict[str, int]] = {}
    episode_last_vp_by_key: dict[tuple[int, int], dict[str, int]] = {}
    reward_component_sums: dict[str, float] = {}
    reward_component_sums_by_side: dict[str, dict[str, float]] = {}
    option_space_totals = {
        "legal_action_count": 0.0,
        "legal_attack_options": 0.0,
        "legal_capture_options": 0.0,
        "mcts_entropy": 0.0,
        "mcts_margin": 0.0,
        "chosen_action_prob": 0.0,
    }
    option_space_by_side: dict[str, dict[str, float]] = {}
    search_efficiency_totals = {
        "mcts_total_visits": 0.0,
        "mcts_active_actions": 0.0,
    }
    attack_effectiveness_by_kind: dict[str, dict[str, float]] = {}
    attack_effectiveness_by_side_kind: dict[str, dict[str, dict[str, float]]] = {}
    value_calibration_pairs: list[tuple[float, float]] = []
    value_calibration_phase_pairs: dict[str, list[tuple[float, float]]] = {
        "early": [],
        "mid": [],
        "late": [],
    }
    matchup_effectiveness: dict[str, dict[str, float]] = {}
    context_effectiveness: dict[str, dict[str, float]] = {}
    xai_policy_top1_counts: dict[str, int] = {}
    xai_latent_top_dim_counts: dict[int, int] = {}
    xai_policy_top1_prob_sum = 0.0
    xai_policy_top1_prob_count = 0
    xai_latent_l2_norm_sum = 0.0
    xai_latent_l2_norm_count = 0
    xai_predicted_value_root_sum = 0.0
    xai_predicted_value_root_count = 0
    xai_dynamics_pred_reward_sum = 0.0
    xai_dynamics_pred_reward_count = 0
    xai_dynamics_next_latent_l2_sum = 0.0
    xai_dynamics_next_latent_l2_count = 0
    xai_dynamics_delta_l2_sum = 0.0
    xai_dynamics_delta_l2_count = 0
    decision_flip_by_side: dict[str, dict[str, float]] = {}
    objective_opportunity_by_side: dict[str, dict[str, float]] = {}
    objective_funnel_by_side: dict[str, dict[str, float]] = {}
    objective_explain_by_side: dict[str, dict[str, dict[str, float]]] = {}
    objective_near_vp_by_side: dict[str, dict[str, float]] = {}
    vp_units_by_side: dict[str, set[str]] = {}
    turn_side_snapshots: dict[tuple[int, int, int, str], list[set[str]]] = {}
    unit_turn_activated: set[tuple[int, int, int, str]] = set()
    episode_return_by_key: dict[tuple[int, int], float] = {}
    xai_decision_rows: list[dict] = []
    reaction_window_count = 0
    reaction_fire_count = 0
    reaction_fire_skipped_count = 0
    reaction_fire_kill_conversions = 0
    reaction_fire_damage_sum = 0.0
    melee_attempts = 0
    melee_success_count = 0
    melee_kills_sum = 0.0
    melee_damage_sum = 0.0
    assault_context_counts = {"favorable": 0, "unfavorable": 0}

    for event in event_bus.events:
        if event.get("type") != "TransitionEvent":
            continue
        p = event.get("payload", {}) or {}
        ek = (int(p.get("iteration", 0)), int(p.get("episode", 0)))
        episode_return_by_key[ek] = episode_return_by_key.get(ek, 0.0) + float(p.get("reward_target", 0.0))
    episode_max_turn_by_key: dict[tuple[int, int], int] = {}
    episode_transitions_by_key: dict[tuple[int, int], list[dict]] = {}
    for event in event_bus.events:
        if event.get("type") != "TransitionEvent":
            continue
        p = event.get("payload", {}) or {}
        ek = (int(p.get("iteration", 0)), int(p.get("episode", 0)))
        gt = int(p.get("game_turn", 0))
        episode_max_turn_by_key[ek] = max(episode_max_turn_by_key.get(ek, 0), gt)
        if ek not in episode_transitions_by_key:
            episode_transitions_by_key[ek] = []
        episode_transitions_by_key[ek].append(p)

    prev_decision_state_by_side_ep: dict[tuple[int, int, str], dict[str, object]] = {}

    for event in event_bus.events:
        if event.get("type") != "TransitionEvent":
            continue
        payload = event.get("payload", {}) or {}
        iteration_idx = int(payload.get("iteration", 0))
        episode_idx = int(payload.get("episode", 0))
        game_turn = int(payload.get("game_turn", 0))
        side = str(payload.get("to_play", "")).strip() or "unknown"
        side_turn_counts[side] = side_turn_counts.get(side, 0) + 1
        unit_id = str(payload.get("unit_id", "")).strip()
        if not unit_id:
            raise ValueError("TransitionEvent contract violation: missing unit_id")
        unit_side = str(payload.get("unit_side", "")).strip()
        if not unit_side:
            raise ValueError("TransitionEvent contract violation: missing unit_side")
        unit_key = str(payload.get("unit_key", "")).strip()
        if not unit_key:
            raise ValueError("TransitionEvent contract violation: missing unit_key")
        unit_label = str(payload.get("unit_label", "")).strip()
        if not unit_label:
            raise ValueError("TransitionEvent contract violation: missing unit_label")
        unit_action_counts[unit_id] = unit_action_counts.get(unit_id, 0) + 1
        unit_turns_activated[unit_id] = unit_turns_activated.get(unit_id, 0) + 1
        if unit_id not in unit_activated_turn_keys:
            unit_activated_turn_keys[unit_id] = set()
        unit_activated_turn_keys[unit_id].add((iteration_idx, episode_idx, game_turn))
        for eligible_id in list(payload.get("eligible_unit_ids", []) or []):
            eligible_norm = str(eligible_id).strip()
            if not eligible_norm:
                continue
            unit_turns_eligible[eligible_norm] = unit_turns_eligible.get(eligible_norm, 0) + 1
            if eligible_norm not in unit_eligible_turn_keys:
                unit_eligible_turn_keys[eligible_norm] = set()
            unit_eligible_turn_keys[eligible_norm].add((iteration_idx, episode_idx, game_turn))
        eligible_set = {
            str(e).strip()
            for e in list(payload.get("eligible_unit_ids", []) or [])
            if str(e).strip()
        }
        snap_key = (iteration_idx, episode_idx, game_turn, side)
        if snap_key not in turn_side_snapshots:
            turn_side_snapshots[snap_key] = []
        turn_side_snapshots[snap_key].append(eligible_set)
        unit_turn_activated.add((iteration_idx, episode_idx, game_turn, unit_id))
        action_kind = str(payload.get("action_kind", "")).strip().upper()
        is_attack = action_kind not in {"", "MOVE", "WAIT", "TIMEOUT"}
        action_key = action_kind if action_kind else "UNKNOWN"
        reaction_window_count += int(payload.get("legal_reaction_options", 0) or 0) > 0
        if action_key == "OPPORTUNITY_FIRE":
            reaction_fire_count += 1
            if int(payload.get("kills_dealt", 0)) > 0:
                reaction_fire_kill_conversions += 1
            reaction_fire_damage_sum += float(payload.get("damage_dealt", 0.0))
        elif action_key == "OPPORTUNITY_SKIP":
            reaction_fire_skipped_count += 1
        if "ASSAULT" in action_key or action_key in {"MELEE", "ASSAULT_MELEE"}:
            melee_attempts += 1
            dmg_now = float(payload.get("damage_dealt", 0.0))
            k_now = float(payload.get("kills_dealt", 0))
            melee_damage_sum += dmg_now
            melee_kills_sum += k_now
            if dmg_now > 0.0 or k_now > 0.0:
                melee_success_count += 1
            assault_bucket = _assault_advantage_bucket(
                chosen_action_prob=float(payload.get("chosen_action_prob", 0.0)),
                mcts_margin=float(payload.get("mcts_margin", 0.0)),
                legal_attack_options=int(payload.get("legal_attack_options", 0)),
                attack_target_cover_mean=float(payload.get("attack_target_cover_mean", -1.0)),
                prob_threshold=assault_advantage_prob_threshold,
                margin_threshold=assault_advantage_margin_threshold,
                cover_max=assault_advantage_cover_max,
                min_score=assault_advantage_min_score,
            )
            assault_context_counts[assault_bucket] = (
                int(assault_context_counts.get(assault_bucket, 0)) + 1
            )
        side_ep_key = (iteration_idx, episode_idx, unit_side)
        if side_ep_key not in decision_flip_by_side:
            decision_flip_by_side[side_ep_key] = {"opportunities": 0.0, "flips": 0.0}
        prev_state = prev_decision_state_by_side_ep.get(side_ep_key)
        curr_signature = {
            "eligible_ids": tuple(sorted(str(x).strip() for x in (payload.get("eligible_unit_ids", []) or []) if str(x).strip())),
            "legal_action_count": int(payload.get("legal_action_count", 0)),
            "action_kind": str(action_key),
        }
        if isinstance(prev_state, dict):
            prev_eligible = tuple(prev_state.get("eligible_ids", ()))
            curr_eligible = tuple(curr_signature["eligible_ids"])
            prev_legal = int(prev_state.get("legal_action_count", 0))
            curr_legal = int(curr_signature["legal_action_count"])
            state_similar = (
                prev_eligible == curr_eligible
                and abs(prev_legal - curr_legal) <= int(decision_flip_legal_count_tolerance)
            )
            if state_similar:
                decision_flip_by_side[side_ep_key]["opportunities"] += 1.0
                if str(prev_state.get("action_kind", "")) != str(action_key):
                    decision_flip_by_side[side_ep_key]["flips"] += 1.0
        prev_decision_state_by_side_ep[side_ep_key] = curr_signature
        if unit_side not in objective_opportunity_by_side:
            objective_opportunity_by_side[unit_side] = {"opportunities": 0.0, "conversions": 0.0}
        if unit_side not in objective_funnel_by_side:
            objective_funnel_by_side[unit_side] = {
                "opportunities": 0.0,
                "progress_actions": 0.0,
                "conversions": 0.0,
                "stalls": 0.0,
                "progress_delta_sum": 0.0,
            }
        if unit_side not in objective_explain_by_side:
            objective_explain_by_side[unit_side] = {
                "no_progress_reason_counts": {},
                "no_progress_reason_l2_counts": {},
                "progress_path_counts": {},
                "conversion_path_counts": {},
                "non_progress_confidence_counts": {},
            }
        if unit_side not in objective_near_vp_by_side:
            objective_near_vp_by_side[unit_side] = {
                "near_vp_opportunities": 0.0,
                "near_vp_progress_actions": 0.0,
                "near_vp_conversions": 0.0,
                "far_vp_opportunities": 0.0,
                "far_vp_progress_actions": 0.0,
                "far_vp_conversions": 0.0,
            }
        has_vp_opportunity = int(payload.get("objective_had_opportunity", 0)) > 0
        objective_progress_delta = float(payload.get("objective_progress_delta", 0.0))
        objective_converted = int(payload.get("objective_converted", 0)) > 0
        objective_distance_before = float(payload.get("objective_distance_before", -1.0))
        if has_vp_opportunity:
            objective_funnel_by_side[unit_side]["opportunities"] += 1.0
            if objective_progress_delta > 0.0:
                objective_funnel_by_side[unit_side]["progress_actions"] += 1.0
            else:
                objective_funnel_by_side[unit_side]["stalls"] += 1.0
            objective_funnel_by_side[unit_side]["progress_delta_sum"] += float(objective_progress_delta)
            if objective_converted:
                objective_funnel_by_side[unit_side]["conversions"] += 1.0
            near_key_prefix = (
                "near_vp"
                if (
                    objective_distance_before >= 0.0
                    and objective_distance_before <= float(objective_near_vp_max_dist)
                )
                else "far_vp"
            )
            objective_near_vp_by_side[unit_side][f"{near_key_prefix}_opportunities"] += 1.0
            if objective_progress_delta > 0.0:
                objective_near_vp_by_side[unit_side][f"{near_key_prefix}_progress_actions"] += 1.0
            if objective_converted:
                objective_near_vp_by_side[unit_side][f"{near_key_prefix}_conversions"] += 1.0
            action_kind_raw = str(payload.get("action_kind", "")).strip().upper()
            chosen_prob = float(payload.get("chosen_action_prob", 0.0))
            mcts_margin = float(payload.get("mcts_margin", 0.0))
            no_prog_counts = objective_explain_by_side[unit_side]["no_progress_reason_counts"]
            no_prog_l2_counts = objective_explain_by_side[unit_side]["no_progress_reason_l2_counts"]
            prog_counts = objective_explain_by_side[unit_side]["progress_path_counts"]
            conv_counts = objective_explain_by_side[unit_side]["conversion_path_counts"]
            conf_counts = objective_explain_by_side[unit_side]["non_progress_confidence_counts"]
            if objective_progress_delta > 0.0:
                if objective_progress_delta >= float(objective_strong_progress_delta_threshold):
                    pr_key = "strong_progress_delta_ge_2"
                else:
                    pr_key = "marginal_progress_delta_0_1"
                prog_counts[pr_key] = float(prog_counts.get(pr_key, 0.0)) + 1.0
            else:
                if action_kind_raw in {"WAIT", "TIMEOUT"}:
                    np_key = "passive_wait_or_timeout"
                elif action_kind_raw == "MOVE":
                    np_key = "moved_without_closing_distance"
                elif action_kind_raw in {"FIRE_MOVE", "RANGED_DIRECT", "RANGED_INDIRECT", "OPPORTUNITY_FIRE", "MELEE", "ASSAULT_MELEE", "CAPTURE", "FIRE_CAPTURE"}:
                    np_key = "attack_or_capture_without_progress"
                else:
                    np_key = "other_non_progress_action"
                no_prog_counts[np_key] = float(no_prog_counts.get(np_key, 0.0)) + 1.0
                dist_before = float(payload.get("objective_distance_before", -1.0))
                dist_after = float(payload.get("objective_distance_after", -1.0))
                legal_capture_options = int(payload.get("legal_capture_options", 0))
                legal_attack_options = int(payload.get("legal_attack_options", 0))
                legal_action_count = int(payload.get("legal_action_count", 0))
                distance_bucket = (
                    "near_vp"
                    if (dist_before >= 0.0 and dist_before <= float(objective_near_vp_max_dist))
                    else "far_vp"
                )
                if legal_action_count <= 1:
                    np_l2_key = f"forced_action_{distance_bucket}"
                elif action_kind_raw in {"WAIT", "TIMEOUT"}:
                    np_l2_key = f"passive_wait_{distance_bucket}"
                elif action_kind_raw == "MOVE":
                    if legal_capture_options > 0:
                        np_l2_key = f"move_skipped_capture_window_{distance_bucket}"
                    elif dist_before >= 0.0 and dist_after >= 0.0 and dist_after >= dist_before:
                        np_l2_key = f"move_no_closer_path_{distance_bucket}"
                    elif legal_attack_options <= 0:
                        np_l2_key = f"move_no_attack_options_{distance_bucket}"
                    else:
                        np_l2_key = f"move_unclear_non_progress_{distance_bucket}"
                elif action_kind_raw in {"FIRE_MOVE", "RANGED_DIRECT", "RANGED_INDIRECT", "OPPORTUNITY_FIRE", "MELEE", "ASSAULT_MELEE", "CAPTURE", "FIRE_CAPTURE"}:
                    if legal_capture_options > 0 and not objective_converted:
                        np_l2_key = f"capture_window_not_converted_{distance_bucket}"
                    elif (
                        chosen_prob >= float(objective_high_confidence_prob_threshold)
                        or mcts_margin >= float(objective_high_confidence_margin_threshold)
                    ):
                        np_l2_key = f"high_confidence_non_progress_attack_{distance_bucket}"
                    else:
                        np_l2_key = f"low_confidence_non_progress_attack_{distance_bucket}"
                else:
                    np_l2_key = f"other_non_progress_action_{distance_bucket}"
                no_prog_l2_counts[np_l2_key] = float(no_prog_l2_counts.get(np_l2_key, 0.0)) + 1.0
                conf_key = (
                    "high_confidence_non_progress"
                    if (
                        chosen_prob >= float(objective_high_confidence_prob_threshold)
                        or mcts_margin >= float(objective_high_confidence_margin_threshold)
                    )
                    else "low_confidence_non_progress"
                )
                conf_counts[conf_key] = float(conf_counts.get(conf_key, 0.0)) + 1.0
            if objective_converted and objective_progress_delta > 0.0:
                cp_key = "converted_after_progress"
            elif objective_converted and objective_progress_delta <= 0.0:
                cp_key = "converted_without_progress"
            elif (not objective_converted) and objective_progress_delta > 0.0:
                cp_key = "progressed_but_not_converted"
            else:
                cp_key = "stalled_and_not_converted"
            conv_counts[cp_key] = float(conv_counts.get(cp_key, 0.0)) + 1.0
        if has_vp_opportunity:
            objective_opportunity_by_side[unit_side]["opportunities"] += 1.0
            side_gain = int((dict(payload.get("vp_gain_by_side", {}) or {})).get(unit_side, 0))
            if side_gain > 0 or int(payload.get("vp_captures", 0)) > 0:
                objective_opportunity_by_side[unit_side]["conversions"] += 1.0
        damage_val = float(payload.get("damage_dealt", 0.0))
        kills_val = int(payload.get("kills_dealt", 0))
        if is_attack:
            if action_key not in attack_effectiveness_by_kind:
                attack_effectiveness_by_kind[action_key] = {
                    "count": 0.0,
                    "success_count": 0.0,
                    "damage_sum": 0.0,
                    "kills_sum": 0.0,
                }
            attack_effectiveness_by_kind[action_key]["count"] += 1.0
            attack_effectiveness_by_kind[action_key]["damage_sum"] += float(damage_val)
            attack_effectiveness_by_kind[action_key]["kills_sum"] += float(kills_val)
            if damage_val > 0.0 or kills_val > 0:
                attack_effectiveness_by_kind[action_key]["success_count"] += 1.0
            if unit_side not in attack_effectiveness_by_side_kind:
                attack_effectiveness_by_side_kind[unit_side] = {}
            if action_key not in attack_effectiveness_by_side_kind[unit_side]:
                attack_effectiveness_by_side_kind[unit_side][action_key] = {
                    "count": 0.0,
                    "success_count": 0.0,
                    "damage_sum": 0.0,
                    "kills_sum": 0.0,
                }
            attack_effectiveness_by_side_kind[unit_side][action_key]["count"] += 1.0
            attack_effectiveness_by_side_kind[unit_side][action_key]["damage_sum"] += float(damage_val)
            attack_effectiveness_by_side_kind[unit_side][action_key]["kills_sum"] += float(kills_val)
            if damage_val > 0.0 or kills_val > 0:
                attack_effectiveness_by_side_kind[unit_side][action_key]["success_count"] += 1.0
        action_kind_counts[action_key] = action_kind_counts.get(action_key, 0) + 1
        if unit_side not in action_kind_counts_by_side:
            action_kind_counts_by_side[unit_side] = {}
        action_kind_counts_by_side[unit_side][action_key] = (
            action_kind_counts_by_side[unit_side].get(action_key, 0) + 1
        )
        if action_key in {"MOVE"}:
            strategy = "ADVANCE"
        elif action_key in {"WAIT"}:
            strategy = "HOLD"
        elif action_key in {"CAPTURE", "FIRE_CAPTURE"}:
            strategy = "CAPTURE"
        elif "ASSAULT" in action_key or action_key in {"MELEE", "ASSAULT_MELEE"}:
            strategy = "ASSAULT"
        elif action_key in {"FIRE_MOVE", "RANGED_DIRECT", "RANGED_INDIRECT", "OPPORTUNITY_FIRE"}:
            strategy = "ATTACK"
        else:
            strategy = "OTHER"
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        if unit_side not in strategy_counts_by_side:
            strategy_counts_by_side[unit_side] = {}
        strategy_counts_by_side[unit_side][strategy] = (
            strategy_counts_by_side[unit_side].get(strategy, 0) + 1
        )
        action_id_raw = str(payload.get("action_id", "")).upper()
        vp_caps = int(payload.get("vp_captures", 0))
        side_gain_now = int((dict(payload.get("vp_gain_by_side", {}) or {})).get(unit_side, 0))
        legal_cap_opts = int(payload.get("legal_capture_options", 0))
        is_capture_kind = ("CAPTURE" in action_key) or (vp_caps > 0) or (side_gain_now > 0)
        is_vp_related = ("VP" in action_id_raw) or is_capture_kind or (legal_cap_opts > 0)
        if is_vp_related:
            vp_actions_by_side[unit_side] = vp_actions_by_side.get(unit_side, 0) + 1
            if unit_side not in vp_units_by_side:
                vp_units_by_side[unit_side] = set()
            vp_units_by_side[unit_side].add(unit_id)
        if is_capture_kind:
            capture_actions_by_side[unit_side] = capture_actions_by_side.get(unit_side, 0) + 1
        if vp_caps > 0:
            vp_captures_by_side[unit_side] = vp_captures_by_side.get(unit_side, 0) + vp_caps
            if unit_side not in vp_units_by_side:
                vp_units_by_side[unit_side] = set()
            vp_units_by_side[unit_side].add(unit_id)
        before_vp = dict(payload.get("vp_control_before_by_side", {}) or {})
        after_vp = dict(payload.get("vp_control_after_by_side", {}) or {})
        gain_vp = dict(payload.get("vp_gain_by_side", {}) or {})
        loss_vp = dict(payload.get("vp_loss_by_side", {}) or {})
        ep_key = (iteration_idx, episode_idx)
        if ep_key not in episode_first_vp_by_key:
            episode_first_vp_by_key[ep_key] = {
                str(k).strip(): int(v)
                for k, v in before_vp.items()
                if str(k).strip()
            }
        episode_last_vp_by_key[ep_key] = {
            str(k).strip(): int(v)
            for k, v in after_vp.items()
            if str(k).strip()
        }
        for side_key, val in before_vp.items():
            side_norm = str(side_key).strip()
            if not side_norm:
                continue
            if side_norm not in vp_initial_by_side:
                vp_initial_by_side[side_norm] = int(val)
        for side_key, val in after_vp.items():
            side_norm = str(side_key).strip()
            if not side_norm:
                continue
            vp_final_by_side[side_norm] = int(val)
        for side_key, val in gain_vp.items():
            side_norm = str(side_key).strip()
            if not side_norm:
                continue
            vp_gain_sum_by_side[side_norm] = vp_gain_sum_by_side.get(side_norm, 0) + int(val)
        for side_key, val in loss_vp.items():
            side_norm = str(side_key).strip()
            if not side_norm:
                continue
            vp_loss_sum_by_side[side_norm] = vp_loss_sum_by_side.get(side_norm, 0) + int(val)
        comp = dict(payload.get("reward_components", {}) or {})
        if unit_side not in reward_component_sums_by_side:
            reward_component_sums_by_side[unit_side] = {}
        for k, v in comp.items():
            key = str(k).strip()
            if not key:
                continue
            val = float(v)
            reward_component_sums[key] = reward_component_sums.get(key, 0.0) + val
            reward_component_sums_by_side[unit_side][key] = (
                reward_component_sums_by_side[unit_side].get(key, 0.0) + val
            )
        if unit_side not in option_space_by_side:
            option_space_by_side[unit_side] = {
                "legal_action_count": 0.0,
                "legal_attack_options": 0.0,
                "legal_capture_options": 0.0,
                "mcts_entropy": 0.0,
                "mcts_margin": 0.0,
                "chosen_action_prob": 0.0,
            }
        for key in option_space_totals.keys():
            val = float(payload.get(key, 0.0))
            option_space_totals[key] += val
            option_space_by_side[unit_side][key] += val
        search_efficiency_totals["mcts_total_visits"] += float(payload.get("mcts_total_visits", 0.0))
        search_efficiency_totals["mcts_active_actions"] += float(payload.get("mcts_active_actions", 0.0))
        final_return = float(episode_return_by_key.get((iteration_idx, episode_idx), 0.0))
        pred_value = float(payload.get("predicted_value", 0.0))
        value_calibration_pairs.append((pred_value, final_return))
        max_turn = int(episode_max_turn_by_key.get((iteration_idx, episode_idx), 0))
        phase = "late"
        if max_turn > 0:
            ratio = float(game_turn) / float(max(1, max_turn))
            if ratio <= 0.33:
                phase = "early"
            elif ratio <= 0.66:
                phase = "mid"
        value_calibration_phase_pairs[phase].append((pred_value, final_return))
        xai_policy_top_actions = [str(x) for x in (payload.get("policy_top_actions", []) or []) if str(x)]
        xai_policy_top_probs = [float(x) for x in (payload.get("policy_top_probs", []) or [])]
        xai_latent_top_indices = [int(x) for x in (payload.get("latent_top_indices", []) or [])]
        xai_latent_top_values = [float(x) for x in (payload.get("latent_top_values", []) or [])]
        opp_fire_no_progress = float(comp.get("opportunity_fire_no_progress", 0.0))
        opp_skip_capture_preserve = float(comp.get("opportunity_skip_capture_preserve", 0.0))
        opp_weighting_label = "neutral"
        if opp_fire_no_progress < 0.0:
            opp_weighting_label = "fire_penalized_for_vp_progress_risk"
        elif opp_skip_capture_preserve > 0.0:
            opp_weighting_label = "skip_bonus_for_capture_preservation"
        xai_decision_rows.append(
            {
                "iteration": int(iteration_idx),
                "episode": int(episode_idx),
                "step": int(payload.get("step", 0)),
                "game_turn": int(game_turn),
                "to_play": str(payload.get("to_play", "")),
                "action_id": str(payload.get("action_id", "")),
                "action_kind": str(payload.get("action_kind", "")),
                "policy_top_actions": list(xai_policy_top_actions),
                "policy_top_probs": list(xai_policy_top_probs),
                "latent_top_indices": list(xai_latent_top_indices),
                "latent_top_values": list(xai_latent_top_values),
                "latent_l2_norm": float(payload.get("latent_l2_norm", 0.0)),
                "predicted_value_root": float(payload.get("predicted_value_root", 0.0)),
                "dynamics_pred_reward": float(payload.get("dynamics_pred_reward", 0.0)),
                "dynamics_next_latent_l2": float(payload.get("dynamics_next_latent_l2", 0.0)),
                "dynamics_delta_l2": float(payload.get("dynamics_delta_l2", 0.0)),
                "vp_captures": int(payload.get("vp_captures", 0)),
                "damage_dealt": float(payload.get("damage_dealt", 0.0)),
                "kills_dealt": int(payload.get("kills_dealt", 0)),
                "acting_q": int(payload.get("acting_q", 0)),
                "acting_r": int(payload.get("acting_r", 0)),
                "target_q": int(payload.get("target_q", 0)),
                "target_r": int(payload.get("target_r", 0)),
                "objective_had_opportunity": int(payload.get("objective_had_opportunity", 0)),
                "objective_distance_before": float(payload.get("objective_distance_before", -1.0)),
                "objective_distance_after": float(payload.get("objective_distance_after", -1.0)),
                "objective_progress_delta": float(payload.get("objective_progress_delta", 0.0)),
                "objective_converted": int(payload.get("objective_converted", 0)),
                "opportunity_fire_no_progress": float(opp_fire_no_progress),
                "opportunity_skip_capture_preserve": float(opp_skip_capture_preserve),
                "opportunity_vp_weighting_label": str(opp_weighting_label),
                "mcts_entropy": float(payload.get("mcts_entropy", 0.0)),
                "mcts_margin": float(payload.get("mcts_margin", 0.0)),
                "chosen_action_prob": float(payload.get("chosen_action_prob", 0.0)),
            }
        )
        if xai_policy_top_actions:
            top1 = str(xai_policy_top_actions[0])
            xai_policy_top1_counts[top1] = xai_policy_top1_counts.get(top1, 0) + 1
        if xai_policy_top_probs:
            xai_policy_top1_prob_sum += float(xai_policy_top_probs[0])
            xai_policy_top1_prob_count += 1
        for dim_idx in xai_latent_top_indices:
            xai_latent_top_dim_counts[int(dim_idx)] = xai_latent_top_dim_counts.get(int(dim_idx), 0) + 1
        xai_latent_l2_norm_sum += float(payload.get("latent_l2_norm", 0.0))
        xai_latent_l2_norm_count += 1
        xai_predicted_value_root_sum += float(payload.get("predicted_value_root", 0.0))
        xai_predicted_value_root_count += 1
        xai_dynamics_pred_reward_sum += float(payload.get("dynamics_pred_reward", 0.0))
        xai_dynamics_pred_reward_count += 1
        xai_dynamics_next_latent_l2_sum += float(payload.get("dynamics_next_latent_l2", 0.0))
        xai_dynamics_next_latent_l2_count += 1
        xai_dynamics_delta_l2_sum += float(payload.get("dynamics_delta_l2", 0.0))
        xai_dynamics_delta_l2_count += 1
        t_damage_map = dict(payload.get("attack_target_class_damage", {}) or {})
        t_kills_map = dict(payload.get("attack_target_class_kills", {}) or {})
        attacker_cls = str(unit_key).strip() or "UNKNOWN_ATTACKER"
        target_attempt_cls = str(payload.get("attack_target_class_attempt", "")).strip()
        if is_attack:
            target_cls = target_attempt_cls or "UNKNOWN_TARGET"
            pair_key = f"{attacker_cls}->{target_cls}"
            if pair_key not in matchup_effectiveness:
                matchup_effectiveness[pair_key] = {
                    "count": 0.0,
                    "success_count": 0.0,
                    "damage_sum": 0.0,
                    "kills_sum": 0.0,
                }
            d = float(t_damage_map.get(target_cls, 0.0))
            k = float(t_kills_map.get(target_cls, 0))
            if d <= 0.0 and k <= 0.0 and (target_cls == "UNKNOWN_TARGET") and t_damage_map:
                d = float(sum(float(v) for v in t_damage_map.values()))
                k = float(sum(float(v) for v in t_kills_map.values()))
            matchup_effectiveness[pair_key]["count"] += 1.0
            matchup_effectiveness[pair_key]["damage_sum"] += d
            matchup_effectiveness[pair_key]["kills_sum"] += k
            if d > 0.0 or k > 0.0:
                matchup_effectiveness[pair_key]["success_count"] += 1.0
        if is_attack:
            dist = float(payload.get("attack_distance_mean", -1.0))
            cover = float(payload.get("attack_target_cover_mean", -1.0))
            los = float(payload.get("attack_target_los_block_mean", -1.0))
            if dist <= 1.5 and dist >= 0.0:
                dist_bucket = "dist_near"
            elif dist <= 3.5:
                dist_bucket = "dist_mid"
            elif dist > 3.5:
                dist_bucket = "dist_far"
            else:
                continue
            if cover <= 0.15 and cover >= 0.0:
                cover_bucket = "cover_low"
            elif cover <= 0.35:
                cover_bucket = "cover_mid"
            elif cover > 0.35:
                cover_bucket = "cover_high"
            else:
                continue
            los_bucket = "los_blocked" if los >= 0.5 else "los_clear"
            ctx_key = f"{dist_bucket}|{cover_bucket}|{los_bucket}"
            if ctx_key not in context_effectiveness:
                context_effectiveness[ctx_key] = {
                    "count": 0.0,
                    "success_count": 0.0,
                    "damage_sum": 0.0,
                    "kills_sum": 0.0,
                }
            context_effectiveness[ctx_key]["count"] += 1.0
            context_effectiveness[ctx_key]["damage_sum"] += float(damage_val)
            context_effectiveness[ctx_key]["kills_sum"] += float(kills_val)
            if float(damage_val) > 0.0 or float(kills_val) > 0.0:
                context_effectiveness[ctx_key]["success_count"] += 1.0
        if is_attack:
            unit_attack_counts[unit_id] = unit_attack_counts.get(unit_id, 0) + 1
        unit_damage[unit_id] = unit_damage.get(unit_id, 0.0) + float(damage_val)
        unit_kills[unit_id] = unit_kills.get(unit_id, 0) + int(kills_val)
        unit_side_map[unit_id] = unit_side
        unit_key_map[unit_id] = unit_key
        unit_label_map[unit_id] = unit_label
        if unit_side not in side_unit_counts:
            side_unit_counts[unit_side] = {}
        side_unit_counts[unit_side][unit_id] = side_unit_counts[unit_side].get(unit_id, 0) + 1

    for (iteration_idx, episode_idx, game_turn, _side), snapshots in turn_side_snapshots.items():
        if not snapshots:
            continue
        candidates: set[str] = set()
        for s in snapshots:
            candidates.update(s)
        for unit_id in candidates:
            if (iteration_idx, episode_idx, game_turn, unit_id) in unit_turn_activated:
                continue
            first_idx = -1
            for i, s in enumerate(snapshots):
                if unit_id in s:
                    first_idx = i
                    break
            if first_idx < 0:
                continue
            lost_before_turn_end = any(
                unit_id not in snapshots[j]
                for j in range(first_idx + 1, len(snapshots))
            )
            if lost_before_turn_end:
                unit_blocked_before_activation_turns[unit_id] = (
                    unit_blocked_before_activation_turns.get(unit_id, 0) + 1
                )

    tactical_tradeoff_totals = {
        "attacks": 0.0,
        "damage_out_sum": 0.0,
        "damage_in_next2_sum": 0.0,
    }
    tactical_tradeoff_by_side: dict[str, dict[str, float]] = {}
    for (_it, _ep), transitions in episode_transitions_by_key.items():
        for i, p in enumerate(transitions):
            side = str(p.get("unit_side", "")).strip() or "unknown"
            action_kind = str(p.get("action_kind", "")).strip().upper()
            is_attack = action_kind not in {"", "MOVE", "WAIT", "TIMEOUT"}
            if not is_attack:
                continue
            out_dmg = float(p.get("damage_dealt", 0.0))
            in_dmg = 0.0
            for j in range(i + 1, min(i + 3, len(transitions))):
                p2 = transitions[j]
                side2 = str(p2.get("unit_side", "")).strip() or "unknown"
                if side2 == side:
                    continue
                in_dmg += float(p2.get("damage_dealt", 0.0))
            tactical_tradeoff_totals["attacks"] += 1.0
            tactical_tradeoff_totals["damage_out_sum"] += out_dmg
            tactical_tradeoff_totals["damage_in_next2_sum"] += in_dmg
            if side not in tactical_tradeoff_by_side:
                tactical_tradeoff_by_side[side] = {
                    "attacks": 0.0,
                    "damage_out_sum": 0.0,
                    "damage_in_next2_sum": 0.0,
                }
            tactical_tradeoff_by_side[side]["attacks"] += 1.0
            tactical_tradeoff_by_side[side]["damage_out_sum"] += out_dmg
            tactical_tradeoff_by_side[side]["damage_in_next2_sum"] += in_dmg

    units_total = max(1, transition_count)
    vp_initial_sum_by_side: dict[str, int] = {}
    vp_final_sum_by_side: dict[str, int] = {}
    vp_episode_count_by_side: dict[str, int] = {}
    all_episode_keys = set(episode_first_vp_by_key.keys()) | set(episode_last_vp_by_key.keys())
    for ep_key in all_episode_keys:
        init_payload = episode_first_vp_by_key.get(ep_key, {})
        final_payload = episode_last_vp_by_key.get(ep_key, {})
        all_sides = set(init_payload.keys()) | set(final_payload.keys())
        for side in all_sides:
            init_val = int(init_payload.get(side, 0))
            final_val = int(final_payload.get(side, init_val))
            vp_initial_sum_by_side[side] = vp_initial_sum_by_side.get(side, 0) + init_val
            vp_final_sum_by_side[side] = vp_final_sum_by_side.get(side, 0) + final_val
            vp_episode_count_by_side[side] = vp_episode_count_by_side.get(side, 0) + 1
    vp_initial_avg_by_side = {
        side: (
            float(vp_initial_sum_by_side.get(side, 0))
            / float(max(1, vp_episode_count_by_side.get(side, 0)))
        )
        for side in sorted(vp_episode_count_by_side.keys())
    }
    vp_final_avg_by_side = {
        side: (
            float(vp_final_sum_by_side.get(side, 0))
            / float(max(1, vp_episode_count_by_side.get(side, 0)))
        )
        for side in sorted(vp_episode_count_by_side.keys())
    }
    vp_net_sum_by_side = {
        side: int(vp_gain_sum_by_side.get(side, 0) - vp_loss_sum_by_side.get(side, 0))
        for side in sorted(set(vp_gain_sum_by_side.keys()) | set(vp_loss_sum_by_side.keys()))
    }
    vp_net_avg_per_episode_by_side = {
        side: (
            float(vp_net_sum_by_side.get(side, 0))
            / float(max(1, vp_episode_count_by_side.get(side, 0)))
        )
        for side in sorted(vp_episode_count_by_side.keys())
    }
    def _objective_reason_for_payload(payload: dict) -> str:
        action_kind_raw = str(payload.get("action_kind", "")).strip().upper()
        delta = float(payload.get("objective_progress_delta", 0.0))
        if delta > 0.0:
            return "progress_taken"
        if action_kind_raw in {"WAIT", "TIMEOUT"}:
            return "passive_wait_or_timeout"
        if action_kind_raw == "MOVE":
            return "moved_without_closing_distance"
        if action_kind_raw in {
            "FIRE_MOVE",
            "RANGED_DIRECT",
            "RANGED_INDIRECT",
            "OPPORTUNITY_FIRE",
            "MELEE",
            "ASSAULT_MELEE",
            "CAPTURE",
            "FIRE_CAPTURE",
        }:
            return "attack_or_capture_without_progress"
        return "other_non_progress_action"

    def _objective_path_for_payload(payload: dict) -> str:
        delta = float(payload.get("objective_progress_delta", 0.0))
        converted = int(payload.get("objective_converted", 0)) > 0
        if delta > 0.0 and converted:
            return "progress_to_converted"
        if delta > 0.0 and not converted:
            return "progress_to_not_converted"
        if delta <= 0.0 and converted:
            return "no_progress_to_converted"
        return "no_progress_to_not_converted"

    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return -1.0
        vv = sorted(float(v) for v in values)
        if len(vv) == 1:
            return float(vv[0])
        pp = max(0.0, min(100.0, float(p)))
        pos = (pp / 100.0) * float(len(vv) - 1)
        lo = int(pos)
        hi = min(len(vv) - 1, lo + 1)
        frac = float(pos - lo)
        return float(vv[lo] * (1.0 - frac) + vv[hi] * frac)

    path_transition_counts_global: dict[tuple[str, str], int] = {}
    path_transition_counts_by_side: dict[str, dict[tuple[str, str], int]] = {}
    reason_ttc_global: dict[str, dict[str, float | list[float]]] = {}
    reason_ttc_by_side: dict[str, dict[str, dict[str, float | list[float]]]] = {}
    path_ttc_global: dict[str, dict[str, float | list[float]]] = {}
    path_ttc_by_side: dict[str, dict[str, dict[str, float | list[float]]]] = {}
    progress_to_conversion_by_side: dict[str, dict[str, float]] = {}
    for (iter_idx, ep_idx), plist in episode_transitions_by_key.items():
        by_side: dict[str, list[dict]] = {}
        for p in plist:
            if int(p.get("objective_had_opportunity", 0)) <= 0:
                continue
            side = str(p.get("unit_side", "")).strip() or "unknown"
            by_side.setdefault(side, []).append(p)
        for side, rows in by_side.items():
            rows_sorted = sorted(rows, key=lambda r: int(r.get("game_turn", 0)))
            conversion_turns = [
                int(r.get("game_turn", 0))
                for r in rows_sorted
                if int(r.get("objective_converted", 0)) > 0
            ]
            for idx in range(len(rows_sorted) - 1):
                p0 = rows_sorted[idx]
                p1 = rows_sorted[idx + 1]
                from_path = _objective_path_for_payload(p0)
                to_path = _objective_path_for_payload(p1)
                key = (str(from_path), str(to_path))
                path_transition_counts_global[key] = path_transition_counts_global.get(key, 0) + 1
                if side not in path_transition_counts_by_side:
                    path_transition_counts_by_side[side] = {}
                path_transition_counts_by_side[side][key] = path_transition_counts_by_side[side].get(key, 0) + 1
            for p in rows_sorted:
                turn = int(p.get("game_turn", 0))
                next_conv = next((ct for ct in conversion_turns if ct >= turn), None)
                reason = _objective_reason_for_payload(p)
                path = _objective_path_for_payload(p)
                if side not in progress_to_conversion_by_side:
                    progress_to_conversion_by_side[side] = {
                        "progress_events": 0.0,
                        "converted_any": 0.0,
                        "converted_within_2_turns": 0.0,
                    }
                if float(p.get("objective_progress_delta", 0.0)) > 0.0:
                    progress_to_conversion_by_side[side]["progress_events"] += 1.0
                    if next_conv is not None:
                        progress_to_conversion_by_side[side]["converted_any"] += 1.0
                        if int(next_conv - turn) <= 2:
                            progress_to_conversion_by_side[side]["converted_within_2_turns"] += 1.0
                if reason not in reason_ttc_global:
                    reason_ttc_global[reason] = {"with_conversion": 0.0, "no_conversion": 0.0, "delays": []}
                if path not in path_ttc_global:
                    path_ttc_global[path] = {"with_conversion": 0.0, "no_conversion": 0.0, "delays": []}
                if side not in reason_ttc_by_side:
                    reason_ttc_by_side[side] = {}
                if side not in path_ttc_by_side:
                    path_ttc_by_side[side] = {}
                if reason not in reason_ttc_by_side[side]:
                    reason_ttc_by_side[side][reason] = {"with_conversion": 0.0, "no_conversion": 0.0, "delays": []}
                if path not in path_ttc_by_side[side]:
                    path_ttc_by_side[side][path] = {"with_conversion": 0.0, "no_conversion": 0.0, "delays": []}
                if next_conv is None:
                    reason_ttc_global[reason]["no_conversion"] = float(reason_ttc_global[reason]["no_conversion"]) + 1.0
                    path_ttc_global[path]["no_conversion"] = float(path_ttc_global[path]["no_conversion"]) + 1.0
                    reason_ttc_by_side[side][reason]["no_conversion"] = float(reason_ttc_by_side[side][reason]["no_conversion"]) + 1.0
                    path_ttc_by_side[side][path]["no_conversion"] = float(path_ttc_by_side[side][path]["no_conversion"]) + 1.0
                else:
                    d = float(max(0, next_conv - turn))
                    reason_ttc_global[reason]["with_conversion"] = float(reason_ttc_global[reason]["with_conversion"]) + 1.0
                    path_ttc_global[path]["with_conversion"] = float(path_ttc_global[path]["with_conversion"]) + 1.0
                    reason_ttc_by_side[side][reason]["with_conversion"] = float(reason_ttc_by_side[side][reason]["with_conversion"]) + 1.0
                    path_ttc_by_side[side][path]["with_conversion"] = float(path_ttc_by_side[side][path]["with_conversion"]) + 1.0
                    (reason_ttc_global[reason]["delays"]).append(d)
                    (path_ttc_global[path]["delays"]).append(d)
                    (reason_ttc_by_side[side][reason]["delays"]).append(d)
                    (path_ttc_by_side[side][path]["delays"]).append(d)

    def _ttc_rows(stats: dict[str, dict[str, float | list[float]]]) -> list[dict]:
        rows = []
        for key, vals in sorted(stats.items(), key=lambda kv: kv[0]):
            delays = list(vals.get("delays", []) or [])
            with_conv = int(vals.get("with_conversion", 0.0))
            no_conv = int(vals.get("no_conversion", 0.0))
            total = int(with_conv + no_conv)
            rows.append(
                {
                    "key": str(key),
                    "count": total,
                    "with_conversion": with_conv,
                    "no_conversion": no_conv,
                    "conversion_observed_rate": (
                        float(with_conv) / float(max(1, total))
                    ),
                    "ttc_mean_turns": (
                        float(sum(delays) / float(max(1, len(delays))))
                        if delays
                        else -1.0
                    ),
                    "ttc_p50_turns": _percentile(delays, 50.0) if delays else -1.0,
                    "ttc_p90_turns": _percentile(delays, 90.0) if delays else -1.0,
                }
            )
        return rows

    transition_rows_global = []
    if path_transition_counts_global:
        from_totals: dict[str, int] = {}
        for (f, _t), c in path_transition_counts_global.items():
            from_totals[f] = from_totals.get(f, 0) + int(c)
        for (f, t), c in sorted(path_transition_counts_global.items(), key=lambda kv: kv[1], reverse=True):
            transition_rows_global.append(
                {
                    "from_path": str(f),
                    "to_path": str(t),
                    "count": int(c),
                    "rate_from": (
                        float(c) / float(max(1, int(from_totals.get(f, 0))))
                    ),
                }
            )
    transition_rows_by_side: dict[str, list[dict]] = {}
    for side, cmap in sorted(path_transition_counts_by_side.items(), key=lambda kv: kv[0]):
        from_totals: dict[str, int] = {}
        for (f, _t), c in cmap.items():
            from_totals[f] = from_totals.get(f, 0) + int(c)
        transition_rows_by_side[side] = [
            {
                "from_path": str(f),
                "to_path": str(t),
                "count": int(c),
                "rate_from": (
                    float(c) / float(max(1, int(from_totals.get(f, 0))))
                ),
            }
            for (f, t), c in sorted(cmap.items(), key=lambda kv: kv[1], reverse=True)
        ]
    conversion_path_global_counts = {
        key: int(
            sum(
                vals.get("conversion_path_counts", {}).get(key, 0.0)
                for vals in objective_explain_by_side.values()
            )
        )
        for key in sorted(
            {
                k
                for vals in objective_explain_by_side.values()
                for k in vals.get("conversion_path_counts", {}).keys()
            }
        )
    }
    no_progress_l2_global_counts = {
        key: int(
            sum(
                vals.get("no_progress_reason_l2_counts", {}).get(key, 0.0)
                for vals in objective_explain_by_side.values()
            )
        )
        for key in sorted(
            {
                k
                for vals in objective_explain_by_side.values()
                for k in vals.get("no_progress_reason_l2_counts", {}).keys()
            }
        )
    }
    converted_after_progress_global = float(conversion_path_global_counts.get("converted_after_progress", 0))
    progress_actions_global = float(
        sum(float(v.get("progress_actions", 0.0)) for v in objective_funnel_by_side.values())
    )
    near_vp_global = {
        "opportunities": float(sum(float(v.get("near_vp_opportunities", 0.0)) for v in objective_near_vp_by_side.values())),
        "progress_actions": float(sum(float(v.get("near_vp_progress_actions", 0.0)) for v in objective_near_vp_by_side.values())),
        "conversions": float(sum(float(v.get("near_vp_conversions", 0.0)) for v in objective_near_vp_by_side.values())),
    }
    far_vp_global = {
        "opportunities": float(sum(float(v.get("far_vp_opportunities", 0.0)) for v in objective_near_vp_by_side.values())),
        "progress_actions": float(sum(float(v.get("far_vp_progress_actions", 0.0)) for v in objective_near_vp_by_side.values())),
        "conversions": float(sum(float(v.get("far_vp_conversions", 0.0)) for v in objective_near_vp_by_side.values())),
    }
    progress_events_global = float(
        sum(float(v.get("progress_events", 0.0)) for v in progress_to_conversion_by_side.values())
    )
    converted_any_global = float(
        sum(float(v.get("converted_any", 0.0)) for v in progress_to_conversion_by_side.values())
    )
    converted_within2_global = float(
        sum(float(v.get("converted_within_2_turns", 0.0)) for v in progress_to_conversion_by_side.values())
    )
    harmful_paths_top = []
    for row in _ttc_rows(path_ttc_global):
        if int(row.get("count", 0)) <= 0:
            continue
        if str(row.get("key", "")).endswith("to_not_converted"):
            harmful_paths_top.append(
                {
                    "path": str(row.get("key", "")),
                    "count": int(row.get("count", 0)),
                    "no_conversion_rate": (
                        float(row.get("no_conversion", 0))
                        / float(max(1, int(row.get("count", 0))))
                    ),
                    "ttc_p50_turns": float(row.get("ttc_p50_turns", -1.0)),
                    "ttc_p90_turns": float(row.get("ttc_p90_turns", -1.0)),
                }
            )
    harmful_paths_top = sorted(
        harmful_paths_top,
        key=lambda r: (float(r.get("no_conversion_rate", 0.0)), int(r.get("count", 0))),
        reverse=True,
    )[:8]
    units_by_side = {}
    for side, counts in side_unit_counts.items():
        side_total = max(1, sum(counts.values()))
        active_units = max(1, len(counts))
        expected_actions_per_unit = float(side_total) / float(active_units)
        units_by_side[side] = {
            "total_actions": int(sum(counts.values())),
            "active_units": int(active_units),
            "expected_actions_per_active_unit": float(expected_actions_per_unit),
            "units": [
                {
                    "unit_id": u,
                    "count": c,
                    "actions": c,
                    "attacks": int(unit_attack_counts.get(u, 0)),
                    "rate_global": (c / units_total),
                    "rate_in_side": (c / side_total),
                    "expected_actions_in_side": float(expected_actions_per_unit),
                    "delta_vs_expected_in_side": float(c - expected_actions_per_unit),
                    "load_ratio_in_side": (
                        float(c) / float(max(1e-9, expected_actions_per_unit))
                    ),
                    "turns_eligible": int(unit_turns_eligible.get(u, 0)),
                    "turns_activated": int(unit_turns_activated.get(u, c)),
                    "activation_coverage": (
                        (
                            float(unit_turns_activated.get(u, c))
                            / float(max(1, int(unit_turns_eligible.get(u, 0))))
                        )
                        if int(unit_turns_eligible.get(u, 0)) > 0
                        else 0.0
                    ),
                    "eligible_turns": int(len(unit_eligible_turn_keys.get(u, set()))),
                    "activated_turns": int(len(unit_activated_turn_keys.get(u, set()))),
                    "turn_activation_coverage": (
                        float(len(unit_activated_turn_keys.get(u, set())))
                        / float(max(1, len(unit_eligible_turn_keys.get(u, set()))))
                        if len(unit_eligible_turn_keys.get(u, set())) > 0
                        else 0.0
                    ),
                    "blocked_before_activation_turns": int(
                        unit_blocked_before_activation_turns.get(u, 0)
                    ),
                    "damage": float(unit_damage.get(u, 0.0)),
                    "kills": int(unit_kills.get(u, 0)),
                    "damage_per_attack": (
                        float(unit_damage.get(u, 0.0))
                        / float(max(1, int(unit_attack_counts.get(u, 0))))
                    ),
                    "unit_key": str(unit_key_map.get(u, "")),
                    "unit_label": str(unit_label_map.get(u, "")),
                    "category": str(unit_key_map.get(u, "")).split("_")[-1]
                    if unit_key_map.get(u, "")
                    else "",
                    "class_name": str(unit_key_map.get(u, "")),
                }
                for u, c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
            ],
        }
    units_sides = {
        "transition_events": transition_count,
        "side_turn_counts": side_turn_counts,
        "side_turn_rates": {k: (v / units_total) for k, v in side_turn_counts.items()},
        "top_action_units": [
            {
                "unit_id": u,
                "side": unit_side_map.get(u, "unknown"),
                "count": c,
                "rate_global": (c / units_total),
            }
            for u, c in sorted(unit_action_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
        ],
        "units_by_side": units_by_side,
        "global_actions": {
            "total_actions": int(sum(action_kind_counts.values())),
            "kinds": [
                {
                    "action_kind": k,
                    "count": int(v),
                    "rate_global": (float(v) / float(units_total)),
                }
                for k, v in sorted(action_kind_counts.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "kinds_by_side": {
                side: [
                    {
                        "action_kind": k,
                        "count": int(v),
                        "rate_in_side": (float(v) / float(max(1, side_turn_counts.get(side, 0)))),
                    }
                    for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
                ]
                for side, counts in action_kind_counts_by_side.items()
            },
        },
        "vp_summary": {
            "vp_related_actions_total": int(sum(vp_actions_by_side.values())),
            "capture_actions_total": int(sum(capture_actions_by_side.values())),
            "vp_captures_total": int(sum(vp_captures_by_side.values())),
            "vp_captures_per_1000_transitions": (
                float(sum(vp_captures_by_side.values())) * 1000.0 / float(max(1, transition_count))
            ),
            "vp_initial_by_side": {k: int(v) for k, v in vp_initial_by_side.items()},
            "vp_final_by_side": {k: int(v) for k, v in vp_final_by_side.items()},
            "vp_initial_avg_by_side": {k: float(v) for k, v in vp_initial_avg_by_side.items()},
            "vp_final_avg_by_side": {k: float(v) for k, v in vp_final_avg_by_side.items()},
            "vp_gain_sum_by_side": {k: int(v) for k, v in vp_gain_sum_by_side.items()},
            "vp_loss_sum_by_side": {k: int(v) for k, v in vp_loss_sum_by_side.items()},
            "vp_net_sum_by_side": {k: int(v) for k, v in vp_net_sum_by_side.items()},
            "vp_net_avg_per_episode_by_side": {
                k: float(v) for k, v in vp_net_avg_per_episode_by_side.items()
            },
            "vp_episode_count_by_side": {k: int(v) for k, v in vp_episode_count_by_side.items()},
            "vp_related_action_rate_global": (
                float(sum(vp_actions_by_side.values())) / float(units_total)
            ),
            "capture_action_rate_global": (
                float(sum(capture_actions_by_side.values())) / float(units_total)
            ),
            "vp_capture_rate_global": (
                float(sum(vp_captures_by_side.values())) / float(units_total)
            ),
            "unique_units_with_vp_captures_total": int(
                len(set().union(*vp_units_by_side.values())) if vp_units_by_side else 0
            ),
            "by_side": {
                side: {
                    "vp_related_actions": int(vp_actions_by_side.get(side, 0)),
                    "capture_actions": int(capture_actions_by_side.get(side, 0)),
                    "vp_captures": int(vp_captures_by_side.get(side, 0)),
                    "vp_initial": float(vp_initial_avg_by_side.get(side, 0.0)),
                    "vp_final": float(vp_final_avg_by_side.get(side, 0.0)),
                    "vp_gained_sum": int(vp_gain_sum_by_side.get(side, 0)),
                    "vp_lost_sum": int(vp_loss_sum_by_side.get(side, 0)),
                    "vp_net_sum": int(vp_net_sum_by_side.get(side, 0)),
                    "vp_net_avg_per_episode": float(vp_net_avg_per_episode_by_side.get(side, 0.0)),
                    "vp_episode_count": int(vp_episode_count_by_side.get(side, 0)),
                    "vp_related_rate_in_side": (
                        float(vp_actions_by_side.get(side, 0))
                        / float(max(1, side_turn_counts.get(side, 0)))
                    ),
                    "capture_rate_in_side": (
                        float(capture_actions_by_side.get(side, 0))
                        / float(max(1, side_turn_counts.get(side, 0)))
                    ),
                    "vp_capture_rate_in_side": (
                        float(vp_captures_by_side.get(side, 0))
                        / float(max(1, side_turn_counts.get(side, 0)))
                    ),
                    "unique_units_with_vp_actions": int(len(vp_units_by_side.get(side, set()))),
                    "unique_units_with_vp_captures": int(len(vp_units_by_side.get(side, set()))),
                }
                for side in sorted(side_turn_counts.keys())
            },
        },
        "strategy_summary": {
            "total_actions": int(sum(strategy_counts.values())),
            "strategies": [
                {
                    "strategy": k,
                    "count": int(v),
                    "rate_global": (float(v) / float(units_total)),
                }
                for k, v in sorted(strategy_counts.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "strategies_by_side": {
                side: [
                    {
                        "strategy": k,
                        "count": int(v),
                        "rate_in_side": (
                            float(v) / float(max(1, side_turn_counts.get(side, 0)))
                        ),
                    }
                    for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
                ]
                for side, counts in strategy_counts_by_side.items()
            },
        },
        "reward_summary": {
            "components_total": {
                k: float(v) for k, v in sorted(reward_component_sums.items(), key=lambda kv: kv[0])
            },
            "components_avg_per_transition": {
                k: (float(v) / float(max(1, transition_count)))
                for k, v in sorted(reward_component_sums.items(), key=lambda kv: kv[0])
            },
            "components_by_side": {
                side: {
                    k: float(v)
                    for k, v in sorted(comp.items(), key=lambda kv: kv[0])
                }
                for side, comp in sorted(reward_component_sums_by_side.items(), key=lambda kv: kv[0])
            },
        },
        "option_space_summary": {
            "avg_per_transition": {
                k: (float(v) / float(max(1, transition_count)))
                for k, v in sorted(option_space_totals.items(), key=lambda kv: kv[0])
            },
            "avg_per_transition_by_side": {
                side: {
                    k: (
                        float(v)
                        / float(max(1, side_turn_counts.get(side, 0)))
                    )
                    for k, v in sorted(vals.items(), key=lambda kv: kv[0])
                }
                for side, vals in sorted(option_space_by_side.items(), key=lambda kv: kv[0])
            },
        },
        "diagnostics_summary": {
            "attack_effectiveness": {
                "by_action_kind": [
                    {
                        "action_kind": kind,
                        "count": int(vals.get("count", 0.0)),
                        "attack_success_estimate": (
                            float(vals.get("success_count", 0.0)) / float(max(1.0, vals.get("count", 0.0)))
                        ),
                        "expected_damage_estimate": (
                            float(vals.get("damage_sum", 0.0)) / float(max(1.0, vals.get("count", 0.0)))
                        ),
                        "expected_kills_estimate": (
                            float(vals.get("kills_sum", 0.0)) / float(max(1.0, vals.get("count", 0.0)))
                        ),
                    }
                    for kind, vals in sorted(
                        attack_effectiveness_by_kind.items(),
                        key=lambda kv: kv[1].get("count", 0.0),
                        reverse=True,
                    )
                ],
                "by_side_action_kind": {
                    side: [
                        {
                            "action_kind": kind,
                            "count": int(vals.get("count", 0.0)),
                            "attack_success_estimate": (
                                float(vals.get("success_count", 0.0))
                                / float(max(1.0, vals.get("count", 0.0)))
                            ),
                            "expected_damage_estimate": (
                                float(vals.get("damage_sum", 0.0))
                                / float(max(1.0, vals.get("count", 0.0)))
                            ),
                            "expected_kills_estimate": (
                                float(vals.get("kills_sum", 0.0))
                                / float(max(1.0, vals.get("count", 0.0)))
                            ),
                        }
                        for kind, vals in sorted(
                            payload.items(),
                            key=lambda kv: kv[1].get("count", 0.0),
                            reverse=True,
                        )
                    ]
                    for side, payload in sorted(
                        attack_effectiveness_by_side_kind.items(),
                        key=lambda kv: kv[0],
                    )
                },
            },
            "search_efficiency_avg": {
                "mcts_total_visits": (
                    float(search_efficiency_totals["mcts_total_visits"]) / float(max(1, transition_count))
                ),
                "mcts_active_actions": (
                    float(search_efficiency_totals["mcts_active_actions"]) / float(max(1, transition_count))
                ),
                "mcts_active_ratio": (
                    float(search_efficiency_totals["mcts_active_actions"])
                    / float(max(1e-9, search_efficiency_totals["mcts_total_visits"]))
                ),
            },
            "value_calibration": {
                "mae": (
                    float(sum(abs(p - r) for p, r in value_calibration_pairs))
                    / float(max(1, len(value_calibration_pairs)))
                ),
                "bins": [
                    {
                        "bin": b["label"],
                        "count": int(len(b["items"])),
                        "avg_predicted": (
                            float(sum(p for p, _ in b["items"])) / float(max(1, len(b["items"])))
                            if b["items"]
                            else 0.0
                        ),
                        "avg_realized_return": (
                            float(sum(r for _, r in b["items"])) / float(max(1, len(b["items"])))
                            if b["items"]
                            else 0.0
                        ),
                        "mae": (
                            float(sum(abs(p - r) for p, r in b["items"])) / float(max(1, len(b["items"])))
                            if b["items"]
                            else 0.0
                        ),
                    }
                    for b in [
                        {"label": "<=-0.5", "items": [(p, r) for p, r in value_calibration_pairs if p <= -0.5]},
                        {"label": "(-0.5,0.0]", "items": [(p, r) for p, r in value_calibration_pairs if -0.5 < p <= 0.0]},
                        {"label": "(0.0,0.5]", "items": [(p, r) for p, r in value_calibration_pairs if 0.0 < p <= 0.5]},
                        {"label": ">0.5", "items": [(p, r) for p, r in value_calibration_pairs if p > 0.5]},
                    ]
                ],
            },
            "value_calibration_by_phase": {
                phase: {
                    "count": int(len(items)),
                    "mae": (
                        float(sum(abs(p - r) for p, r in items)) / float(max(1, len(items)))
                        if items
                        else 0.0
                    ),
                    "avg_predicted": (
                        float(sum(p for p, _ in items)) / float(max(1, len(items)))
                        if items
                        else 0.0
                    ),
                    "avg_realized_return": (
                        float(sum(r for _, r in items)) / float(max(1, len(items)))
                        if items
                        else 0.0
                    ),
                }
                for phase, items in sorted(value_calibration_phase_pairs.items(), key=lambda kv: kv[0])
            },
            "matchup_effectiveness": [
                {
                    "matchup": key,
                    "count": int(vals.get("count", 0.0)),
                    "attack_success_estimate": (
                        float(vals.get("success_count", 0.0))
                        / float(max(1.0, vals.get("count", 0.0)))
                    ),
                    "expected_damage_estimate": (
                        float(vals.get("damage_sum", 0.0))
                        / float(max(1.0, vals.get("count", 0.0)))
                    ),
                    "expected_kills_estimate": (
                        float(vals.get("kills_sum", 0.0))
                        / float(max(1.0, vals.get("count", 0.0)))
                    ),
                }
                for key, vals in sorted(
                    matchup_effectiveness.items(),
                    key=lambda kv: kv[1].get("count", 0.0),
                    reverse=True,
                )
            ],
            "context_effectiveness": [
                {
                    "context": key,
                    "count": int(vals.get("count", 0.0)),
                    "attack_success_estimate": (
                        float(vals.get("success_count", 0.0))
                        / float(max(1.0, vals.get("count", 0.0)))
                    ),
                    "expected_damage_estimate": (
                        float(vals.get("damage_sum", 0.0))
                        / float(max(1.0, vals.get("count", 0.0)))
                    ),
                    "expected_kills_estimate": (
                        float(vals.get("kills_sum", 0.0))
                        / float(max(1.0, vals.get("count", 0.0)))
                    ),
                }
                for key, vals in sorted(
                    context_effectiveness.items(),
                    key=lambda kv: kv[1].get("count", 0.0),
                    reverse=True,
                )
            ],
            "decision_flip_rate": {
                "global": {
                    "opportunities": int(sum(v.get("opportunities", 0.0) for v in decision_flip_by_side.values())),
                    "flips": int(sum(v.get("flips", 0.0) for v in decision_flip_by_side.values())),
                    "rate": (
                        float(sum(v.get("flips", 0.0) for v in decision_flip_by_side.values()))
                        / float(max(1.0, sum(v.get("opportunities", 0.0) for v in decision_flip_by_side.values())))
                    ),
                },
                "by_side": {
                    side: {
                        "opportunities": int(sum(v.get("opportunities", 0.0) for k, v in decision_flip_by_side.items() if len(k) >= 3 and str(k[2]) == side)),
                        "flips": int(sum(v.get("flips", 0.0) for k, v in decision_flip_by_side.items() if len(k) >= 3 and str(k[2]) == side)),
                        "rate": (
                            float(sum(v.get("flips", 0.0) for k, v in decision_flip_by_side.items() if len(k) >= 3 and str(k[2]) == side))
                            / float(max(1.0, sum(v.get("opportunities", 0.0) for k, v in decision_flip_by_side.items() if len(k) >= 3 and str(k[2]) == side)))
                        ),
                    }
                    for side in sorted(set(str(k[2]) for k in decision_flip_by_side.keys() if len(k) >= 3))
                },
            },
            "objective_opportunity_conversion": {
                "global": {
                    "opportunities": int(sum(v.get("opportunities", 0.0) for v in objective_opportunity_by_side.values())),
                    "conversions": int(sum(v.get("conversions", 0.0) for v in objective_opportunity_by_side.values())),
                    "rate": (
                        float(sum(v.get("conversions", 0.0) for v in objective_opportunity_by_side.values()))
                        / float(max(1.0, sum(v.get("opportunities", 0.0) for v in objective_opportunity_by_side.values())))
                    ),
                },
                "by_side": {
                    side: {
                        "opportunities": int(vals.get("opportunities", 0.0)),
                        "conversions": int(vals.get("conversions", 0.0)),
                        "rate": (
                            float(vals.get("conversions", 0.0))
                            / float(max(1.0, vals.get("opportunities", 0.0)))
                        ),
                    }
                    for side, vals in sorted(objective_opportunity_by_side.items(), key=lambda kv: kv[0])
                },
            },
            "objective_progress_funnel": {
                "global": {
                    "opportunities": int(sum(v.get("opportunities", 0.0) for v in objective_funnel_by_side.values())),
                    "progress_actions": int(sum(v.get("progress_actions", 0.0) for v in objective_funnel_by_side.values())),
                    "conversions": int(sum(v.get("conversions", 0.0) for v in objective_funnel_by_side.values())),
                    "stalls": int(sum(v.get("stalls", 0.0) for v in objective_funnel_by_side.values())),
                    "progress_rate": (
                        float(sum(v.get("progress_actions", 0.0) for v in objective_funnel_by_side.values()))
                        / float(max(1.0, sum(v.get("opportunities", 0.0) for v in objective_funnel_by_side.values())))
                    ),
                    "conversion_rate": (
                        float(sum(v.get("conversions", 0.0) for v in objective_funnel_by_side.values()))
                        / float(max(1.0, sum(v.get("opportunities", 0.0) for v in objective_funnel_by_side.values())))
                    ),
                    "avg_progress_delta": (
                        float(sum(v.get("progress_delta_sum", 0.0) for v in objective_funnel_by_side.values()))
                        / float(max(1.0, sum(v.get("opportunities", 0.0) for v in objective_funnel_by_side.values())))
                    ),
                },
                "by_side": {
                    side: {
                        "opportunities": int(vals.get("opportunities", 0.0)),
                        "progress_actions": int(vals.get("progress_actions", 0.0)),
                        "conversions": int(vals.get("conversions", 0.0)),
                        "stalls": int(vals.get("stalls", 0.0)),
                        "progress_rate": (
                            float(vals.get("progress_actions", 0.0))
                            / float(max(1.0, vals.get("opportunities", 0.0)))
                        ),
                        "conversion_rate": (
                            float(vals.get("conversions", 0.0))
                            / float(max(1.0, vals.get("opportunities", 0.0)))
                        ),
                        "avg_progress_delta": (
                            float(vals.get("progress_delta_sum", 0.0))
                            / float(max(1.0, vals.get("opportunities", 0.0)))
                        ),
                    }
                    for side, vals in sorted(objective_funnel_by_side.items(), key=lambda kv: kv[0])
                },
            },
            "objective_progress_explain": {
                "global": {
                    "no_progress_reason_counts": {
                        key: int(
                            sum(
                                vals.get("no_progress_reason_counts", {}).get(key, 0.0)
                                for vals in objective_explain_by_side.values()
                            )
                        )
                        for key in sorted(
                            {
                                k
                                for vals in objective_explain_by_side.values()
                                for k in vals.get("no_progress_reason_counts", {}).keys()
                            }
                        )
                    },
                    "no_progress_reason_l2_counts": {
                        key: int(
                            sum(
                                vals.get("no_progress_reason_l2_counts", {}).get(key, 0.0)
                                for vals in objective_explain_by_side.values()
                            )
                        )
                        for key in sorted(
                            {
                                k
                                for vals in objective_explain_by_side.values()
                                for k in vals.get("no_progress_reason_l2_counts", {}).keys()
                            }
                        )
                    },
                    "progress_path_counts": {
                        key: int(
                            sum(
                                vals.get("progress_path_counts", {}).get(key, 0.0)
                                for vals in objective_explain_by_side.values()
                            )
                        )
                        for key in sorted(
                            {
                                k
                                for vals in objective_explain_by_side.values()
                                for k in vals.get("progress_path_counts", {}).keys()
                            }
                        )
                    },
                    "conversion_path_counts": {
                        key: int(
                            sum(
                                vals.get("conversion_path_counts", {}).get(key, 0.0)
                                for vals in objective_explain_by_side.values()
                            )
                        )
                        for key in sorted(
                            {
                                k
                                for vals in objective_explain_by_side.values()
                                for k in vals.get("conversion_path_counts", {}).keys()
                            }
                        )
                    },
                    "non_progress_confidence_counts": {
                        key: int(
                            sum(
                                vals.get("non_progress_confidence_counts", {}).get(key, 0.0)
                                for vals in objective_explain_by_side.values()
                            )
                        )
                        for key in sorted(
                            {
                                k
                                for vals in objective_explain_by_side.values()
                                for k in vals.get("non_progress_confidence_counts", {}).keys()
                            }
                        )
                    },
                },
                "by_side": {
                    side: {
                        "no_progress_reason_counts": {
                            key: int(val)
                            for key, val in sorted((vals.get("no_progress_reason_counts", {}) or {}).items(), key=lambda kv: kv[0])
                        },
                        "no_progress_reason_l2_counts": {
                            key: int(val)
                            for key, val in sorted((vals.get("no_progress_reason_l2_counts", {}) or {}).items(), key=lambda kv: kv[0])
                        },
                        "progress_path_counts": {
                            key: int(val)
                            for key, val in sorted((vals.get("progress_path_counts", {}) or {}).items(), key=lambda kv: kv[0])
                        },
                        "conversion_path_counts": {
                            key: int(val)
                            for key, val in sorted((vals.get("conversion_path_counts", {}) or {}).items(), key=lambda kv: kv[0])
                        },
                        "non_progress_confidence_counts": {
                            key: int(val)
                            for key, val in sorted((vals.get("non_progress_confidence_counts", {}) or {}).items(), key=lambda kv: kv[0])
                        },
                    }
                    for side, vals in sorted(objective_explain_by_side.items(), key=lambda kv: kv[0])
                },
            },
            "objective_path_analysis": {
                "conversion_quality_metrics": {
                    "global": {
                        "converted_from_progress_rate": (
                            float(converted_after_progress_global)
                            / float(max(1.0, progress_actions_global))
                        ),
                        "converted_rate_near_vp": (
                            float(near_vp_global["conversions"])
                            / float(max(1.0, near_vp_global["opportunities"]))
                        ),
                        "converted_rate_far_vp": (
                            float(far_vp_global["conversions"])
                            / float(max(1.0, far_vp_global["opportunities"]))
                        ),
                        "conversion_within_2_turns_after_progress": (
                            float(converted_within2_global) / float(max(1.0, progress_events_global))
                        ),
                        "conversion_within_2_turns_given_eventual_conversion": (
                            float(converted_within2_global) / float(max(1.0, converted_any_global))
                        ),
                        "support_counts": {
                            "progress_actions": int(progress_actions_global),
                            "converted_after_progress": int(converted_after_progress_global),
                            "near_vp_opportunities": int(near_vp_global["opportunities"]),
                            "near_vp_conversions": int(near_vp_global["conversions"]),
                            "far_vp_opportunities": int(far_vp_global["opportunities"]),
                            "far_vp_conversions": int(far_vp_global["conversions"]),
                            "progress_events": int(progress_events_global),
                            "progress_events_eventually_converted": int(converted_any_global),
                            "progress_events_converted_within_2_turns": int(converted_within2_global),
                        },
                        "no_progress_causes_l2_top": [
                            {
                                "cause": str(k),
                                "count": int(v),
                                "rate_over_no_progress": (
                                    float(v)
                                    / float(
                                        max(
                                            1.0,
                                            sum(float(x) for x in no_progress_l2_global_counts.values()),
                                        )
                                    )
                                ),
                            }
                            for k, v in sorted(
                                no_progress_l2_global_counts.items(),
                                key=lambda kv: kv[1],
                                reverse=True,
                            )[:8]
                        ],
                    },
                    "by_side": {
                        side: {
                            "converted_from_progress_rate": (
                                float((objective_explain_by_side.get(side, {}).get("conversion_path_counts", {}) or {}).get("converted_after_progress", 0.0))
                                / float(max(1.0, float((objective_funnel_by_side.get(side, {}) or {}).get("progress_actions", 0.0))))
                            ),
                            "converted_rate_near_vp": (
                                float((objective_near_vp_by_side.get(side, {}) or {}).get("near_vp_conversions", 0.0))
                                / float(max(1.0, float((objective_near_vp_by_side.get(side, {}) or {}).get("near_vp_opportunities", 0.0))))
                            ),
                            "converted_rate_far_vp": (
                                float((objective_near_vp_by_side.get(side, {}) or {}).get("far_vp_conversions", 0.0))
                                / float(max(1.0, float((objective_near_vp_by_side.get(side, {}) or {}).get("far_vp_opportunities", 0.0))))
                            ),
                            "conversion_within_2_turns_after_progress": (
                                float((progress_to_conversion_by_side.get(side, {}) or {}).get("converted_within_2_turns", 0.0))
                                / float(max(1.0, float((progress_to_conversion_by_side.get(side, {}) or {}).get("progress_events", 0.0))))
                            ),
                            "conversion_within_2_turns_given_eventual_conversion": (
                                float((progress_to_conversion_by_side.get(side, {}) or {}).get("converted_within_2_turns", 0.0))
                                / float(max(1.0, float((progress_to_conversion_by_side.get(side, {}) or {}).get("converted_any", 0.0))))
                            ),
                            "support_counts": {
                                "progress_actions": int((objective_funnel_by_side.get(side, {}) or {}).get("progress_actions", 0.0)),
                                "converted_after_progress": int((objective_explain_by_side.get(side, {}).get("conversion_path_counts", {}) or {}).get("converted_after_progress", 0.0)),
                                "near_vp_opportunities": int((objective_near_vp_by_side.get(side, {}) or {}).get("near_vp_opportunities", 0.0)),
                                "near_vp_conversions": int((objective_near_vp_by_side.get(side, {}) or {}).get("near_vp_conversions", 0.0)),
                                "far_vp_opportunities": int((objective_near_vp_by_side.get(side, {}) or {}).get("far_vp_opportunities", 0.0)),
                                "far_vp_conversions": int((objective_near_vp_by_side.get(side, {}) or {}).get("far_vp_conversions", 0.0)),
                                "progress_events": int((progress_to_conversion_by_side.get(side, {}) or {}).get("progress_events", 0.0)),
                                "progress_events_eventually_converted": int((progress_to_conversion_by_side.get(side, {}) or {}).get("converted_any", 0.0)),
                                "progress_events_converted_within_2_turns": int((progress_to_conversion_by_side.get(side, {}) or {}).get("converted_within_2_turns", 0.0)),
                            },
                            "no_progress_causes_l2_top": [
                                {
                                    "cause": str(k),
                                    "count": int(v),
                                    "rate_over_no_progress": (
                                        float(v)
                                        / float(
                                            max(
                                                1.0,
                                                sum(
                                                    float(x)
                                                    for x in (
                                                        (objective_explain_by_side.get(side, {}) or {}).get(
                                                            "no_progress_reason_l2_counts", {}
                                                        )
                                                        or {}
                                                    ).values()
                                                ),
                                            )
                                        )
                                    ),
                                }
                                for k, v in sorted(
                                    (
                                        (objective_explain_by_side.get(side, {}) or {}).get(
                                            "no_progress_reason_l2_counts", {}
                                        )
                                        or {}
                                    ).items(),
                                    key=lambda kv: kv[1],
                                    reverse=True,
                                )[:8]
                            ],
                        }
                        for side in sorted(
                            set(objective_funnel_by_side.keys())
                            | set(objective_near_vp_by_side.keys())
                            | set(progress_to_conversion_by_side.keys())
                        )
                    },
                },
                "path_transition_matrix": {
                    "global": transition_rows_global,
                    "by_side": transition_rows_by_side,
                },
                "time_to_convert": {
                    "by_reason": {
                        "global": _ttc_rows(reason_ttc_global),
                        "by_side": {
                            side: _ttc_rows(vals)
                            for side, vals in sorted(reason_ttc_by_side.items(), key=lambda kv: kv[0])
                        },
                    },
                    "by_path": {
                        "global": _ttc_rows(path_ttc_global),
                        "by_side": {
                            side: _ttc_rows(vals)
                            for side, vals in sorted(path_ttc_by_side.items(), key=lambda kv: kv[0])
                        },
                    },
                },
                "harmful_paths_top": harmful_paths_top,
            },
            "tactical_survival_tradeoff": {
                "window_steps": 2,
                "global": {
                    "attacks": int(tactical_tradeoff_totals.get("attacks", 0.0)),
                    "damage_out_avg": (
                        float(tactical_tradeoff_totals.get("damage_out_sum", 0.0))
                        / float(max(1.0, tactical_tradeoff_totals.get("attacks", 0.0)))
                    ),
                    "damage_in_next2_avg": (
                        float(tactical_tradeoff_totals.get("damage_in_next2_sum", 0.0))
                        / float(max(1.0, tactical_tradeoff_totals.get("attacks", 0.0)))
                    ),
                    "net_tradeoff_avg": (
                        float(tactical_tradeoff_totals.get("damage_out_sum", 0.0) - tactical_tradeoff_totals.get("damage_in_next2_sum", 0.0))
                        / float(max(1.0, tactical_tradeoff_totals.get("attacks", 0.0)))
                    ),
                },
                "by_side": {
                    side: {
                        "attacks": int(vals.get("attacks", 0.0)),
                        "damage_out_avg": (
                            float(vals.get("damage_out_sum", 0.0))
                            / float(max(1.0, vals.get("attacks", 0.0)))
                        ),
                        "damage_in_next2_avg": (
                            float(vals.get("damage_in_next2_sum", 0.0))
                            / float(max(1.0, vals.get("attacks", 0.0)))
                        ),
                        "net_tradeoff_avg": (
                            float(vals.get("damage_out_sum", 0.0) - vals.get("damage_in_next2_sum", 0.0))
                            / float(max(1.0, vals.get("attacks", 0.0)))
                        ),
                    }
                    for side, vals in sorted(tactical_tradeoff_by_side.items(), key=lambda kv: kv[0])
                },
            },
            "xai_decision_signals": {
                "representation": {
                    "latent_l2_norm_avg": (
                        float(xai_latent_l2_norm_sum) / float(max(1, xai_latent_l2_norm_count))
                    ),
                    "top_latent_dims": [
                        {
                            "dim": int(dim_idx),
                            "count": int(cnt),
                            "rate": (float(cnt) / float(max(1, transition_count))),
                        }
                        for dim_idx, cnt in sorted(
                            xai_latent_top_dim_counts.items(),
                            key=lambda kv: kv[1],
                            reverse=True,
                        )[:10]
                    ],
                },
                "prediction": {
                    "policy_top1_confidence_avg": (
                        float(xai_policy_top1_prob_sum) / float(max(1, xai_policy_top1_prob_count))
                    ),
                    "predicted_value_root_avg": (
                        float(xai_predicted_value_root_sum) / float(max(1, xai_predicted_value_root_count))
                    ),
                    "top_policy_actions": [
                        {
                            "action_id": str(action_id),
                            "count": int(cnt),
                            "rate": (float(cnt) / float(max(1, transition_count))),
                        }
                        for action_id, cnt in sorted(
                            xai_policy_top1_counts.items(),
                            key=lambda kv: kv[1],
                            reverse=True,
                        )[:10]
                    ],
                },
                "dynamics": {
                    "pred_reward_avg": (
                        float(xai_dynamics_pred_reward_sum) / float(max(1, xai_dynamics_pred_reward_count))
                    ),
                    "next_latent_l2_avg": (
                        float(xai_dynamics_next_latent_l2_sum) / float(max(1, xai_dynamics_next_latent_l2_count))
                    ),
                    "delta_l2_avg": (
                        float(xai_dynamics_delta_l2_sum) / float(max(1, xai_dynamics_delta_l2_count))
                    ),
                },
                "policy_top1_confidence_avg": (
                    float(xai_policy_top1_prob_sum) / float(max(1, xai_policy_top1_prob_count))
                ),
                "latent_l2_norm_avg": (
                    float(xai_latent_l2_norm_sum) / float(max(1, xai_latent_l2_norm_count))
                ),
                "predicted_value_root_avg": (
                    float(xai_predicted_value_root_sum) / float(max(1, xai_predicted_value_root_count))
                ),
                "dynamics_pred_reward_avg": (
                    float(xai_dynamics_pred_reward_sum) / float(max(1, xai_dynamics_pred_reward_count))
                ),
                "dynamics_next_latent_l2_avg": (
                    float(xai_dynamics_next_latent_l2_sum) / float(max(1, xai_dynamics_next_latent_l2_count))
                ),
                "dynamics_delta_l2_avg": (
                    float(xai_dynamics_delta_l2_sum) / float(max(1, xai_dynamics_delta_l2_count))
                ),
                "top_policy_actions": [
                    {
                        "action_id": str(action_id),
                        "count": int(cnt),
                        "rate": (float(cnt) / float(max(1, transition_count))),
                    }
                    for action_id, cnt in sorted(
                        xai_policy_top1_counts.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:10]
                ],
                "top_latent_dims": [
                    {
                        "dim": int(dim_idx),
                        "count": int(cnt),
                        "rate": (float(cnt) / float(max(1, transition_count))),
                    }
                    for dim_idx, cnt in sorted(
                        xai_latent_top_dim_counts.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:10]
                ],
            },
            "train_stability": {
                "final_grad_norm": float(latest_metrics.get("grad_norm", 0.0)),
                "replay_age_mean": float(latest_metrics.get("replay_age_mean", 0.0)),
                "replay_age_max": float(latest_metrics.get("replay_age_max", 0.0)),
            },
        },
    }
    units_path = run_dir / "metrics" / "units_sides.json"
    units_path.parent.mkdir(parents=True, exist_ok=True)
    units_path.write_text(json.dumps(units_sides, indent=2), encoding="utf-8")

    reaction_den = max(1, reaction_fire_count + reaction_fire_skipped_count)
    melee_den = max(1, melee_attempts)
    latest_metrics["phase_2_9_train_kpis"] = {
        "reaction_window_count": int(reaction_window_count),
        "reaction_fire_count": int(reaction_fire_count),
        "reaction_fire_skipped_count": int(reaction_fire_skipped_count),
        "reaction_fire_activation_rate": (
            float(reaction_fire_count) / float(reaction_den)
        ),
        "reaction_fire_kill_conversion_rate": (
            float(reaction_fire_kill_conversions) / float(max(1, reaction_fire_count))
        ),
        "reaction_fire_damage_induced_proxy": (
            float(reaction_fire_damage_sum) / float(max(1, reaction_fire_count))
        ),
        "reaction_fire_damage_prevented_proxy": (
            float(reaction_fire_kill_conversions) / float(max(1, reaction_fire_count))
        ),
        "converted_from_progress_rate": (
            float(converted_after_progress_global) / float(max(1.0, progress_actions_global))
        ),
        "converted_rate_near_vp": (
            float(near_vp_global["conversions"])
            / float(max(1.0, near_vp_global["opportunities"]))
        ),
        "conversion_within_2_turns_after_progress": (
            float(converted_within2_global) / float(max(1.0, progress_events_global))
        ),
        "assault_melee_action_family_count": int(melee_attempts),
        "assault_quality": {
            "melee_attempts": int(melee_attempts),
            "melee_success_rate": (
                float(melee_success_count) / float(melee_den)
            ),
            "melee_kills_per_attempt": (
                float(melee_kills_sum) / float(melee_den)
            ),
            "melee_damage_per_attempt": (
                float(melee_damage_sum) / float(melee_den)
            ),
        },
        "assault_context_tags": {
            "favorable": int(assault_context_counts.get("favorable", 0)),
            "unfavorable": int(assault_context_counts.get("unfavorable", 0)),
            "favorable_rate": (
                float(assault_context_counts.get("favorable", 0))
                / float(melee_den)
            ),
        },
    }
    latest_metrics["objective_contract"] = {
        "tracked_side": str(objective_tracked_side),
        "metric": "objectives_captured",
        "source": "scenario_json.victory_outcomes.tracked_side",
    }

    xai_decisions_path = run_dir / "xai" / "xai_decisions.jsonl"
    xai_decisions_path.parent.mkdir(parents=True, exist_ok=True)
    with xai_decisions_path.open("w", encoding="utf-8") as fh:
        for row in xai_decision_rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")

    metrics_path = run_dir / "metrics" / "summary.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(latest_metrics, indent=2), encoding="utf-8")

    # Persist channel previews for first/mid/last snapshots (UI inspection).
    if replay._items:
        first_obs = replay._items[0].observation
        if isinstance(first_obs, torch.Tensor) and first_obs.ndim == 3:
            c, h, w = first_obs.shape

            def _snapshot_payload(label: str, obs_tensor: torch.Tensor, index: int) -> dict:
                channels = []
                for idx in range(int(c)):
                    plane = obs_tensor[idx]
                    nonzero = int((plane != 0).sum().item())
                    channels.append(
                        {
                            "index": idx,
                            "name": _channel_name(idx),
                            "nonzero_cells": nonzero,
                            "nonzero_ratio": float(nonzero / float(max(1, h * w))),
                            "mean_value": float(plane.mean().item()),
                            "max_value": float(plane.max().item()),
                            "min_value": float(plane.min().item()),
                            "values": plane.tolist(),
                        }
                    )
                return {
                    "label": label,
                    "sample_index": int(index),
                    "channels": channels,
                }

            n = len(replay._items)
            pick = [
                ("first", 0),
                ("mid", max(0, n // 2)),
                ("last", max(0, n - 1)),
            ]
            snapshots = []
            for label, idx in pick:
                obs_tensor = replay._items[idx].observation
                if isinstance(obs_tensor, torch.Tensor) and obs_tensor.ndim == 3:
                    snapshots.append(_snapshot_payload(label, obs_tensor, idx))

            (run_dir / "metrics" / "observation_channels.json").write_text(
                json.dumps(
                    {
                        "encoder_type": str(getattr(model, "encoder_type", "mlp")),
                        "shape": {
                            "channels": int(c),
                            "height": int(h),
                            "width": int(w),
                        },
                        "snapshots": snapshots,
                        # Backward-compat alias to first snapshot channel stats.
                        "channels": snapshots[0]["channels"] if snapshots else [],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    xai_dir = run_dir / "xai"
    xai_dir.mkdir(parents=True, exist_ok=True)
    (xai_dir / "decision_report.json").write_text(
        json.dumps(build_decision_report(0, ["episode_rollout"], [1.0]), indent=2),
        encoding="utf-8",
    )
    (xai_dir / "search_snapshot.json").write_text(
        json.dumps(build_search_snapshot(["episode_rollout"], [1], [1.0]), indent=2),
        encoding="utf-8",
    )
    (xai_dir / "episode_narrative.json").write_text(
        json.dumps(build_episode_narrative(episode_rewards, episode_actions), indent=2),
        encoding="utf-8",
    )
    if mlflow_mod is not None:
        try:
            _mlflow_log_metrics(
                mlflow_mod,
                {
                    "phase29_reaction_activation_rate": float(
                        latest_metrics.get("phase_2_9_train_kpis", {})
                        .get("reaction_fire_activation_rate", 0.0)
                    ),
                    "phase29_melee_attempts": float(
                        latest_metrics.get("phase_2_9_train_kpis", {})
                        .get("assault_quality", {})
                        .get("melee_attempts", 0.0)
                    ),
                    "phase29_converted_from_progress_rate": float(
                        latest_metrics.get("phase_2_9_train_kpis", {})
                        .get("converted_from_progress_rate", 0.0)
                    ),
                    "phase29_converted_rate_near_vp": float(
                        latest_metrics.get("phase_2_9_train_kpis", {})
                        .get("converted_rate_near_vp", 0.0)
                    ),
                    "phase29_conversion_within_2_turns_after_progress": float(
                        latest_metrics.get("phase_2_9_train_kpis", {})
                        .get("conversion_within_2_turns_after_progress", 0.0)
                    ),
                },
                step=int(iterations),
            )
            mlflow_mod.log_artifact(str(metrics_path))
            mlflow_mod.log_artifact(str(run_dir / "run_manifest.json"))
            mlflow_mod.log_artifact(str(run_dir / "metrics" / "units_sides.json"))
            mlflow_mod.log_artifact(str(run_dir / "xai" / "decision_report.json"))
            mlflow_mod.end_run()
        except Exception:
            pass
    print(f"[MuZero] completed run_dir={run_dir}")
    return {"run_id": run_id, "metrics": latest_metrics}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MuZero training on VOEC.")
    parser.add_argument(
        "--config",
        default="agents/muzero/configs/muzero_config.yaml",
        help="Path to MuZero YAML config file.",
    )
    parser.add_argument(
        "--mlflow-experiment",
        default="assault_muzero",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--mlflow-run-name",
        default="",
        help="Optional MLflow run name. Defaults to MuZero run_id.",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    print(
        run_training(
            config_path=args.config,
            mlflow_experiment=args.mlflow_experiment,
            mlflow_run_name=args.mlflow_run_name,
        )
    )
