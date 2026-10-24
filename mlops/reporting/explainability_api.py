"""
Hexagonal Spatial Causal Attribution Service (IGNH / Grad-CAM) for EfficientZero V2.

Computes fine-grained channel attribution and spatial hexagonal heatmaps for unit
decisions in Assault match replays using:
1. Integrated Gradients for Heterogeneous features (IGNH - Sundararajan et al. 2017 adapted for hex wargames).
2. Hexagonal Grad-CAM over the representation tower.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from agents.efficientzero_v2.core.adapter_voec import EZV2Observation
from agents.efficientzero_v2.core.observation import (
    DEFAULT_OBS_CHANNELS,
    DEFAULT_OBS_HEIGHT,
    DEFAULT_OBS_WIDTH,
    observation_to_tensor,
)
from agents.efficientzero_v2.core.selfplay import _action_id_to_index
from agents.efficientzero_v2.train.train_engine import _channel_name
try:
    from scripts.analyze_channel_attribution import _load_model
except Exception:
    def _load_model(run_dir: Path) -> Any:
        return None

logger = logging.getLogger("assault.explainability")

# Canonical tactical channel groups
CHANNEL_GROUPS: dict[str, list[int]] = {
    "COVER_TERRAIN": [15, 16, 27],
    "LOS_VISIBILITY": [17],
    "THREAT_MAP": [1, 3, 4, 5, 7, 9, 11, 23, 29],
    "VP_PROXIMITY": [6, 13, 14, 18, 36, 37],
    "DOCTRINE_ROLE": [32, 33, 34, 35],
    "UNIT_STATE_TACTICAL": [0, 2, 8, 10, 21, 22, 24, 25, 26, 28, 30, 31],
}

CHANNEL_GROUP_LABELS: dict[str, str] = {
    "COVER_TERRAIN": "Cover & Fortifications",
    "LOS_VISIBILITY": "LOS & Concealment",
    "THREAT_MAP": "Threat Field & Reaction Risk",
    "VP_PROXIMITY": "VP Proximity & Objective Pull",
    "DOCTRINE_ROLE": "Doctrine Profile & Engagement Range",
    "UNIT_STATE_TACTICAL": "Unit Status & Tactical Posture",
}

_MODEL_CACHE: dict[str, nn.Module] = {}


def _resolve_channel_group(channel_idx: int) -> str:
    for group, indices in CHANNEL_GROUPS.items():
        if channel_idx in indices:
            return group
    return "OTHER"


def get_cached_model(run_dir: Path) -> nn.Module:
    key = str(run_dir.resolve())
    if key not in _MODEL_CACHE:
        logger.info("Loading EfficientZero V2 model weights from %s", run_dir)
        _MODEL_CACHE[key] = _load_model(run_dir)
    return _MODEL_CACHE[key]


def build_obs_from_step_data(
    step: dict[str, Any],
    scenario_overlay: dict[str, Any] | None = None,
) -> tuple[EZV2Observation, dict[str, Any]]:
    """
    Reconstruct an EZV2Observation instance from replay step data and optional scenario overlay.
    """
    turn = int(step.get("turn", step.get("game_turn", 1)) or 1)
    to_play = str(step.get("to_play", "") or "")
    done = bool(step.get("done", False))

    overlay = scenario_overlay or {}
    max_turns = int(step.get("max_turns", overlay.get("max_turns", 8)) or 8)

    # 1. Playable hexes
    playable_hexes: list[dict[str, Any]] = []
    map_cells = list(overlay.get("map_cells", []) or [])
    if map_cells:
        for c in map_cells:
            if isinstance(c, dict) and "q" in c and "r" in c:
                playable_hexes.append({"q": int(c["q"]), "r": int(c["r"])})
    if not playable_hexes:
        # Fall back to step observations or coordinates in units/vps
        coords_set = set()
        for u in list(step.get("units", []) or step.get("unit_positions", []) or []):
            if isinstance(u, dict) and "q" in u and "r" in u:
                coords_set.add((int(u["q"]), int(u["r"])))
        for vp_k in (step.get("vp_map") or {}).keys():
            parts = str(vp_k).split(",")
            if len(parts) == 2:
                try:
                    coords_set.add((int(parts[0]), int(parts[1])))
                except Exception:
                    pass
        playable_hexes = [{"q": q, "r": r} for q, r in sorted(coords_set)]

    # 2. VP hexes and ownership
    vp_hexes: list[dict[str, Any]] = []
    vp_owner_by_hex: dict[str, str] = {}
    overlay_vps = list(overlay.get("vp_hexes", []) or [])
    step_vp_map = dict(step.get("vp_map", step.get("vp_map_after", {})) or {})

    if overlay_vps:
        for v in overlay_vps:
            if isinstance(v, dict) and "q" in v and "r" in v:
                vq, vr = int(v["q"]), int(v["r"])
                vp_hexes.append({"q": vq, "r": vr, "value": float(v.get("value", 2.0) or 2.0)})
                k = f"{vq},{vr}"
                owner = step_vp_map.get(k, v.get("initial_owner", ""))
                if owner:
                    vp_owner_by_hex[k] = str(owner)
    elif step_vp_map:
        for k, owner in step_vp_map.items():
            parts = str(k).split(",")
            if len(parts) == 2:
                try:
                    vq, vr = int(parts[0]), int(parts[1])
                    vp_hexes.append({"q": vq, "r": vr, "value": 2.0})
                    if owner:
                        vp_owner_by_hex[k] = str(owner)
                except Exception:
                    pass

    # 3. Terrain properties
    terrain_cover_by_hex: dict[str, float] = dict(step.get("obs_terrain_cover_map", {}) or {})
    terrain_los_block_by_hex: dict[str, int] = dict(step.get("obs_terrain_los_block_map", {}) or {})
    terrain_move_cost_by_hex: dict[str, float] = dict(step.get("obs_terrain_move_cost_map", {}) or {})
    terrain_type_by_hex: dict[str, str] = dict(step.get("obs_terrain_type_map", {}) or {})
    fortification_type_by_hex: dict[str, str] = dict(step.get("obs_fortification_type_map", {}) or {})

    # Fill missing terrain from overlay cells if needed
    for cell in map_cells:
        if isinstance(cell, dict) and "q" in cell and "r" in cell:
            k = f"{int(cell['q'])},{int(cell['r'])}"
            t_type = str(cell.get("terrain", "clear") or "clear").lower()
            if k not in terrain_type_by_hex:
                terrain_type_by_hex[k] = t_type
            if k not in terrain_cover_by_hex:
                # Standard cover estimation
                if "woods" in t_type or "forest" in t_type:
                    terrain_cover_by_hex[k] = 0.35
                elif "urban" in t_type or "town" in t_type or "village" in t_type:
                    terrain_cover_by_hex[k] = 0.50
                elif "rough" in t_type or "hill" in t_type:
                    terrain_cover_by_hex[k] = 0.25
                elif "bocage" in t_type:
                    terrain_cover_by_hex[k] = 0.40
                else:
                    terrain_cover_by_hex[k] = 0.0
            if k not in terrain_los_block_by_hex:
                if "woods" in t_type or "forest" in t_type or "urban" in t_type or "town" in t_type:
                    terrain_los_block_by_hex[k] = 1
                else:
                    terrain_los_block_by_hex[k] = 0
            if k not in terrain_move_cost_by_hex:
                if "woods" in t_type or "forest" in t_type:
                    terrain_move_cost_by_hex[k] = 2.0
                elif "rough" in t_type or "hill" in t_type:
                    terrain_move_cost_by_hex[k] = 1.5
                else:
                    terrain_move_cost_by_hex[k] = 1.0

    # 4. Units
    raw_units = list(step.get("units", []) or [])
    if not raw_units and list(step.get("unit_positions", []) or []):
        hp_map = dict(step.get("unit_hp_map", {}) or {})
        alive_map = dict(step.get("unit_alive_map", {}) or {})
        supp_map = dict(step.get("unit_suppressed_map", {}) or {})
        for p in list(step.get("unit_positions", []) or []):
            if isinstance(p, dict) and "unit_id" in p:
                uid = str(p["unit_id"])
                side_val = str(p.get("side", "") or uid.split("_")[0])
                raw_units.append({
                    "unit_id": uid,
                    "unit_key": str(p.get("unit_key", uid)),
                    "side": side_val,
                    "q": int(p.get("q", 0) or 0),
                    "r": int(p.get("r", 0) or 0),
                    "hp": float(hp_map.get(uid, 3.0)),
                    "alive": bool(alive_map.get(uid, True)),
                    "suppressed": bool(supp_map.get(uid, False)),
                    "doctrine_role": str(p.get("doctrine_role", p.get("role_assigned", "SCREEN"))),
                })

    obs = EZV2Observation(
        turn=turn,
        to_play=to_play,
        done=done,
        units=raw_units,
        playable_hexes=playable_hexes,
        vp_hexes=vp_hexes,
        vp_owner_by_hex=vp_owner_by_hex,
        terrain_move_cost_by_hex=terrain_move_cost_by_hex,
        terrain_cover_by_hex=terrain_cover_by_hex,
        terrain_los_block_by_hex=terrain_los_block_by_hex,
        terrain_type_by_hex=terrain_type_by_hex,
        fortification_type_by_hex=fortification_type_by_hex,
        max_turns=max_turns,
    )

    # Compute coordinate bounding box
    all_coords: list[tuple[int, int]] = []
    for u in raw_units:
        q, r = u.get("q"), u.get("r")
        if isinstance(q, int) and isinstance(r, int):
            all_coords.append((q, r))
    for h in playable_hexes:
        q, r = h.get("q"), h.get("r")
        if isinstance(q, int) and isinstance(r, int):
            all_coords.append((q, r))

    if all_coords:
        min_q = min(q for q, _ in all_coords)
        max_q = max(q for q, _ in all_coords)
        min_r = min(r for _, r in all_coords)
        max_r = max(r for _, r in all_coords)
    else:
        min_q, max_q = -8, 8
        min_r, max_r = -8, 8

    coord_meta = {
        "min_q": min_q,
        "max_q": max_q,
        "min_r": min_r,
        "max_r": max_r,
        "q_span": max(0, max_q - min_q),
        "r_span": max(0, max_r - min_r),
        "playable_hexes": playable_hexes,
    }
    return obs, coord_meta


def compute_hex_attribution(
    model: nn.Module,
    obs_tensor: torch.Tensor,
    action_index: int,
    coord_meta: dict[str, Any],
    steps: int = 15,
    device: str = "cpu",
) -> dict[str, Any]:
    """
    Computes Integrated Gradients for Heterogeneous features (IGNH) and Grad-CAM
    for the selected action_index on obs_tensor.
    """
    model.eval()
    obs_tensor = obs_tensor.to(device)
    if obs_tensor.dim() == 3:
        obs_tensor = obs_tensor.unsqueeze(0)

    num_channels = obs_tensor.shape[1]
    height = obs_tensor.shape[2]
    width = obs_tensor.shape[3]

    # 1. Build Heterogeneous Baseline (x0)
    # - Spatial coordinates (ch 19, 20) are preserved (delta = 0, no spurious positional bias)
    # - Playable hex mask (ch 12) is preserved
    # - Dynamic channels (units, threat, race, doctrine, hp) are zeroed out
    # - Terrain channels (cover, los, move_cost) are zeroed out (representing neutral open ground)
    x0 = torch.zeros_like(obs_tensor)
    if num_channels > 12:
        x0[:, 12, :, :] = obs_tensor[:, 12, :, :]  # map_playable
    if num_channels > 19:
        x0[:, 19, :, :] = obs_tensor[:, 19, :, :]  # q_coord_norm
    if num_channels > 20:
        x0[:, 20, :, :] = obs_tensor[:, 20, :, :]  # r_coord_norm

    # 2. Hook for Grad-CAM on representation tower (only active on gradients)
    activations: list[torch.Tensor] = []
    cam_gradients: list[torch.Tensor] = []

    def hook_forward(module, inp, outp):
        if outp.requires_grad:
            activations.append(outp)
            outp.register_hook(lambda g: cam_gradients.append(g))

    hook_handle = None
    target_cam_layer = None
    if hasattr(model, "representation_tower") and len(model.representation_tower) > 0:
        target_cam_layer = model.representation_tower[-1]
    elif hasattr(model, "representation_input"):
        target_cam_layer = model.representation_input

    if target_cam_layer is not None:
        hook_handle = target_cam_layer.register_forward_hook(hook_forward)

    # 3. Integrated Gradients across M steps
    accum_grad = torch.zeros_like(obs_tensor)
    delta_x = obs_tensor - x0

    score_target = 0.0
    score_baseline = 0.0

    steps = max(5, int(steps))
    for step_i in range(1, steps + 1):
        alpha = float(step_i) / float(steps)
        interp_x = x0 + alpha * delta_x
        interp_x = interp_x.clone().detach().requires_grad_(True)

        model.zero_grad()
        out = model.initial_inference(interp_x)
        policy_logits = out[1]
        score = policy_logits[0, action_index]

        if step_i == steps:
            score_target = float(score.item())
        score.backward(retain_graph=(step_i == steps and hook_handle is not None))

        if interp_x.grad is not None:
            accum_grad += interp_x.grad.detach()

    if hook_handle is not None:
        hook_handle.remove()
        hook_handle = None

    # Score at baseline
    with torch.no_grad():
        out_base = model.initial_inference(x0)
        score_baseline = float(out_base[1][0, action_index].item())

    # IG attribution tensor: (x - x0) * (1/M * sum(grads))
    ig_attribution = (delta_x * (accum_grad / float(steps))).squeeze(0)  # (C, H, W)

    # 4. Grad-CAM calculation
    gradcam_map = torch.zeros((height, width), dtype=torch.float32)
    if activations and cam_gradients:
        try:
            last_act = activations[-1]
            last_grad = cam_gradients[-1]
            weights = last_grad.mean(dim=(2, 3), keepdim=True)
            cam = torch.relu((weights * last_act).sum(dim=1, keepdim=True)).squeeze()
            if cam.max() > cam.min():
                gradcam_map = (cam - cam.min()) / (cam.max() - cam.min() + 1e-9)
            else:
                gradcam_map = cam
        except Exception as e:
            logger.debug("Grad-CAM calculation skipped: %s", e)

    if hook_handle is not None:
        hook_handle.remove()

    # 5. Hexagonal coordinate projection mapping
    min_q = coord_meta["min_q"]
    min_r = coord_meta["min_r"]
    q_span = coord_meta["q_span"]
    r_span = coord_meta["r_span"]
    playable_hexes = coord_meta["playable_hexes"]

    def to_xy(q: int, r: int) -> tuple[int, int]:
        if q_span <= (width - 1):
            x = int(q - min_q)
        else:
            x = int(round((float(q - min_q) / float(max(1, q_span))) * float(width - 1)))
        if r_span <= (height - 1):
            y = int(r - min_r)
        else:
            y = int(round((float(r - min_r) / float(max(1, r_span))) * float(height - 1)))
        return max(0, min(width - 1, x)), max(0, min(height - 1, y))

    # 6. Channel Attributions Breakdown
    channel_results: list[dict[str, Any]] = []
    total_abs_attr = float(ig_attribution.abs().sum().item())
    safe_denom = total_abs_attr if total_abs_attr > 1e-9 else 1.0

    group_scores: dict[str, float] = {g: 0.0 for g in CHANNEL_GROUPS.keys()}
    group_abs_scores: dict[str, float] = {g: 0.0 for g in CHANNEL_GROUPS.keys()}

    for c in range(num_channels):
        c_plane = ig_attribution[c]
        raw_val = float(c_plane.sum().item())
        abs_val = float(c_plane.abs().sum().item())
        grp = _resolve_channel_group(c)
        c_name = _channel_name(c)

        if grp in group_scores:
            group_scores[grp] += raw_val
            group_abs_scores[grp] += abs_val

        channel_results.append({
            "channel_index": c,
            "channel_name": c_name,
            "group": grp,
            "raw_attribution": round(raw_val, 5),
            "importance": round(abs_val, 5),
            "percentage": round((abs_val / safe_denom) * 100.0, 2),
            "direction": "support" if raw_val >= 0 else "oppose",
        })

    channel_results.sort(key=lambda x: x["importance"], reverse=True)

    group_attributions: dict[str, Any] = {}
    for g, abs_s in group_abs_scores.items():
        pct = round((abs_s / safe_denom) * 100.0, 2)
        group_attributions[g] = {
            "name": CHANNEL_GROUP_LABELS.get(g, g),
            "raw_score": round(group_scores[g], 5),
            "importance": round(abs_s, 5),
            "percentage": pct,
            "direction": "support" if group_scores[g] >= 0 else "oppose",
        }

    # 7. Spatial Hexagonal Heatmaps per Group
    # Spatial composite: sum of all channels on each hex cell
    composite_plane = ig_attribution.sum(dim=0).cpu().numpy()
    gradcam_np = gradcam_map.detach().cpu().numpy()

    # Precompute group planes
    group_planes: dict[str, Any] = {}
    for g, indices in CHANNEL_GROUPS.items():
        valid_indices = [idx for idx in indices if idx < num_channels]
        if valid_indices:
            group_planes[g] = ig_attribution[valid_indices].sum(dim=0).cpu().numpy()
        else:
            group_planes[g] = None

    spatial_heatmaps: dict[str, list[dict[str, Any]]] = {
        "composite": [],
        "gradcam": [],
    }
    for g in CHANNEL_GROUPS.keys():
        spatial_heatmaps[g] = []

    # Map each hex to its attribution
    for h in playable_hexes:
        hq, hr = int(h["q"]), int(h["r"])
        x, y = to_xy(hq, hr)

        c_val = float(composite_plane[y, x])
        g_val = float(gradcam_np[y, x])
        spatial_heatmaps["composite"].append({"q": hq, "r": hr, "value": round(c_val, 4)})
        spatial_heatmaps["gradcam"].append({"q": hq, "r": hr, "value": round(g_val, 4)})

        for g, plane in group_planes.items():
            if plane is not None:
                val = float(plane[y, x])
                spatial_heatmaps[g].append({"q": hq, "r": hr, "value": round(val, 4)})

    # 8. Top Influential Hexes Identification
    hex_influence: list[dict[str, Any]] = []
    for h in playable_hexes:
        hq, hr = int(h["q"]), int(h["r"])
        x, y = to_xy(hq, hr)
        # Find dominant channel at this (x, y)
        cell_channels = ig_attribution[:, y, x]
        dom_idx = int(cell_channels.abs().argmax().item())
        dom_val = float(cell_channels[dom_idx].item())
        dom_name = _channel_name(dom_idx)
        dom_group = _resolve_channel_group(dom_idx)
        comp_val = float(composite_plane[y, x])

        impact_desc = "Favorable pull towards target action" if comp_val >= 0 else "Deterrent / risk penalty"
        hex_influence.append({
            "q": hq,
            "r": hr,
            "score": round(comp_val, 4),
            "abs_score": round(abs(comp_val), 4),
            "dominant_channel": dom_name,
            "dominant_group": CHANNEL_GROUP_LABELS.get(dom_group, dom_group),
            "dominant_value": round(dom_val, 4),
            "impact": "favorable" if comp_val >= 0 else "unfavorable",
            "description": f"Hex ({hq}, {hr}): {dom_name} ({dom_val:+.3f}) - {impact_desc}",
        })

    hex_influence.sort(key=lambda x: x["abs_score"], reverse=True)
    top_influential_hexes = hex_influence[:8]

    # 9. Natural Language Tactical Rationale Generator
    top_groups = sorted(group_attributions.items(), key=lambda item: item[1]["importance"], reverse=True)
    dominant_g = top_groups[0][1] if top_groups else {"name": "Tactical Posture", "percentage": 0.0, "direction": "support"}
    secondary_g = top_groups[1][1] if len(top_groups) > 1 else None

    rationale_parts = [
        f"Selected action influenced primarily by {dominant_g['name']} ({dominant_g['percentage']}%, {dominant_g['direction']})"
    ]
    if secondary_g and secondary_g["percentage"] > 10.0:
        rationale_parts.append(
            f", modulated by {secondary_g['name']} ({secondary_g['percentage']}%, {secondary_g['direction']})"
        )
    rationale_parts.append(f". Completeness score delta: {score_target - score_baseline:+.3f}.")
    tactical_rationale = "".join(rationale_parts)

    return {
        "score_target": round(score_target, 4),
        "score_baseline": round(score_baseline, 4),
        "score_delta": round(score_target - score_baseline, 4),
        "total_abs_attribution": round(total_abs_attr, 4),
        "group_attributions": group_attributions,
        "channel_attributions": channel_results,
        "spatial_heatmaps": spatial_heatmaps,
        "top_influential_hexes": top_influential_hexes,
        "tactical_rationale": tactical_rationale,
    }


def _resolve_run_dir(repo_root: Path, eval_source_path: str) -> Optional[Path]:
    from mlops.reporting.replay_api import resolve_replay_path

    resolved_run_dir = None
    rp = resolve_replay_path(eval_source_path=eval_source_path)
    if rp is not None and rp.exists():
        # Usually runs_curriculum/<run_id>/xai/... -> run_id is parent of xai
        p = rp.parent
        while p != p.parent:
            if (p / "checkpoints").exists() or (p / "run_manifest.json").exists():
                return p
            p = p.parent

    # Check if eval_source_path itself points to a run directory
    cand = (repo_root / eval_source_path).resolve()
    if (cand / "checkpoints").exists() or (cand / "run_manifest.json").exists():
        return cand
    elif (cand.parent / "checkpoints").exists():
        return cand.parent

    # Search in runs_curriculum for latest run with checkpoints
    runs_dir = repo_root / "runs_curriculum"
    if runs_dir.exists():
        runs_with_ckpts = [
            r for r in runs_dir.iterdir()
            if r.is_dir() and (r / "checkpoints" / "final.pt").exists()
        ]
        if runs_with_ckpts:
            runs_with_ckpts.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return runs_with_ckpts[0]

    # Search in runs
    runs_dir_base = repo_root / "runs"
    if runs_dir_base.exists():
        runs_with_ckpts = [
            r for r in runs_dir_base.iterdir()
            if r.is_dir() and (r / "checkpoints" / "final.pt").exists()
        ]
        if runs_with_ckpts:
            runs_with_ckpts.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return runs_with_ckpts[0]

    return None


def explain_replay_step(
    repo_root: Path,
    eval_source_path: str,
    episode_id: str,
    step_index: int,
    action_id: str | None = None,
    steps: int = 15,
    load_scenario_overlay_fn: Optional[Callable[[Path, str], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Main entrypoint: loads the replay transition step, finds model weights,
    computes IGNH & Grad-CAM, and returns a comprehensive explainability payload.
    """
    t0 = time.perf_counter()

    # 1. Resolve replay file and step data
    from mlops.reporting.replay_api import build_v2_replay_steps_payload

    steps_payload = build_v2_replay_steps_payload(
        eval_source_path=eval_source_path,
        episode_id=episode_id,
        from_step=step_index,
        to_step=step_index,
        repo_root=repo_root,
        load_scenario_overlay=load_scenario_overlay_fn,
    )
    step_list = steps_payload.get("steps", [])
    if not step_list:
        return {
            "ok": False,
            "error": f"Step index {step_index} not found in episode {episode_id}",
            "eval_source_path": eval_source_path,
        }

    step_data = step_list[0]
    scenario_id = str(step_data.get("scenario_id", steps_payload.get("scenario_id", "")) or "")
    scenario_overlay = steps_payload.get("scenario_overlay")
    if not scenario_overlay and load_scenario_overlay_fn is not None and scenario_id:
        scenario_overlay = load_scenario_overlay_fn(repo_root, scenario_id)

    # 2. Reconstruct Observation and Coordinate Metadata
    obs, coord_meta = build_obs_from_step_data(step_data, scenario_overlay)

    # 3. Locate Model Checkpoint
    resolved_run_dir = _resolve_run_dir(repo_root, eval_source_path)

    if resolved_run_dir is None:
        return {
            "ok": False,
            "error": "No trained model checkpoint found for explainability attribution",
            "eval_source_path": eval_source_path,
        }

    # 4. Load Model and Action Mapping
    model = get_cached_model(resolved_run_dir)
    obs_channels = getattr(model, "observation_channels", DEFAULT_OBS_CHANNELS)
    obs_h = getattr(model, "observation_height", DEFAULT_OBS_HEIGHT)
    obs_w = getattr(model, "observation_width", DEFAULT_OBS_WIDTH)
    action_dim = getattr(model, "action_dim", 32)

    # Determine target action
    target_action_id = action_id or str(
        step_data.get("action_id", step_data.get("mcts_chosen_action", step_data.get("requested_action_id", "")))
        or ""
    )
    if not target_action_id:
        target_action_id = "WAIT"

    action_idx = _action_id_to_index(target_action_id, action_dim)

    # 5. Build Observation Tensor
    obs_tensor = observation_to_tensor(obs, channels=obs_channels, height=obs_h, width=obs_w)

    # 6. Execute IGNH & Grad-CAM
    attr_result = compute_hex_attribution(
        model=model,
        obs_tensor=obs_tensor,
        action_index=action_idx,
        coord_meta=coord_meta,
        steps=steps,
    )

    # 7. Extract Auxiliary Tactical Heads directly from model initial inference
    tactical_heads = _extract_auxiliary_heads(model, obs_tensor, coord_meta)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "ok": True,
        "run_dir": str(resolved_run_dir.name),
        "scenario_id": scenario_id,
        "episode_id": episode_id,
        "step_index": int(step_index),
        "turn": int(obs.turn),
        "to_play": str(obs.to_play),
        "unit_id": str(step_data.get("unit_id", "")),
        "action_id": target_action_id,
        "action_kind": str(step_data.get("action_kind", target_action_id.split(":")[0])),
        "action_index": action_idx,
        "action_dim": action_dim,
        "observation_channels": obs_channels,
        "execution_time_ms": round(elapsed_ms, 2),
        "tactical_heads": tactical_heads,
        **attr_result,
    }


