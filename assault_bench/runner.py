from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from assault_bench.configs.config_loader import load_benchmark_config
from agents.muzero.adapter_voec import MuZeroVOECAdapter
from agents.muzero.configs.config_loader import load_muzero_config
from agents.muzero.core.mcts import run_mcts_puct
from agents.muzero.core.network import MuZeroNetwork
from agents.muzero.core.selfplay import (
    observation_to_tensor,
    observation_to_vector,
    priors_and_values_from_model,
    value_signs_from_to_play,
)
from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator


@dataclass
class BenchmarkResult:
    agent_name: str
    episodes: int
    avg_return: float
    avg_steps: float
    terminal_rate: float
    timeout_rate: float
    win_rate: float
    terminal_reasons: Dict[str, float]
    vp_final_avg_by_side: Dict[str, float]
    vp_final_distribution_by_side: Dict[str, Dict[str, float]]
    winner_side_counts: Dict[str, int]
    winner_side_rates: Dict[str, float]
    tracked_side: str
    tracked_metric: str
    tracked_captured_avg: float
    tracked_captured_distribution: Dict[str, float]
    scenario_outcome_counts: Dict[str, int]
    scenario_outcome_rates: Dict[str, float]
    phase_2_9_eval_kpis: Dict[str, float]


def _action_kind_from_id(action_id: str) -> str:
    raw = str(action_id or "").strip()
    if not raw:
        return ""
    return raw.split(":", 1)[0].strip().upper()


def _side_hp_snapshot(units) -> Dict[str, float]:
    hp: Dict[str, float] = {}
    for u in list(units or []):
        side = str(getattr(u, "side", "") or "").strip()
        if not side:
            continue
        hp[side] = hp.get(side, 0.0) + float(max(0.0, float(getattr(u, "hp", 0) or 0.0)))
    return hp


def _side_alive_snapshot(units) -> Dict[str, int]:
    alive: Dict[str, int] = {}
    for u in list(units or []):
        side = str(getattr(u, "side", "") or "").strip()
        if not side:
            continue
        if bool(getattr(u, "alive", False)):
            alive[side] = alive.get(side, 0) + 1
    return alive


def _assault_advantage_bucket(chosen_prob: float, margin: float, legal_count: int) -> str:
    score = 0
    if float(chosen_prob) >= 0.55:
        score += 1
    if float(margin) >= 0.20:
        score += 1
    if int(legal_count) >= 6:
        score += 1
    return "favorable" if score >= 2 else "unfavorable"


