from __future__ import annotations

from typing import Any, Dict, List, Optional
import torch
import torch.nn.functional as F

from agents.efficientzero_v2.core.selfplay import (
    _action_id_to_index,
    _priors_and_values,
    _observation_to_vector,
)
from agents.efficientzero_v2.core.observation import observation_to_tensor


def observation_to_vector(obs) -> list[float]:
    return _observation_to_vector(obs)


def value_signs_from_to_play(obs, legal_actions: List[str]) -> dict[str, int]:
    root_side = str(getattr(obs, "to_play", "") or "")
    side_by_unit: dict[str, str] = {}
    for u in list(getattr(obs, "units", []) or []):
        uid = str(u.get("unit_id", "") if isinstance(u, dict) else getattr(u, "unit_id", ""))
        uside = str(u.get("side", "") if isinstance(u, dict) else getattr(u, "side", ""))
        if uid and uside:
            side_by_unit[uid] = uside

    signs = {}
    for action_id in legal_actions:
        parts = str(action_id).split(":")
        unit_id = parts[1] if len(parts) > 1 else ""
        action_side = side_by_unit.get(unit_id, root_side)
        signs[action_id] = 1 if action_side == root_side else -1
    return signs


def priors_and_values_from_model(
    *,
    model,
    observation,
    legal_actions: List[str],
    action_dim: int,
    unroll_steps: int = 1,
    discount: float = 0.997,
    return_root_cache: bool = False,
):
    priors, values, xai = _priors_and_values(
        model=model,
        obs_encoded=observation,
        legal_actions=legal_actions,
        action_dim=action_dim,
    )
    if not return_root_cache:
        return priors, values

    # Build root_cache compatible with xai inspection
    root_cache: dict[str, Any] = {}
    if model is not None:
        model_device = next(model.parameters()).device
        with torch.inference_mode():
            if str(getattr(model, "encoder_type", "mlp")) == "cnn":
                obs_tensor = observation.unsqueeze(0).to(model_device)
            else:
                obs_tensor = torch.tensor([observation], dtype=torch.float32, device=model_device)
            try:
                inf_res = model.initial_inference(obs_tensor, return_aux=True)
                if isinstance(inf_res, tuple) and len(inf_res) >= 5:
                    hidden, policy_logits, value_root, _, aux_dict = inf_res
                    root_cache = {
                        "hidden": hidden.detach(),
                        "policy_logits": policy_logits[0].detach(),
                        "value_root": value_root.detach(),
                        "aux": dict(aux_dict or {}),
                    }
                elif isinstance(inf_res, tuple) and len(inf_res) >= 4:
                    hidden, policy_logits, value_root, _ = inf_res[:4]
                    root_cache = {
                        "hidden": hidden.detach(),
                        "policy_logits": policy_logits[0].detach(),
                        "value_root": value_root.detach(),
                        "aux": {},
                    }
            except Exception:
                pass
    return priors, values, root_cache


def xai_root_signals_from_root_cache(
    *,
    root_cache: dict,
    legal_actions: List[str],
    action_dim: int,
    topk: int = 5,
    index_cache: dict[str, int] | None = None,
) -> dict[str, Any]:
    hidden = (dict(root_cache or {})).get("hidden", None)
    logits = (dict(root_cache or {})).get("policy_logits", None)
    value_root = (dict(root_cache or {})).get("value_root", None)
    aux = dict((dict(root_cache or {})).get("aux", {}) or {})

    tactical_signals: dict[str, Any] = {}
    if aux:
        threat_pred = aux.get("threat_map_pred")
        if threat_pred is not None:
            t_flat = threat_pred.detach().cpu().float().view(-1)
            if (t_flat < 0.0).any() or (t_flat > 1.0).any():
                t_probs = torch.sigmoid(t_flat)
            else:
                t_probs = t_flat
            tactical_signals["threat_coverage_ratio"] = float((t_probs >= 0.5).float().mean().item())
            tactical_signals["threat_max"] = float(t_probs.max().item())
            tactical_signals["threat_mean"] = float(t_probs.mean().item())

        attr_pred = aux.get("attrition_pred")
        if attr_pred is not None:
            a_flat = attr_pred.detach().cpu().float().view(-1)
            f_cas = max(0.0, float(a_flat[0].item())) if len(a_flat) >= 1 else 0.0
            e_cas = max(0.0, float(a_flat[1].item())) if len(a_flat) >= 2 else 0.0
            ratio = float(e_cas / max(1e-4, f_cas))
            tactical_signals["predicted_friendly_casualties"] = f_cas
            tactical_signals["predicted_enemy_casualties"] = e_cas
            tactical_signals["predicted_exchange_ratio"] = ratio

        morale_pred = aux.get("morale_pred")
        if morale_pred is not None:
            m_flat = morale_pred.detach().cpu().float().view(-1)
            m_probs = torch.softmax(m_flat, dim=-1)
            risk = float(sum(m_probs[i].item() * (i / max(1, len(m_probs) - 1)) for i in range(len(m_probs))))
            tactical_signals["suppression_risk_score"] = risk

        obj_pred = aux.get("objective_logit")
        if obj_pred is not None:
            tactical_signals["objective_pred_prob"] = float(torch.sigmoid(obj_pred.detach().cpu().float()).item())

    if hidden is None or logits is None or value_root is None:
        return {
            "policy_top_actions": [],
            "policy_top_probs": [],
            "latent_top_indices": [],
            "latent_top_values": [],
            "latent_l2_norm": None,
            "predicted_value_root": None,
            **tactical_signals,
        }
    hidden_vec = hidden[0].detach()
    hidden_flat = torch.flatten(hidden_vec)
    legal_indices = [_action_id_to_index(a, action_dim) for a in legal_actions]
    if legal_indices:
        legal_idx_t = torch.tensor(legal_indices, dtype=torch.long, device=logits.device)
        legal_logits = torch.index_select(logits, dim=0, index=legal_idx_t).to(torch.float32)
        legal_probs_t = torch.softmax(legal_logits, dim=0)
        kk = min(max(1, int(topk)), int(legal_probs_t.numel()))
        top_p, top_i = torch.topk(legal_probs_t, k=kk)
        ranked = [
            (str(legal_actions[int(i)]), float(p))
            for i, p in zip(top_i.detach().cpu().tolist(), top_p.detach().cpu().tolist())
        ]
        policy_top_actions = [str(a) for a, _ in ranked]
        policy_top_probs = [float(p) for _, p in ranked]
    else:
        policy_top_actions = []
        policy_top_probs = []
    k = min(max(1, int(topk)), int(hidden_flat.numel()))
    top_vals, top_idx = torch.topk(hidden_flat.abs(), k=k)
    latent_top_indices = [int(i) for i in top_idx.detach().cpu().tolist()]
    latent_top_values = [float(v) for v in top_vals.detach().cpu().tolist()]
    latent_l2_norm = float(torch.linalg.vector_norm(hidden_flat, ord=2).item())
    predicted_value_root = float(value_root[0, 0].item())
    return {
        "policy_top_actions": policy_top_actions,
        "policy_top_probs": policy_top_probs,
        "latent_top_indices": latent_top_indices,
        "latent_top_values": latent_top_values,
        "latent_l2_norm": latent_l2_norm,
        "predicted_value_root": predicted_value_root,
        **tactical_signals,
    }


