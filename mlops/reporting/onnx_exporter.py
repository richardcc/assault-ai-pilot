"""
ONNX Model Exporter for EfficientZero V2.
Exports representation, initial inference, and recurrent dynamics models
for visual inspection in Netron (https://netron.app).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
import torch.nn as nn

from agents.efficientzero_v2.core.network import EfficientZeroV2Network

logger = logging.getLogger("assault.mlops.onnx_exporter")


class InitialInferenceONNX(nn.Module):
    """Wraps initial inference for ONNX graph tracing."""

    def __init__(self, model: EfficientZeroV2Network) -> None:
        super().__init__()
        self.model = model

    def forward(
        self, observation: torch.Tensor
    ) -> Tuple[
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
    ]:
        hidden, policy, value, reward, aux = self.model.initial_inference(
            observation, return_aux=True
        )
        threat = (
            aux["threat_map_pred"]
            if "threat_map_pred" in aux and aux["threat_map_pred"] is not None
            else torch.zeros(1)
        )
        attrition = (
            aux["attrition_pred"]
            if "attrition_pred" in aux and aux["attrition_pred"] is not None
            else torch.zeros(1)
        )
        morale = (
            aux["morale_pred"]
            if "morale_pred" in aux and aux["morale_pred"] is not None
            else torch.zeros(1)
        )
        ownership = (
            aux["final_ownership_pred"]
            if "final_ownership_pred" in aux and aux["final_ownership_pred"] is not None
            else torch.zeros(1)
        )
        return hidden, policy, value, threat, attrition, morale, ownership


class RecurrentInferenceONNX(nn.Module):
    """Wraps recurrent dynamics inference for ONNX graph tracing."""

    def __init__(self, model: EfficientZeroV2Network) -> None:
        super().__init__()
        self.model = model

    def forward(
        self, hidden: torch.Tensor, action_onehot: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        next_hidden, policy, value, reward, aux = self.model.recurrent_inference(
            hidden, action_onehot, return_aux=True
        )
        return next_hidden, policy, value, reward


class RepresentationTowerONNX(nn.Module):
    """Wraps the pure representation backbone for ONNX graph tracing."""

    def __init__(self, model: EfficientZeroV2Network) -> None:
        super().__init__()
        self.model = model

    def forward(self, observation: torch.Tensor) -> torch.Tensor:
        obs_in = self.model._gate_input_channels(observation)
        hidden = self.model._scale_latent(
            self.model.representation_tower(self.model.representation_input(obs_in))
        )
        return hidden


def _resolve_checkpoint_and_config(
    repo_root: Path, run_id: str, checkpoint_path: Optional[str] = None
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """Locates checkpoint file and training config for a given run ID."""
    cfg: Dict[str, Any] = {}
    found_ckpt: Optional[Path] = None

    if checkpoint_path:
        p = Path(checkpoint_path)
        if not p.is_absolute():
            p = repo_root / p
        if p.exists() and p.is_file():
            found_ckpt = p

    # Search candidates across runs/ and runs_curriculum/
    search_dirs = [
        repo_root / "runs" / run_id,
        repo_root / "runs_curriculum" / run_id,
        repo_root / "runs_curriculum" / "experiments" / run_id,
    ]

    for sdir in search_dirs:
        if not sdir.exists():
            continue
        cfg_path = sdir / "config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        if found_ckpt is None:
            ckpt_candidates = [
                sdir / "checkpoints" / "final.pt",
                sdir / "checkpoints" / "best.pt",
                sdir / "final.pt",
            ]
            for c in ckpt_candidates:
                if c.exists() and c.is_file():
                    found_ckpt = c
                    break

            if found_ckpt is None:
                all_pts = sorted(sdir.glob("**/*.pt"), key=lambda x: x.stat().st_mtime, reverse=True)
                if all_pts:
                    found_ckpt = all_pts[0]

    return found_ckpt, cfg


def export_model_to_onnx(
    repo_root: Path,
    run_id: str,
    checkpoint_path: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Exports EfficientZero V2 network components to ONNX format for Netron visualization.

    Returns:
        Dictionary with exported files, sizes, paths and download URLs.
    """
    ckpt_file, cfg = _resolve_checkpoint_and_config(repo_root, run_id, checkpoint_path)

    # Extract network dimensions with defaults
    model_cfg = dict(cfg.get("model", {}) or {})
    obs_channels = int(
        model_cfg.get(
            "observation_channels",
            model_cfg.get("channels", 38),
        )
    )
    obs_h = int(model_cfg.get("observation_height", 16))
    obs_w = int(model_cfg.get("observation_width", 16))
    hidden_dim = int(model_cfg.get("hidden_dim", 48))
    action_dim = int(model_cfg.get("action_dim", 32))
    support_size = int(model_cfg.get("support_size", 30))

    # Initialize model
    model = EfficientZeroV2Network(
        observation_dim=obs_channels * obs_h * obs_w,
        hidden_dim=hidden_dim,
        action_dim=action_dim,
        encoder_type="cnn",
        observation_channels=obs_channels,
        observation_height=obs_h,
        observation_width=obs_w,
        support_size=support_size,
        enable_threat_head=bool(model_cfg.get("enable_threat_head", True)),
        enable_final_ownership_head=bool(model_cfg.get("enable_final_ownership_head", True)),
        enable_attrition_head=bool(model_cfg.get("enable_attrition_head", True)),
        enable_morale_head=bool(model_cfg.get("enable_morale_head", True)),
    )

    if ckpt_file and ckpt_file.exists():
        try:
            state = torch.load(ckpt_file, map_location="cpu", weights_only=False)
            if isinstance(state, dict):
                if "model_state_dict" in state:
                    model.load_state_dict(state["model_state_dict"], strict=False)
                elif "state_dict" in state:
                    model.load_state_dict(state["state_dict"], strict=False)
                elif "network" in state:
                    model.load_state_dict(state["network"], strict=False)
                else:
                    model.load_state_dict(state, strict=False)
        except Exception as exc:
            logger.warning(f"Could not load state_dict into model: {exc}")

    model.eval()

    # Determine destination directory
    if output_dir is None:
        target_root = repo_root / "runs" / run_id
        if not target_root.exists() and (repo_root / "runs_curriculum" / run_id).exists():
            target_root = repo_root / "runs_curriculum" / run_id
        out_dir = target_root / "onnx"
    else:
        out_dir = output_dir

    out_dir.mkdir(parents=True, exist_ok=True)

    files_exported: List[Dict[str, Any]] = []

    # 1. Initial Inference (Representation + Predictions + Tactical Heads)
    init_path = out_dir / "ezv2_initial_inference.onnx"
    try:
        init_wrapper = InitialInferenceONNX(model)
        dummy_obs = torch.randn(1, obs_channels, obs_h, obs_w)
        torch.onnx.export(
            init_wrapper,
            dummy_obs,
            str(init_path),
            input_names=["observation"],
            output_names=[
                "latent_state",
                "policy_logits",
                "value",
                "threat_map",
                "attrition",
                "morale",
                "final_ownership",
            ],
            dynamic_axes={"observation": {0: "batch"}, "latent_state": {0: "batch"}},
            opset_version=17,
        )
        files_exported.append(
            {
                "name": "ezv2_initial_inference.onnx",
                "label": "Initial Inference (Backbone + 10 Tactical Heads)",
                "path": str(init_path),
                "size_bytes": init_path.stat().st_size,
                "download_url": f"/api/model/download-onnx?run_id={run_id}&file=ezv2_initial_inference.onnx",
            }
        )
    except Exception as exc:
        logger.error(f"Failed exporting initial inference ONNX: {exc}")

    # 2. Recurrent Inference (Dynamics + Rollout Predictions)
    rec_path = out_dir / "ezv2_recurrent_inference.onnx"
    try:
        rec_wrapper = RecurrentInferenceONNX(model)
        dummy_hidden = torch.randn(1, hidden_dim, obs_h, obs_w)
        dummy_action = torch.zeros(1, action_dim)
        dummy_action[0, 0] = 1.0
        torch.onnx.export(
            rec_wrapper,
            (dummy_hidden, dummy_action),
            str(rec_path),
            input_names=["latent_state", "action_onehot"],
            output_names=["next_latent_state", "policy_logits", "value", "reward"],
            dynamic_axes={
                "latent_state": {0: "batch"},
                "action_onehot": {0: "batch"},
                "next_latent_state": {0: "batch"},
            },
            opset_version=17,
        )
        files_exported.append(
            {
                "name": "ezv2_recurrent_inference.onnx",
                "label": "Recurrent Dynamics (Transition Tower + Value/Reward)",
                "path": str(rec_path),
                "size_bytes": rec_path.stat().st_size,
                "download_url": f"/api/model/download-onnx?run_id={run_id}&file=ezv2_recurrent_inference.onnx",
            }
        )
    except Exception as exc:
        logger.error(f"Failed exporting recurrent inference ONNX: {exc}")

    # 3. Pure Representation Tower
    tower_path = out_dir / "ezv2_representation_tower.onnx"
    try:
        tower_wrapper = RepresentationTowerONNX(model)
        dummy_obs = torch.randn(1, obs_channels, obs_h, obs_w)
        torch.onnx.export(
            tower_wrapper,
            dummy_obs,
            str(tower_path),
            input_names=["observation"],
            output_names=["latent_state"],
            dynamic_axes={"observation": {0: "batch"}, "latent_state": {0: "batch"}},
            opset_version=17,
        )
        files_exported.append(
            {
                "name": "ezv2_representation_tower.onnx",
                "label": "Representation Tower (HexConv2d + Residual Backbone)",
                "path": str(tower_path),
                "size_bytes": tower_path.stat().st_size,
                "download_url": f"/api/model/download-onnx?run_id={run_id}&file=ezv2_representation_tower.onnx",
            }
        )
    except Exception as exc:
        logger.error(f"Failed exporting representation tower ONNX: {exc}")

    return {
        "ok": len(files_exported) > 0,
        "run_id": run_id,
        "checkpoint_used": str(ckpt_file) if ckpt_file else None,
        "export_dir": str(out_dir),
        "files": files_exported,
        "netron_url": "https://netron.app",
        "message": f"Successfully exported {len(files_exported)} ONNX models.",
    }