def _extract_auxiliary_heads(
    model: nn.Module | None,
    obs_tensor: torch.Tensor,
    coord_meta: dict[str, Any],
) -> dict[str, Any]:
    width = obs_tensor.shape[2] if obs_tensor.dim() >= 3 else DEFAULT_OBS_WIDTH
    height = obs_tensor.shape[1] if obs_tensor.dim() >= 3 else DEFAULT_OBS_HEIGHT
    min_q = coord_meta["min_q"]
    min_r = coord_meta["min_r"]
    q_span = coord_meta["q_span"]
    r_span = coord_meta["r_span"]
    playable_hexes = coord_meta["playable_hexes"]

    def to_xy(q: int, r: int) -> tuple[int, int]:
        if q_span <= (width - 1):
            x = int(q - min_q)
        else:
            x = int(round((float(q - min_q) / float(max(1, q_span))) * float(width - 1)))
        if r_span <= (height - 1):
            y = int(r - min_r)
        else:
            y = int(round((float(r - min_r) / float(max(1, r_span))) * float(height - 1)))
        return max(0, min(width - 1, x)), max(0, min(height - 1, y))

    ch7_plane = obs_tensor[7].cpu().numpy() if obs_tensor.shape[0] > 7 else None
    gt_threat_hexes: list[dict[str, Any]] = []
    if ch7_plane is not None:
        for h in playable_hexes:
            hq, hr = int(h["q"]), int(h["r"])
            x, y = to_xy(hq, hr)
            val = float(ch7_plane[y, x])
            gt_threat_hexes.append({"q": hq, "r": hr, "value": round(val, 4)})

    max_gt = max((h["value"] for h in gt_threat_hexes), default=0.0)
    mean_gt = round(sum(h["value"] for h in gt_threat_hexes) / max(1, len(gt_threat_hexes)), 4) if gt_threat_hexes else 0.0

    heads: dict[str, Any] = {
        "ground_truth_threat": gt_threat_hexes,
        "threat_map": gt_threat_hexes,
        "threat_summary": {
            "max_threat": max_gt,
            "mean_threat": mean_gt,
            "high_risk_hexes": len([h for h in gt_threat_hexes if h["value"] >= 0.5]),
            "source": "observation_channel_7",
        },
        "morale": {
            "suppression_risk": 0.0,
            "status": "STABLE",
            "source": "fallback",
        },
        "attrition": {
            "predicted_friendly_casualties": 0.0,
            "predicted_enemy_casualties": 0.0,
            "exchange_ratio": 1.0,
            "source": "fallback",
        },
    }

    if model is None:
        return heads

    try:
        with torch.no_grad():
            inp = obs_tensor.unsqueeze(0)
            initial_out = model.initial_inference(inp, return_aux=True)
            aux = initial_out[4] if len(initial_out) > 4 and isinstance(initial_out[4], dict) else {}

            tmp = aux.get("threat_map_pred")
            if isinstance(tmp, torch.Tensor) and tmp.numel() > 0:
                sig_threat = torch.sigmoid(tmp).squeeze().cpu().numpy()
                pred_threat_hexes: list[dict[str, Any]] = []
                for h in playable_hexes:
                    hq, hr = int(h["q"]), int(h["r"])
                    x, y = to_xy(hq, hr)
                    val = float(sig_threat[y, x]) if sig_threat.ndim >= 2 else float(sig_threat)
                    pred_threat_hexes.append({"q": hq, "r": hr, "value": round(val, 4)})
                pred_threat_hexes.sort(key=lambda item: item["value"], reverse=True)
                heads["threat_map"] = pred_threat_hexes
                max_t = max((item["value"] for item in pred_threat_hexes), default=0.0)
                mean_t = round(sum(item["value"] for item in pred_threat_hexes) / max(1, len(pred_threat_hexes)), 4) if pred_threat_hexes else 0.0
                heads["threat_summary"] = {
                    "max_threat": max_t,
                    "mean_threat": mean_t,
                    "high_risk_hexes": len([item for item in pred_threat_hexes if item["value"] >= 0.5]),
                    "source": "neural_head_prediction",
                }

            mor = aux.get("morale_pred")
            if isinstance(mor, torch.Tensor) and mor.numel() > 0:
                mor_flat = mor.squeeze()
                if mor_flat.numel() == 1:
                    mor_val = float(torch.sigmoid(mor_flat).item())
                    heads["morale"] = {
                        "suppression_risk": round(mor_val, 4),
                        "status": "DANGER" if mor_val >= 0.60 else ("ELEVATED" if mor_val >= 0.30 else "STABLE"),
                        "source": "neural_head_prediction",
                    }
                else:
                    mor_probs = torch.softmax(mor_flat, dim=-1).cpu().tolist()
                    # Class 0: Normal / Fresh, Classes > 0: Suppressed / Pinned / Broken
                    suppression_risk = float(sum(mor_probs[1:])) if len(mor_probs) > 1 else 0.0
                    heads["morale"] = {
                        "suppression_risk": round(suppression_risk, 4),
                        "morale_distribution": [round(float(p), 3) for p in mor_probs],
                        "status": "DANGER" if suppression_risk >= 0.60 else ("ELEVATED" if suppression_risk >= 0.30 else "STABLE"),
                        "source": "neural_head_prediction",
                    }

            att = aux.get("attrition_pred")
            if isinstance(att, torch.Tensor) and att.numel() > 0:
                att_flat = att.squeeze().cpu().tolist()
                if not isinstance(att_flat, list):
                    att_flat = [float(att_flat)]
                fc = round(float(att_flat[0]), 2) if len(att_flat) > 0 else 0.0
                ec = round(float(att_flat[1]), 2) if len(att_flat) > 1 else 0.0
                heads["attrition"] = {
                    "predicted_friendly_casualties": fc,
                    "predicted_enemy_casualties": ec,
                    "exchange_ratio": round(ec / max(0.1, fc), 2),
                    "source": "neural_head_prediction",
                }

            fop = aux.get("final_ownership_pred")
            if isinstance(fop, torch.Tensor) and fop.numel() > 0:
                fop_np = torch.tanh(fop).squeeze().cpu().numpy()
                fo_hexes: list[dict[str, Any]] = []
                for h in playable_hexes:
                    hq, hr = int(h["q"]), int(h["r"])
                    x, y = to_xy(hq, hr)
                    val = float(fop_np[y, x]) if fop_np.ndim >= 2 else float(fop_np)
                    fo_hexes.append({"q": hq, "r": hr, "value": round(val, 4)})
                heads["final_ownership"] = fo_hexes
    except Exception as e:
        logger.warning("Error evaluating auxiliary neural heads: %s", e)

    return heads