def xai_root_signals_from_model(
    model,
    observation,
    legal_actions: List[str],
    action_dim: int,
    topk: int = 5,
    index_cache: dict[str, int] | None = None,
):
    model_device = next(model.parameters()).device
    with torch.inference_mode():
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_tensor = observation.unsqueeze(0).to(model_device)
        else:
            obs_tensor = torch.tensor([observation], dtype=torch.float32, device=model_device)
        aux_dict = {}
        try:
            inf_res = model.initial_inference(obs_tensor, return_aux=True)
            if isinstance(inf_res, tuple) and len(inf_res) >= 5:
                hidden, policy_logits, value_root, _, aux_dict = inf_res
                aux_dict = dict(aux_dict or {})
            elif isinstance(inf_res, tuple) and len(inf_res) >= 4:
                hidden, policy_logits, value_root, _ = inf_res[:4]
            else:
                hidden, policy_logits, value_root, _ = model.initial_inference(obs_tensor)
        except TypeError:
            hidden, policy_logits, value_root, _ = model.initial_inference(obs_tensor)
        cache = {
            "hidden": hidden.detach(),
            "policy_logits": policy_logits[0].detach(),
            "value_root": value_root.detach(),
            "aux": aux_dict,
        }
    return xai_root_signals_from_root_cache(
        root_cache=cache,
        legal_actions=legal_actions,
        action_dim=action_dim,
        topk=topk,
        index_cache=index_cache,
    )


def xai_dynamics_signals_for_action_from_hidden(
    *,
    model,
    hidden,
    chosen_action_id: str,
    action_dim: int,
    index_cache: dict[str, int] | None = None,
):
    model_device = next(model.parameters()).device
    if hidden is None:
        return {
            "dynamics_pred_reward": None,
            "dynamics_next_latent_l2": None,
            "dynamics_delta_l2": None,
        }
    with torch.inference_mode():
        hidden_t = hidden.to(model_device)
        hidden_vec = hidden_t[0].detach()
        action_idx = int(_action_id_to_index(chosen_action_id, action_dim))
        action_onehot = F.one_hot(
            torch.tensor([action_idx], dtype=torch.long, device=model_device),
            num_classes=int(action_dim),
        ).to(torch.float32)
        next_hidden, _, _, pred_reward = model.recurrent_inference(hidden_t, action_onehot)
        next_hidden_vec = next_hidden[0].detach()
        dynamics_pred_reward = float(pred_reward[0, 0].item())
        dynamics_next_latent_l2 = float(torch.linalg.vector_norm(next_hidden_vec, ord=2).item())
        dynamics_delta_l2 = float(torch.linalg.vector_norm(next_hidden_vec - hidden_vec, ord=2).item())
    return {
        "dynamics_pred_reward": dynamics_pred_reward,
        "dynamics_next_latent_l2": dynamics_next_latent_l2,
        "dynamics_delta_l2": dynamics_delta_l2,
    }


def xai_dynamics_signals_for_action(
    model,
    observation,
    chosen_action_id: str,
    action_dim: int,
    index_cache: dict[str, int] | None = None,
):
    model_device = next(model.parameters()).device
    with torch.inference_mode():
        if str(getattr(model, "encoder_type", "mlp")) == "cnn":
            obs_tensor = observation.unsqueeze(0).to(model_device)
        else:
            obs_tensor = torch.tensor([observation], dtype=torch.float32, device=model_device)
        hidden, _, _, _ = model.initial_inference(obs_tensor)
    return xai_dynamics_signals_for_action_from_hidden(
        model=model,
        hidden=hidden,
        chosen_action_id=chosen_action_id,
        action_dim=action_dim,
        index_cache=index_cache,
    )
