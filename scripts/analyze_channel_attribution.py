"""
Channel Attribution and Effectiveness Analyzer for Assault RL Networks.

Evaluates:
1. Spatial sparsity and dynamic range (active vs dead channels).
2. Saliency gradients (sensitivity of policy and value heads).
3. Occlusion/ablation impact (KL divergence of policy, value shift, decision flip rate).
4. Composite importance score and actionable classification per channel.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure assault repository root is in python path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import torch
import torch.nn as nn
import torch.nn.functional as F

from agents.efficientzero_v2.core.interop import EZV2VOECAdapter
from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.selfplay import _observation_to_tensor
from agents.efficientzero_v2.train.train_engine import _channel_name
from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator


class LegacyConvBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(x + self.conv2(self.act(self.conv1(x))))


class LegacyEZV2CNN(nn.Module):
    def __init__(
        self,
        observation_channels: int = 32,
        hidden_dim: int = 48,
        action_dim: int = 32,
        dynamics_blocks: int = 3,
        prediction_blocks: int = 2,
    ):
        super().__init__()
        self.observation_channels = observation_channels
        self.observation_height = 16
        self.observation_width = 16
        self.representation_input = nn.Sequential(
            nn.Conv2d(observation_channels, hidden_dim, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        self.representation_tower = nn.Sequential(
            *[LegacyConvBlock(hidden_dim) for _ in range(max(1, prediction_blocks))]
        )
        self.action_embedding = nn.Embedding(action_dim, 16)
        self.dynamics_merge = nn.Sequential(
            nn.Conv2d(hidden_dim + 16, hidden_dim, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        self.dynamics_state = nn.Sequential(
            *[LegacyConvBlock(hidden_dim) for _ in range(max(1, dynamics_blocks))]
        )
        self.prediction_trunk = nn.Sequential(
            *[LegacyConvBlock(hidden_dim) for _ in range(max(1, prediction_blocks))]
        )
        flat = hidden_dim * 16 * 16
        self.dynamics_reward = nn.Sequential(
            nn.Linear(flat, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        self.prediction_policy = nn.Linear(flat, action_dim)
        self.prediction_value = nn.Linear(flat, 1)
        self.prediction_objective = nn.Linear(flat, 1)
        self.consistency_projection = nn.Sequential(
            nn.Linear(flat, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
        )

    def initial_inference(self, obs: torch.Tensor):
        hidden = self.representation_tower(self.representation_input(obs))
        pred_hidden = self.prediction_trunk(hidden)
        flat = torch.flatten(pred_hidden, start_dim=1)
        p = self.prediction_policy(flat)
        v = self.prediction_value(flat)
        r = torch.zeros_like(v)
        return hidden, p, v, r


def _collect_observations(
    voec_config_path: Path,
    scenario_id: str,
    seeds: list[int],
    steps_per_seed: int = 15,
    channels: int = 32,
    height: int = 16,
    width: int = 16,
) -> list[torch.Tensor]:
    """Collect real observation tensors across multiple game rollouts."""
    voec_cfg = load_voec_config(voec_config_path)
    sim = VOECSimulator(assets=voec_cfg.assets)
    adapter = EZV2VOECAdapter(sim)

    observations: list[torch.Tensor] = []

    for seed in seeds:
        obs = adapter.initial_state(scenario_id=scenario_id, seed=seed)
        for _ in range(steps_per_seed):
            ten = _observation_to_tensor(obs, channels=channels, height=height, width=width)
            observations.append(ten.detach().cpu())

            legal = list(adapter.legal_actions() or [])
            if not legal or getattr(obs, "done", False):
                break
            # Step with first legal action to evolve the board
            action = legal[0]
            adapter.apply(action)
            obs = adapter.observation()

    return observations


def _load_model(run_dir: Path) -> nn.Module:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"run_manifest.json not found in {run_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    m_cfg = manifest.get("config", {}).get("model", {})

    ckpt_path = run_dir / "checkpoints" / "final.pt"
    if not ckpt_path.exists():
        pt_files = list((run_dir / "checkpoints").glob("*.pt"))
        if not pt_files:
            raise FileNotFoundError(f"No checkpoint found in {run_dir / 'checkpoints'}")
        ckpt_path = pt_files[0]

    state_dict = torch.load(ckpt_path, map_location="cpu", weights_only=True)

    # Check whether state_dict has modern (GroupNorm / SE) or legacy keys
    is_legacy = any("conv1.bias" in k for k in state_dict.keys()) or any(
        "representation_tower.0.conv1.bias" in k for k in state_dict.keys()
    )

    if is_legacy:
        model = LegacyEZV2CNN(
            observation_channels=int(m_cfg.get("observation_channels", 32)),
            hidden_dim=int(m_cfg.get("hidden_dim", 48)),
            action_dim=int(m_cfg.get("action_dim", 32)),
            dynamics_blocks=int(m_cfg.get("dynamics_blocks", 3)),
            prediction_blocks=int(m_cfg.get("prediction_blocks", 2)),
        )
    else:
        model = EfficientZeroV2Network(
            observation_dim=4,
            hidden_dim=int(m_cfg.get("hidden_dim", 48)),
            action_dim=int(m_cfg.get("action_dim", 32)),
            encoder_type=str(m_cfg.get("encoder_type", "cnn")),
            observation_channels=int(m_cfg.get("observation_channels", 32)),
            observation_height=int(m_cfg.get("observation_height", 16)),
            observation_width=int(m_cfg.get("observation_width", 16)),
            dynamics_blocks=int(m_cfg.get("dynamics_blocks", 3)),
            prediction_blocks=int(m_cfg.get("prediction_blocks", 2)),
        )

    model.load_state_dict(state_dict)
    model.eval()
    return model


def analyze_channels(
    model: nn.Module,
    observations: list[torch.Tensor],
    device: str = "cpu",
) -> dict[str, Any]:
    model = model.to(device)
    num_samples = len(observations)
    if num_samples == 0:
        raise ValueError("No observations provided for analysis.")

    num_channels = getattr(model, "observation_channels", 32)
    height = getattr(model, "observation_height", 16)
    width = getattr(model, "observation_width", 16)

    # Channel stats accumulators
    nonzero_ratios = [0.0] * num_channels
    mean_abs_values = [0.0] * num_channels
    std_values = [0.0] * num_channels

    # Attribution / Saliency accumulators
    grad_saliency_value = [0.0] * num_channels
    grad_saliency_policy = [0.0] * num_channels

    # Ablation accumulators
    kl_divergence = [0.0] * num_channels
    value_shift = [0.0] * num_channels
    decision_flips = [0] * num_channels

    for obs in observations:
        obs_tensor = obs.to(device).unsqueeze(0)  # Shape (1, C, H, W)

        # Baseline forward pass with gradients for saliency
        obs_req = obs_tensor.clone().detach().requires_grad_(True)
        _, policy_logits_base, value_base, _ = model.initial_inference(obs_req)

        probs_base = F.softmax(policy_logits_base, dim=-1)
        top_action_base = int(torch.argmax(policy_logits_base, dim=-1).item())

        # Gradient Saliency for Value
        model.zero_grad()
        if obs_req.grad is not None:
            obs_req.grad.zero_()
        value_base.sum().backward(retain_graph=True)
        if obs_req.grad is not None:
            v_grad = obs_req.grad.abs().squeeze(0)  # (C, H, W)
            for c in range(num_channels):
                grad_saliency_value[c] += float(v_grad[c].mean().item())

        # Gradient Saliency for Policy (Entropy-weighted / expected logits)
        model.zero_grad()
        if obs_req.grad is not None:
            obs_req.grad.zero_()
        policy_scalar = (probs_base * policy_logits_base).sum()
        policy_scalar.backward()
        if obs_req.grad is not None:
            p_grad = obs_req.grad.abs().squeeze(0)
            for c in range(num_channels):
                grad_saliency_policy[c] += float(p_grad[c].mean().item())

        # Baseline values for ablation comparison (without grad)
        with torch.no_grad():
            _, base_p_logits, base_val, _ = model.initial_inference(obs_tensor)
            p_base_dist = F.softmax(base_p_logits, dim=-1)
            v_base_val = float(base_val.item())

            # Basic spatial stats
            for c in range(num_channels):
                plane = obs_tensor[0, c]
                nonzero_count = float((plane != 0).sum().item())
                nonzero_ratios[c] += nonzero_count / float(height * width)
                mean_abs_values[c] += float(plane.abs().mean().item())
                std_values[c] += float(plane.std().item())

                # Ablation: zero-out channel c
                ablated_obs = obs_tensor.clone()
                ablated_obs[0, c, :, :] = 0.0

                _, abl_p_logits, abl_val, _ = model.initial_inference(ablated_obs)
                p_abl_dist = F.softmax(abl_p_logits, dim=-1)
                v_abl_val = float(abl_val.item())

                # KL divergence: KL(P_base || P_ablated)
                kl = F.kl_div(p_abl_dist.log(), p_base_dist, reduction="batchmean").item()
                kl_divergence[c] += max(0.0, float(kl))
                value_shift[c] += abs(v_base_val - v_abl_val)

                top_action_abl = int(torch.argmax(abl_p_logits, dim=-1).item())
                if top_action_abl != top_action_base:
                    decision_flips[c] += 1

    # Normalize by sample count
    results_per_channel: list[dict[str, Any]] = []
    max_kl = max(kl_divergence) / float(num_samples) if max(kl_divergence) > 0 else 1.0
    max_v_shift = max(value_shift) / float(num_samples) if max(value_shift) > 0 else 1.0
    max_p_grad = max(grad_saliency_policy) / float(num_samples) if max(grad_saliency_policy) > 0 else 1.0

    for c in range(num_channels):
        name = _channel_name(c)
        nz_ratio = nonzero_ratios[c] / float(num_samples)
        m_abs = mean_abs_values[c] / float(num_samples)
        std_v = std_values[c] / float(num_samples)
        kl = kl_divergence[c] / float(num_samples)
        v_diff = value_shift[c] / float(num_samples)
        flips = decision_flips[c] / float(num_samples)
        v_grad = grad_saliency_value[c] / float(num_samples)
        p_grad = grad_saliency_policy[c] / float(num_samples)

        # Composite score
        comp_score = (
            0.40 * (kl / max_kl if max_kl > 0 else 0)
            + 0.30 * (v_diff / max_v_shift if max_v_shift > 0 else 0)
            + 0.20 * flips
            + 0.10 * (p_grad / max_p_grad if max_p_grad > 0 else 0)
        )

        # Classification
        if nz_ratio == 0.0 or std_v < 1e-6:
            status = "INACTIVE_OR_CONSTANT"
            recommendation = "Canal nulo/constante. Revisar extracción si se esperaba activo."
        elif comp_score >= 0.30 or flips >= 0.15:
            status = "HIGH_EFFECTIVENESS"
            recommendation = "Canal clave para decisiones tácticas. Mantener indispensable."
        elif comp_score >= 0.10 or flips >= 0.05:
            status = "MODERATE_EFFECTIVENESS"
            recommendation = "Aporta contexto táctico complementario."
        else:
            status = "LOW_EFFECTIVENESS"
            recommendation = "Bajo impacto en política/valor; potencial candidato a poda/refactor."

        # Category
        if 0 <= c <= 5:
            category = "Vitality & Presence"
        elif 6 <= c <= 7:
            category = "Global Context"
        elif 8 <= c <= 11:
            category = "Unit Roles"
        elif 12 <= c <= 21:
            category = "Map & Objectives"
        else:
            category = "Combat Capabilities"

        results_per_channel.append(
            {
                "index": c,
                "name": name,
                "category": category,
                "status": status,
                "importance_score": round(comp_score, 4),
                "decision_flip_rate": round(flips * 100.0, 2),
                "kl_divergence": round(kl, 5),
                "value_shift_mean": round(v_diff, 5),
                "nonzero_ratio": round(nz_ratio, 4),
                "mean_abs": round(m_abs, 4),
                "std": round(std_v, 4),
                "grad_saliency_policy": round(p_grad, 6),
                "grad_saliency_value": round(v_grad, 6),
                "recommendation": recommendation,
            }
        )

    # Sort channels by importance score descending
    ranked_channels = sorted(results_per_channel, key=lambda x: x["importance_score"], reverse=True)

    # Group summary by category
    categories_summary: dict[str, dict[str, float]] = {}
    for cat in ["Vitality & Presence", "Global Context", "Unit Roles", "Map & Objectives", "Combat Capabilities"]:
        cat_items = [ch for ch in results_per_channel if ch["category"] == cat]
        if cat_items:
            categories_summary[cat] = {
                "avg_importance": round(sum(ch["importance_score"] for ch in cat_items) / len(cat_items), 4),
                "avg_flip_rate": round(sum(ch["decision_flip_rate"] for ch in cat_items) / len(cat_items), 2),
                "avg_kl": round(sum(ch["kl_divergence"] for ch in cat_items) / len(cat_items), 5),
                "active_channels": sum(1 for ch in cat_items if ch["status"] != "INACTIVE_OR_CONSTANT"),
                "total_channels": len(cat_items),
            }

    return {
        "num_observations_analyzed": num_samples,
        "channels_analyzed": num_channels,
        "categories_summary": categories_summary,
        "ranked_channels": ranked_channels,
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze channel effectiveness and attribution.")
    parser.add_argument(
        "--run-dir",
        type=str,
        default="runs/efficientzero_v2_dfd76db3",
        help="Path to training run directory",
    )
    parser.add_argument(
        "--voec-config",
        type=str,
        default="voec_sim/configs/voec_config.yaml",
        help="Path to voec_config.yaml",
    )
    parser.add_argument(
        "--scenario-id",
        type=str,
        default="battaglia_cittadina_2_1",
        help="Scenario ID for rollouts",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[42, 101, 202, 303],
        help="Seeds for environment rollouts",
    )
    parser.add_argument(
        "--steps-per-seed",
        type=int,
        default=15,
        help="Steps to roll out per seed",
    )
    parser.add_argument(
        "--out-json",
        type=str,
        default="",
        help="Optional path to output JSON report",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    voec_cfg_path = Path(args.voec_config).resolve()

    print(f"[1/4] Loading model from: {run_dir}")
    model = _load_model(run_dir)

    print(f"[2/4] Collecting observations across seeds {args.seeds} in scenario '{args.scenario_id}'...")
    observations = _collect_observations(
        voec_config_path=voec_cfg_path,
        scenario_id=args.scenario_id,
        seeds=args.seeds,
        steps_per_seed=args.steps_per_seed,
        channels=getattr(model, "observation_channels", 32),
        height=getattr(model, "observation_height", 16),
        width=getattr(model, "observation_width", 16),
    )
    print(f"      Total observation samples collected: {len(observations)}")

    print(f"[3/4] Running saliency, gradient attribution and occlusion ablation analysis...")
    report = analyze_channels(model, observations, device="cpu")

    out_path = Path(args.out_json) if args.out_json else run_dir / "metrics" / "channel_effectiveness_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[4/4] Analysis complete! Report written to: {out_path}")

    # Print summary table
    print("\n" + "=" * 95)
    print(f"{'Idx':<4} {'Name':<26} {'Category':<20} {'Status':<18} {'Score':<7} {'Flip %':<7} {'KL':<8}")
    print("-" * 95)
    for ch in report["ranked_channels"]:
        print(
            f"{ch['index']:<4} {ch['name']:<26} {ch['category']:<20} {ch['status']:<18} "
            f"{ch['importance_score']:<7.3f} {ch['decision_flip_rate']:<7.1f} {ch['kl_divergence']:<8.4f}"
        )
    print("=" * 95)


if __name__ == "__main__":
    main()