def compute_step_tactical_heads(
    repo_root: Path,
    eval_source_path: str,
    episode_id: str,
    step_index: int,
    load_scenario_overlay_fn: Optional[Callable[[Path, str], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Fast extraction of step-level tactical heads (threat_map, attrition, morale, final_ownership).
    """
    t0 = time.perf_counter()
    from mlops.reporting.replay_api import build_v2_replay_steps_payload

    steps_payload = build_v2_replay_steps_payload(
        eval_source_path=eval_source_path,
        episode_id=episode_id,
        from_step=step_index,
        to_step=step_index,
        repo_root=repo_root,
        load_scenario_overlay=load_scenario_overlay_fn,
    )
    step_list = steps_payload.get("steps", [])
    if not step_list:
        return {
            "ok": False,
            "error": f"Step index {step_index} not found in episode {episode_id}",
        }

    step_data = step_list[0]
    scenario_id = str(step_data.get("scenario_id", steps_payload.get("scenario_id", "")) or "")
    scenario_overlay = steps_payload.get("scenario_overlay")
    if not scenario_overlay and load_scenario_overlay_fn is not None and scenario_id:
        scenario_overlay = load_scenario_overlay_fn(repo_root, scenario_id)

    obs, coord_meta = build_obs_from_step_data(step_data, scenario_overlay)
    resolved_run_dir = _resolve_run_dir(repo_root, eval_source_path)

    obs_channels = DEFAULT_OBS_CHANNELS
    obs_h = DEFAULT_OBS_HEIGHT
    obs_w = DEFAULT_OBS_WIDTH
    model = None
    if resolved_run_dir is not None:
        try:
            model = get_cached_model(resolved_run_dir)
            obs_channels = getattr(model, "observation_channels", DEFAULT_OBS_CHANNELS)
            obs_h = getattr(model, "observation_height", DEFAULT_OBS_HEIGHT)
            obs_w = getattr(model, "observation_width", DEFAULT_OBS_WIDTH)
        except Exception as e:
            logger.warning("Could not load model for tactical heads: %s", e)
            model = None

    obs_tensor = observation_to_tensor(obs, channels=obs_channels, height=obs_h, width=obs_w)
    tactical_heads = _extract_auxiliary_heads(model, obs_tensor, coord_meta)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "ok": True,
        "run_dir": str(resolved_run_dir.name) if resolved_run_dir else None,
        "scenario_id": scenario_id,
        "episode_id": episode_id,
        "step_index": int(step_index),
        "turn": int(obs.turn),
        "to_play": str(obs.to_play),
        "tactical_heads": tactical_heads,
        "execution_time_ms": round(elapsed_ms, 2),
    }


def compute_replay_topography_profile(
    repo_root: Path,
    scenario_id: str = "",
    eval_source_path: str = "",
    episode_id: str = "episode_0",
    load_scenario_overlay_fn: Optional[Callable[[Path, str], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Computes or retrieves Turn-0 IPB Topography Profile for replay visualization (Roadmap Task 4.3).
    """
    t0 = time.perf_counter()
    from assault_model.map.topography_analyzer import analyze_battlefield_topography

    scen_id = str(scenario_id or "").strip()
    scenario_overlay = None

    if not scen_id and eval_source_path:
        from mlops.reporting.replay_api import build_v2_replay_steps_payload
        try:
            steps_payload = build_v2_replay_steps_payload(
                eval_source_path=eval_source_path,
                episode_id=episode_id,
                from_step=0,
                to_step=0,
                repo_root=repo_root,
                load_scenario_overlay=load_scenario_overlay_fn,
            )
            scen_id = str(steps_payload.get("scenario_id", "") or "")
            scenario_overlay = steps_payload.get("scenario_overlay")
        except Exception:
            pass

    if not scenario_overlay and load_scenario_overlay_fn is not None and scen_id:
        scenario_overlay = load_scenario_overlay_fn(repo_root, scen_id)

    if not scenario_overlay:
        return {
            "ok": False,
            "error": f"Scenario overlay not found for '{scen_id}'",
        }

    hex_data = list(
        scenario_overlay.get("map_cells")
        or scenario_overlay.get("playable_hexes")
        or scenario_overlay.get("hexes")
        or []
    )
    vp_hexes = list(scenario_overlay.get("vp_hexes", []) or [])

    profile = analyze_battlefield_topography(
        hex_data=hex_data,
        vp_hexes=vp_hexes,
        scenario_id=scen_id,
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "ok": True,
        "scenario_id": scen_id,
        "elapsed_ms": round(elapsed_ms, 2),
        "topography": profile.to_dict(),
    }