def _benchmark_seed_task(payload: dict):
    from voec_sim.assets_bridge.importers import AssetPaths
    import torch

    assets = AssetPaths(
        root=Path(payload["assets"]["root"]),
        unit_catalog=Path(payload["assets"]["unit_catalog"]),
        map_piece_catalog=Path(payload["assets"]["map_piece_catalog"]),
        scenarios_dir=Path(payload["assets"]["scenarios_dir"]),
    )
    sim = VOECSimulator(assets=assets)
    adapter = MuZeroVOECAdapter(sim)
    model = None
    if payload.get("checkpoint_path"):
        model = MuZeroNetwork(
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
        state_dict = torch.load(payload["checkpoint_path"], map_location="cpu")
        model.load_state_dict(state_dict)
        model.eval()
    return _run_episode_with_policy(
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
        model=model,
        action_dim=int(payload.get("action_dim", 32)),
        mcts_unroll_steps=int(payload.get("mcts_unroll_steps", 1)),
        mcts_discount=float(payload.get("mcts_discount", 0.997)),
    )


def _run_episode_with_policy(
    adapter: MuZeroVOECAdapter,
    scenario_id: str,
    seed: int,
    policy_name: str,
    policy_by_side: Dict[str, str],
    max_steps: int,
    max_steps_override: int,
    mcts_simulations: int,
    mcts_c_puct: float,
    mcts_temperature: float,
    model=None,
    action_dim: int = 32,
    mcts_unroll_steps: int = 1,
    mcts_discount: float = 0.997,
):
    def _scenario_outcome_from_final_vp(final_vp_by_side: Dict[str, int]) -> Dict[str, object]:
        runtime = getattr(adapter.sim, "_runtime", None)
        scenario = getattr(runtime, "scenario", None) if runtime is not None else None
        vo = dict(getattr(scenario, "victory_outcomes", {}) or {})
        tracked_side = str(vo.get("tracked_side", "")).strip()
        metric = str(vo.get("metric", "")).strip()
        table = list(vo.get("table", []) or [])
        captured = int(final_vp_by_side.get(tracked_side, 0)) if tracked_side else 0
        matched = None
        for row in table:
            cap = dict(row.get("captured", {}) or {})
            lo = int(cap.get("min", -10**9))
            hi = int(cap.get("max", 10**9))
            if lo <= captured <= hi:
                matched = row
                break
        if matched is None and table:
            matched = dict(table[-1])
        return {
            "tracked_side": tracked_side,
            "metric": metric,
            "captured": int(captured),
            "result": str((matched or {}).get("result", "")).strip(),
            "next_scenario": str((matched or {}).get("next_scenario", "")).strip(),
            "next_page": int((matched or {}).get("next_page", 0) or 0),
        }

    def _final_vp_control_counts() -> Dict[str, int]:
        state = getattr(adapter.sim, "_state", None)
        if state is None:
            return {}
        counts: Dict[str, int] = {}
        side_to_ownership = dict(getattr(state, "side_to_ownership", {}) or {})
        for side in side_to_ownership.keys():
            counts[str(side)] = 0
        victory = getattr(state, "victory", None)
        if victory is None:
            return counts
        for vp in getattr(victory, "points", []) or []:
            hs = state.hex_states.get(vp.hex_coords) if getattr(state, "hex_states", None) else None
            if hs is None:
                continue
            owner = getattr(hs, "ownership", None)
            for side, side_owner in side_to_ownership.items():
                if owner == side_owner:
                    side_s = str(side)
                    counts[side_s] = counts.get(side_s, 0) + 1
                    break
        return counts

    obs = adapter.initial_state(scenario_id=scenario_id, seed=seed)
    eval_side = str(obs.to_play) if obs.to_play is not None else ""
    scenario_turn_limit = None
    if hasattr(adapter.sim, "scenario_max_turns"):
        try:
            scenario_turn_limit = adapter.sim.scenario_max_turns()
        except Exception:
            scenario_turn_limit = None
    effective_max_steps = int(max_steps)
    unit_count = len(getattr(obs, "units", []) or [])
    if int(max_steps_override) > 0:
        effective_max_steps = int(max_steps_override)
    elif scenario_turn_limit is not None and int(scenario_turn_limit) > 0 and unit_count > 0:
        effective_max_steps = int(scenario_turn_limit) * int(unit_count)
    total_reward = 0.0
    steps = 0
    terminal = False
    timeout = False
    win = False
    terminal_reason = ""
    winner_side = ""
    timeout_reason = "turn_unit_budget"
    phase29 = {
        "reaction_window_count": 0,
        "reaction_fire_count": 0,
        "reaction_fire_skipped_count": 0,
        "reaction_fire_kill_conversions": 0,
        "reaction_fire_damage_sum": 0.0,
        "melee_attempts": 0,
        "melee_success_count": 0,
        "melee_kills_sum": 0.0,
        "melee_damage_sum": 0.0,
        "assault_favorable_count": 0,
        "assault_unfavorable_count": 0,
    }
    for _ in range(effective_max_steps):
        if adapter.sim.reached_turn_limit() and not adapter.terminal():
            timeout_reason = "scenario_turn_limit"
            break
        legal = adapter.legal_actions()
        if not legal:
            break
        active_side = str(obs.to_play) if obs.to_play is not None else ""
        side_hp_before = _side_hp_snapshot(getattr(obs, "units", []))
        side_alive_before = _side_alive_snapshot(getattr(obs, "units", []))
        reaction_opts = [a for a in legal if _action_kind_from_id(a).startswith("OPPORTUNITY_")]
        if reaction_opts:
            phase29["reaction_window_count"] += 1
        active_policy = str(policy_by_side.get(active_side, policy_name)).strip().lower() or str(policy_name)
        chosen_prob = 0.0
        margin = 0.0
        if active_policy == "random":
            action = random.choice(legal)
        else:
            priors = None
            values = None
            signs = value_signs_from_to_play(obs, legal)
            if model is not None:
                if str(getattr(model, "encoder_type", "mlp")) == "cnn":
                    obs_vector = observation_to_tensor(
                        obs,
                        channels=int(getattr(model, "observation_channels", 8)),
                        height=int(getattr(model, "observation_height", 16)),
                        width=int(getattr(model, "observation_width", 16)),
                    )
                else:
                    obs_vector = observation_to_vector(obs)
                priors, values = priors_and_values_from_model(
                    model=model,
                    observation=obs_vector,
                    legal_actions=legal,
                    action_dim=action_dim,
                    unroll_steps=mcts_unroll_steps,
                    discount=mcts_discount,
                )
            mcts_out = run_mcts_puct(
                legal_actions=legal,
                num_simulations=mcts_simulations,
                c_puct=mcts_c_puct,
                temperature=mcts_temperature,
                # Benchmark/eval must stay reproducible: no Dirichlet exploration noise.
                dirichlet_epsilon=0.0,
                priors_by_action=priors,
                values_by_action=values,
                value_sign_by_action=signs,
            )
            action = mcts_out.chosen_action
            probs = [float(x) for x in (mcts_out.probs or [])]
            if probs:
                chosen_prob = float(max(probs))
                top2 = sorted(probs, reverse=True)[:2]
                margin = float(top2[0] - top2[1]) if len(top2) > 1 else float(top2[0])
        action_kind = _action_kind_from_id(action)
        transition = adapter.apply(action)
        post_units = getattr(transition.state, "units", []) or []
        side_hp_after = _side_hp_snapshot(post_units)
        side_alive_after = _side_alive_snapshot(post_units)
        enemy_damage = 0.0
        enemy_kills = 0
        for side_k, hp_before in side_hp_before.items():
            if str(side_k) == str(active_side):
                continue
            enemy_damage += max(0.0, float(hp_before - float(side_hp_after.get(side_k, hp_before))))
            enemy_kills += max(0, int(side_alive_before.get(side_k, 0) - side_alive_after.get(side_k, 0)))
        if action_kind == "OPPORTUNITY_FIRE":
            phase29["reaction_fire_count"] += 1
            phase29["reaction_fire_damage_sum"] += float(enemy_damage)
            if int(enemy_kills) > 0:
                phase29["reaction_fire_kill_conversions"] += 1
        elif action_kind == "OPPORTUNITY_SKIP":
            phase29["reaction_fire_skipped_count"] += 1
        if "ASSAULT" in action_kind or action_kind in {"MELEE", "ASSAULT_MELEE"}:
            phase29["melee_attempts"] += 1
            phase29["melee_damage_sum"] += float(enemy_damage)
            phase29["melee_kills_sum"] += float(enemy_kills)
            if float(enemy_damage) > 0.0 or int(enemy_kills) > 0:
                phase29["melee_success_count"] += 1
            bucket = _assault_advantage_bucket(
                chosen_prob=float(chosen_prob),
                margin=float(margin),
                legal_count=len(legal),
            )
            phase29[f"assault_{bucket}_count"] += 1
        if transition.done:
            terminal_reason = str(transition.state.end_reason or "natural_terminal")
            winner = transition.state.winner
            winner_side = str(winner) if winner is not None else ""
            if winner is None:
                total_reward += 0.0
                win = False
            else:
                won = str(winner) == eval_side
                total_reward += 1.0 if won else -1.0
                win = won
        steps += 1
        obs = adapter.observation()
        if transition.done:
            terminal = True
            break
    if not terminal:
        timeout_transition = adapter.sim.resolve_timeout(
            action_id="TIMEOUT",
            end_reason=timeout_reason,
        )
        winner = timeout_transition.state.winner
        winner_side = str(winner) if winner is not None else ""
        if winner is None:
            total_reward += 0.0
            win = False
        else:
            won = str(winner) == eval_side
            total_reward += 1.0 if won else -1.0
            win = won
        terminal = True
        timeout = True
        terminal_reason = str(timeout_transition.state.end_reason or timeout_reason)
    final_vp_by_side = _final_vp_control_counts()
    scenario_outcome = _scenario_outcome_from_final_vp(final_vp_by_side)
    reaction_den = max(1, int(phase29["reaction_fire_count"] + phase29["reaction_fire_skipped_count"]))
    melee_den = max(1, int(phase29["melee_attempts"]))
    phase29_summary = {
        "reaction_window_count": int(phase29["reaction_window_count"]),
        "reaction_fire_count": int(phase29["reaction_fire_count"]),
        "reaction_fire_skipped_count": int(phase29["reaction_fire_skipped_count"]),
        "reaction_fire_activation_rate": (
            float(phase29["reaction_fire_count"]) / float(reaction_den)
        ),
        "reaction_fire_kill_conversion_rate": (
            float(phase29["reaction_fire_kill_conversions"])
            / float(max(1, int(phase29["reaction_fire_count"])))
        ),
        "reaction_fire_damage_induced_proxy": (
            float(phase29["reaction_fire_damage_sum"])
            / float(max(1, int(phase29["reaction_fire_count"])))
        ),
        "reaction_fire_damage_prevented_proxy": (
            float(phase29["reaction_fire_kill_conversions"])
            / float(max(1, int(phase29["reaction_fire_count"])))
        ),
        "assault_melee_action_family_count": int(phase29["melee_attempts"]),
        "melee_attempts": int(phase29["melee_attempts"]),
        "melee_success_rate": (
            float(phase29["melee_success_count"]) / float(melee_den)
        ),
        "melee_kills_per_attempt": (
            float(phase29["melee_kills_sum"]) / float(melee_den)
        ),
        "melee_damage_per_attempt": (
            float(phase29["melee_damage_sum"]) / float(melee_den)
        ),
        "assault_favorable_count": int(phase29["assault_favorable_count"]),
        "assault_unfavorable_count": int(phase29["assault_unfavorable_count"]),
    }
    return (
        total_reward,
        steps,
        terminal,
        timeout,
        win,
        terminal_reason,
        final_vp_by_side,
        winner_side,
        scenario_outcome,
        phase29_summary,
    )


def _load_train_phase29_from_checkpoint(checkpoint_path: str) -> Dict[str, float]:
    if not checkpoint_path:
        return {}
    ckpt = Path(checkpoint_path)
    if not ckpt.is_absolute():
        ckpt = (Path.cwd() / ckpt).resolve()
    run_dir = ckpt.parent.parent
    summary_path = run_dir / "metrics" / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    section = payload.get("phase_2_9_train_kpis", {}) or {}
    return dict(section)


def _phase29_value(payload: Dict[str, object], key: str) -> float:
    if key in payload:
        return float(payload.get(key, 0.0) or 0.0)
    assault_quality = dict(payload.get("assault_quality", {}) or {})
    if key in assault_quality:
        return float(assault_quality.get(key, 0.0) or 0.0)
    return 0.0


def _build_phase29_train_eval(train_kpis: Dict[str, float], eval_kpis: Dict[str, float]) -> Dict[str, Dict]:
    keys = [
        "reaction_window_count",
        "reaction_fire_count",
        "reaction_fire_skipped_count",
        "reaction_fire_activation_rate",
        "reaction_fire_kill_conversion_rate",
        "reaction_fire_damage_induced_proxy",
        "reaction_fire_damage_prevented_proxy",
        "assault_melee_action_family_count",
        "melee_attempts",
        "melee_success_rate",
        "melee_kills_per_attempt",
        "melee_damage_per_attempt",
    ]
    return {
        "train": {k: _phase29_value(train_kpis, k) for k in keys},
        "eval": {k: float(eval_kpis.get(k, 0.0)) for k in keys},
        "delta_eval_minus_train": {
            k: float(eval_kpis.get(k, 0.0)) - _phase29_value(train_kpis, k)
            for k in keys
        },
    }


def _build_phase29_promotion_gate(
    *,
    train_kpis: Dict[str, float],
    eval_kpis: Dict[str, float],
    muzero_row: Dict,
    baseline_row: Dict,
) -> Dict[str, object]:
    eval_reaction_windows = float(eval_kpis.get("reaction_window_count", 0.0))
    eval_reaction_events = float(eval_kpis.get("reaction_fire_count", 0.0)) + float(
        eval_kpis.get("reaction_fire_skipped_count", 0.0)
    )
    reaction_contract_pass = (
        (eval_reaction_events <= eval_reaction_windows)
        if eval_reaction_windows > 0.0
        else (eval_reaction_events == 0.0)
    )
    assault_usage_non_zero = float(eval_kpis.get("melee_attempts", 0.0)) > 0.0
    tracked_side = str(muzero_row.get("tracked_side", "") or "").strip()
    winner_counts = dict(muzero_row.get("winner_side_counts", {}) or {})
    dominant_winner_side = ""
    if winner_counts:
        dominant_winner_side = str(max(winner_counts.items(), key=lambda kv: int(kv[1]))[0])
    muzero_captured = float(muzero_row.get("tracked_captured_avg", 0.0))
    baseline_captured = float(baseline_row.get("tracked_captured_avg", 0.0))
    # VP-first: interpret tracked-side capture direction based on who is winning.
    # If tracked side is dominant winner, higher captured is better.
    # Otherwise tracked side is typically opponent perspective, so lower is better.
    if tracked_side and dominant_winner_side and tracked_side == dominant_winner_side:
        capture_conversion_no_regression = muzero_captured >= baseline_captured
    else:
        capture_conversion_no_regression = muzero_captured <= baseline_captured
    eval_loss_rate = 1.0 - float(muzero_row.get("win_rate", 0.0))
    baseline_loss_rate = 1.0 - float(baseline_row.get("win_rate", 0.0))
    loss_rate_no_regression = eval_loss_rate <= baseline_loss_rate + 1e-9
    melee_attempt_rate = float(eval_kpis.get("melee_attempts", 0.0)) / float(
        max(1.0, float(eval_reaction_windows) + float(eval_kpis.get("melee_attempts", 0.0)))
    )
    melee_success_rate = float(eval_kpis.get("melee_success_rate", 0.0))
    assault_misuse_block = bool(melee_attempt_rate > 0.15 and melee_success_rate < 0.20)
    reaction_failfast_block = bool(
        float(eval_kpis.get("reaction_fire_activation_rate", 0.0))
        > _phase29_value(train_kpis, "reaction_fire_activation_rate")
        and float(muzero_row.get("win_rate", 0.0)) < float(baseline_row.get("win_rate", 0.0))
    )
    checks = {
        "reaction_contract_pass": bool(reaction_contract_pass),
        "capture_conversion_after_contact_no_regression": bool(capture_conversion_no_regression),
        "loss_rate_no_regression": bool(loss_rate_no_regression),
        "reaction_failfast_block": bool(not reaction_failfast_block),
    }
    return {
        "status": "PASS" if all(bool(v) for v in checks.values()) else "FAIL",
        "checks": checks,
        "advisory": {
            "assault_usage_non_zero": bool(assault_usage_non_zero),
            "assault_misuse_block": bool(not assault_misuse_block),
        },
        "promotion_mode": "vp_first",
        "tracked_capture_direction": (
            "higher_is_better"
            if (tracked_side and dominant_winner_side and tracked_side == dominant_winner_side)
            else "lower_is_better"
        ),
        "tracked_side": tracked_side,
        "dominant_winner_side": dominant_winner_side,
        "muzero_tracked_captured_avg": float(muzero_captured),
        "baseline_tracked_captured_avg": float(baseline_captured),
        "eval_loss_rate": float(eval_loss_rate),
        "baseline_loss_rate": float(baseline_loss_rate),
        "melee_attempt_rate_proxy": float(melee_attempt_rate),
    }


def _iter_index_from_checkpoint_name(name: str) -> int:
    m = re.search(r"iter_(\d+)\.pt$", str(name))
    return int(m.group(1)) if m else -1


def _resolve_checkpoint_path(checkpoint_path: str, run_root: Path) -> str:
    raw = str(checkpoint_path or "").strip()
    if raw and raw.lower() != "latest":
        return raw
    ckpts = list(run_root.glob("muzero_*/checkpoints/iter_*.pt"))
    if not ckpts:
        return ""
    best = sorted(
        ckpts,
        key=lambda p: (p.stat().st_mtime, _iter_index_from_checkpoint_name(p.name)),
        reverse=True,
    )[0]
    return str(best)


def run_benchmark(
    config_path: str = "assault_bench/configs/benchmark_config.yaml",
    checkpoint_path: str = "",
    muzero_config_path: str = "",
) -> Dict:
    cfg = load_benchmark_config(Path(config_path))
    voec_cfg = load_voec_config(Path(cfg.paths["voec_config"]))
    scenario_id = str(cfg.benchmark["scenario_id"])
    seeds = list(cfg.benchmark["seeds"])
    max_steps = int(cfg.benchmark["max_steps"])
    max_steps_override = int(cfg.benchmark.get("max_steps_override", 0))
    mcts_simulations = int(cfg.benchmark["mcts_simulations"])
    mcts_c_puct = float(cfg.benchmark["mcts_c_puct"])
    mcts_temperature = float(cfg.benchmark.get("mcts_temperature", 1.0))
    num_workers = int(cfg.benchmark.get("num_workers", 1))
    run_root = Path(str(cfg.paths["run_root"]))
    checkpoint_path = _resolve_checkpoint_path(checkpoint_path=checkpoint_path, run_root=run_root)
    cfg_muzero_path = (
        muzero_config_path
        if muzero_config_path
        else str(cfg.paths.get("muzero_config", "agents/muzero/configs/muzero_config.yaml"))
    )

    model = None
    action_dim = 32
    mcts_unroll_steps = 1
    mcts_discount = 0.997
    if checkpoint_path:
        muz_cfg = load_muzero_config(Path(cfg_muzero_path))
        action_dim = int(muz_cfg.model["action_dim"])
        mcts_unroll_steps = int(muz_cfg.selfplay.get("mcts_unroll_steps", 1))
        mcts_discount = float(muz_cfg.selfplay.get("mcts_discount", 0.997))
        model = MuZeroNetwork(
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
        import torch

        state_dict = torch.load(ckpt, map_location="cpu")
        model.load_state_dict(state_dict)
        model.eval()
        print(f"[Bench] loaded_checkpoint={ckpt}")
    else:
        print("[Bench] running without checkpoint (stub mode)")

    sim = VOECSimulator(assets=voec_cfg.assets)
    adapter = MuZeroVOECAdapter(sim)
    print(
        "[Bench] "
        f"scenario={scenario_id} seeds={len(seeds)} "
        f"workers={num_workers} max_steps={max_steps}"
    )

    results: List[BenchmarkResult] = []
    base_obs = adapter.initial_state(scenario_id=scenario_id, seed=int(seeds[0] if seeds else 0))
    sides = sorted(
        {
            str(u.get("side", "")).strip()
            for u in (getattr(base_obs, "units", []) or [])
            if str(u.get("side", "")).strip()
        }
    )
    if len(sides) < 2:
        active_side = str(getattr(base_obs, "to_play", "") or "").strip()
        if active_side:
            sides = [active_side]
    matchup_specs: list[tuple[str, str, Dict[str, str]]] = [
        ("muzero_stub", "mcts", {}),
        ("baseline_random", "random", {}),
    ]
    if len(sides) >= 2:
        side_a, side_b = sides[0], sides[1]
        matchup_specs.extend(
            [
                (
                    f"muzero_vs_random_{side_a}",
                    "mcts",
                    {side_a: "mcts", side_b: "random"},
                ),
                (
                    f"muzero_vs_random_{side_b}",
                    "mcts",
                    {side_a: "random", side_b: "mcts"},
                ),
            ]
        )
    for agent_name, policy, policy_by_side in matchup_specs:
        print(
            f"[Bench] agent={agent_name} policy={policy} "
            f"policy_by_side={policy_by_side if policy_by_side else '{}'} start"
        )
        returns = []
        steps = []
        terminals = []
        timeouts = []
        wins = []
        terminal_reason_counts: Dict[str, int] = {}
        vp_final_counts_by_side: Dict[str, Dict[int, int]] = {}
        winner_side_counts: Dict[str, int] = {}
        tracked_side = ""
        tracked_metric = ""
        tracked_captured_values: List[int] = []
        scenario_outcome_counts: Dict[str, int] = {}
        phase29_seed_rows: List[Dict[str, float]] = []
        if num_workers > 1:
            payloads = [
                {
                    "assets": {
                        "root": str(voec_cfg.assets.root),
                        "unit_catalog": str(voec_cfg.assets.unit_catalog),
                        "map_piece_catalog": str(voec_cfg.assets.map_piece_catalog),
                        "scenarios_dir": str(voec_cfg.assets.scenarios_dir),
                    },
                    "scenario_id": scenario_id,
                    "seed": s,
                    "policy_name": policy,
                    "policy_by_side": dict(policy_by_side),
                    "max_steps": max_steps,
                    "max_steps_override": max_steps_override,
                    "mcts_simulations": mcts_simulations,
                    "mcts_c_puct": mcts_c_puct,
                    "mcts_temperature": mcts_temperature,
                    "checkpoint_path": str(ckpt) if checkpoint_path else "",
                    "action_dim": action_dim,
                    "mcts_unroll_steps": mcts_unroll_steps,
                    "mcts_discount": mcts_discount,
                    "model": {
                        "observation_dim": int(muz_cfg.model["observation_dim"])
                        if checkpoint_path
                        else 4,
                        "hidden_dim": int(muz_cfg.model["hidden_dim"])
                        if checkpoint_path
                        else 64,
                        "action_dim": action_dim,
                        "encoder_type": str(muz_cfg.model.get("encoder_type", "mlp"))
                        if checkpoint_path
                        else "mlp",
                        "observation_channels": int(muz_cfg.model.get("observation_channels", 8))
                        if checkpoint_path
                        else 8,
                        "observation_height": int(muz_cfg.model.get("observation_height", 16))
                        if checkpoint_path
                        else 16,
                        "observation_width": int(muz_cfg.model.get("observation_width", 16))
                        if checkpoint_path
                        else 16,
                        "dynamics_blocks": int(muz_cfg.model.get("dynamics_blocks", 1))
                        if checkpoint_path
                        else 1,
                        "prediction_blocks": int(muz_cfg.model.get("prediction_blocks", 1))
                        if checkpoint_path
                        else 1,
                    },
                }
                for s in seeds
            ]
            with ProcessPoolExecutor(max_workers=num_workers) as ex:
                futures = [ex.submit(_benchmark_seed_task, p) for p in payloads]
                for fut in as_completed(futures):
                    (
                        ret,
                        step_count,
                        terminal,
                        timeout,
                        win,
                        terminal_reason,
                        final_vp_by_side,
                        winner_side,
                        scenario_outcome,
                        phase29_summary,
                    ) = fut.result()
                    returns.append(ret)
                    steps.append(step_count)
                    terminals.append(terminal)
                    timeouts.append(timeout)
                    wins.append(win)
                    for side, vp_count in (final_vp_by_side or {}).items():
                        side_s = str(side)
                        vp_i = int(vp_count)
                        if side_s not in vp_final_counts_by_side:
                            vp_final_counts_by_side[side_s] = {}
                        vp_final_counts_by_side[side_s][vp_i] = (
                            vp_final_counts_by_side[side_s].get(vp_i, 0) + 1
                        )
                    winner_key = str(winner_side or "").strip()
                    if winner_key:
                        winner_side_counts[winner_key] = winner_side_counts.get(winner_key, 0) + 1
                    tracked_side = tracked_side or str(scenario_outcome.get("tracked_side", "")).strip()
                    tracked_metric = tracked_metric or str(scenario_outcome.get("metric", "")).strip()
                    tracked_captured_values.append(int(scenario_outcome.get("captured", 0) or 0))
                    outcome_label = str(scenario_outcome.get("result", "")).strip() or "unknown"
                    scenario_outcome_counts[outcome_label] = scenario_outcome_counts.get(outcome_label, 0) + 1
                    phase29_seed_rows.append(dict(phase29_summary or {}))
                    key = terminal_reason or "unknown"
                    terminal_reason_counts[key] = terminal_reason_counts.get(key, 0) + 1
                    print(
                        f"[Bench]   seed_done return={ret:.3f} "
                        f"steps={step_count} terminal={terminal} timeout={timeout} "
                        f"reason={key}"
                    )
        else:
            for idx, s in enumerate(seeds, start=1):
                (
                    ret,
                    step_count,
                    terminal,
                    timeout,
                    win,
                    terminal_reason,
                    final_vp_by_side,
                    winner_side,
                    scenario_outcome,
                    phase29_summary,
                ) = _run_episode_with_policy(
                    adapter=adapter,
                    scenario_id=scenario_id,
                    seed=s,
                    policy_name=policy,
                    policy_by_side=dict(policy_by_side),
                    max_steps=max_steps,
                    max_steps_override=max_steps_override,
                    mcts_simulations=mcts_simulations,
                    mcts_c_puct=mcts_c_puct,
                    mcts_temperature=mcts_temperature,
                    model=model if policy != "random" else None,
                    action_dim=action_dim,
                    mcts_unroll_steps=mcts_unroll_steps,
                    mcts_discount=mcts_discount,
                )
                returns.append(ret)
                steps.append(step_count)
                terminals.append(terminal)
                timeouts.append(timeout)
                wins.append(win)
                for side, vp_count in (final_vp_by_side or {}).items():
                    side_s = str(side)
                    vp_i = int(vp_count)
                    if side_s not in vp_final_counts_by_side:
                        vp_final_counts_by_side[side_s] = {}
                    vp_final_counts_by_side[side_s][vp_i] = (
                        vp_final_counts_by_side[side_s].get(vp_i, 0) + 1
                    )
                winner_key = str(winner_side or "").strip()
                if winner_key:
                    winner_side_counts[winner_key] = winner_side_counts.get(winner_key, 0) + 1
                tracked_side = tracked_side or str(scenario_outcome.get("tracked_side", "")).strip()
                tracked_metric = tracked_metric or str(scenario_outcome.get("metric", "")).strip()
                tracked_captured_values.append(int(scenario_outcome.get("captured", 0) or 0))
                outcome_label = str(scenario_outcome.get("result", "")).strip() or "unknown"
                scenario_outcome_counts[outcome_label] = scenario_outcome_counts.get(outcome_label, 0) + 1
                phase29_seed_rows.append(dict(phase29_summary or {}))
                key = terminal_reason or "unknown"
                terminal_reason_counts[key] = terminal_reason_counts.get(key, 0) + 1
                print(
                    f"[Bench]   seed {idx}/{len(seeds)}={s} "
                    f"return={ret:.3f} steps={step_count} "
                    f"terminal={terminal} timeout={timeout} reason={key}"
                )
        results.append(
            # Aggregate phase-2.9 eval KPIs across seeds.
            # Keep key naming aligned with training summary contract.
            BenchmarkResult(
                agent_name=agent_name,
                episodes=len(seeds),
                avg_return=sum(returns) / len(returns),
                avg_steps=sum(steps) / len(steps),
                terminal_rate=sum(1 for x in terminals if x) / len(terminals),
                timeout_rate=sum(1 for x in timeouts if x) / len(timeouts),
                win_rate=sum(1 for x in wins if x) / len(wins),
                terminal_reasons={
                    reason: count / len(seeds) for reason, count in terminal_reason_counts.items()
                },
                vp_final_avg_by_side={
                    side: (
                        sum(vp * c for vp, c in counts.items()) / float(max(1, len(seeds)))
                    )
                    for side, counts in vp_final_counts_by_side.items()
                },
                vp_final_distribution_by_side={
                    side: {
                        str(vp): (c / float(max(1, len(seeds))))
                        for vp, c in sorted(counts.items(), key=lambda kv: kv[0])
                    }
                    for side, counts in vp_final_counts_by_side.items()
                },
                winner_side_counts={
                    side: int(c) for side, c in sorted(winner_side_counts.items(), key=lambda kv: kv[0])
                },
                winner_side_rates={
                    side: (float(c) / float(max(1, len(seeds))))
                    for side, c in sorted(winner_side_counts.items(), key=lambda kv: kv[0])
                },
                tracked_side=tracked_side,
                tracked_metric=tracked_metric,
                tracked_captured_avg=(
                    sum(float(x) for x in tracked_captured_values) / float(max(1, len(tracked_captured_values)))
                ),
                tracked_captured_distribution={
                    str(v): (
                        float(sum(1 for x in tracked_captured_values if int(x) == int(v)))
                        / float(max(1, len(tracked_captured_values)))
                    )
                    for v in sorted(set(int(x) for x in tracked_captured_values))
                },
                scenario_outcome_counts={
                    k: int(v) for k, v in sorted(scenario_outcome_counts.items(), key=lambda kv: kv[0])
                },
                scenario_outcome_rates={
                    k: (float(v) / float(max(1, len(seeds))))
                    for k, v in sorted(scenario_outcome_counts.items(), key=lambda kv: kv[0])
                },
                phase_2_9_eval_kpis={
                    "reaction_window_count": int(
                        sum(int(r.get("reaction_window_count", 0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_count": int(
                        sum(int(r.get("reaction_fire_count", 0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_skipped_count": int(
                        sum(int(r.get("reaction_fire_skipped_count", 0)) for r in phase29_seed_rows)
                    ),
                    "reaction_fire_activation_rate": (
                        float(sum(float(r.get("reaction_fire_activation_rate", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "reaction_fire_kill_conversion_rate": (
                        float(sum(float(r.get("reaction_fire_kill_conversion_rate", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "reaction_fire_damage_induced_proxy": (
                        float(sum(float(r.get("reaction_fire_damage_induced_proxy", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "reaction_fire_damage_prevented_proxy": (
                        float(sum(float(r.get("reaction_fire_damage_prevented_proxy", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "assault_melee_action_family_count": int(
                        sum(int(r.get("assault_melee_action_family_count", 0)) for r in phase29_seed_rows)
                    ),
                    "melee_attempts": int(
                        sum(int(r.get("melee_attempts", 0)) for r in phase29_seed_rows)
                    ),
                    "melee_success_rate": (
                        float(sum(float(r.get("melee_success_rate", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "melee_kills_per_attempt": (
                        float(sum(float(r.get("melee_kills_per_attempt", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "melee_damage_per_attempt": (
                        float(sum(float(r.get("melee_damage_per_attempt", 0.0)) for r in phase29_seed_rows))
                        / float(max(1, len(phase29_seed_rows)))
                    ),
                    "assault_favorable_count": int(
                        sum(int(r.get("assault_favorable_count", 0)) for r in phase29_seed_rows)
                    ),
                    "assault_unfavorable_count": int(
                        sum(int(r.get("assault_unfavorable_count", 0)) for r in phase29_seed_rows)
                    ),
                },
            )
        )
        last = results[-1]
        print(
            f"[Bench] agent={agent_name} done "
            f"avg_return={last.avg_return:.3f} avg_steps={last.avg_steps:.1f} "
            f"terminal_rate={last.terminal_rate:.3f} timeout_rate={last.timeout_rate:.3f} "
            f"win_rate={last.win_rate:.3f}"
        )

    payload = {"scenario_id": scenario_id, "results": [r.__dict__ for r in results]}
    muzero_row = next((r.__dict__ for r in results if r.agent_name == "muzero_stub"), {})
    baseline_row = next((r.__dict__ for r in results if r.agent_name == "baseline_random"), {})
    train_phase29 = _load_train_phase29_from_checkpoint(checkpoint_path=checkpoint_path)
    eval_phase29 = dict(muzero_row.get("phase_2_9_eval_kpis", {}) or {})
    payload["phase_2_9_train_eval"] = _build_phase29_train_eval(
        train_kpis=train_phase29,
        eval_kpis=eval_phase29,
    )
    payload["phase_2_9_promotion_gate"] = _build_phase29_promotion_gate(
        train_kpis=train_phase29,
        eval_kpis=eval_phase29,
        muzero_row=muzero_row,
        baseline_row=baseline_row,
    )
    out = run_root / "bench_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VOEC benchmark matrix.")
    parser.add_argument(
        "--config",
        default="assault_bench/configs/benchmark_config.yaml",
        help="Path to benchmark YAML config file.",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="Optional MuZero checkpoint path; empty or 'latest' auto-selects newest iter_*.pt under runs/muzero_*/checkpoints.",
    )
    parser.add_argument(
        "--muzero-config",
        default="",
        help="Optional MuZero config path used to build model shape when --checkpoint is set.",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    print(
        json.dumps(
            run_benchmark(
                config_path=args.config,
                checkpoint_path=args.checkpoint,
                muzero_config_path=args.muzero_config,
            ),
            indent=2,
        )
    )
