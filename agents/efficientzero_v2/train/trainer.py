from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable, Dict, List

import torch
import torch.nn.functional as F

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.replay import ReplaySample
from agents.efficientzero_v2.train.trainer_base import EfficientZeroV2BaseTrainer, TrainMetrics
from agents.efficientzero_v2.core.support import cross_entropy_two_hot
from agents.efficientzero_v2.train.loss_balancer import pcgrad_backward, AdaptiveLossScaler


@dataclass
class EfficientTrainMetrics(TrainMetrics):
    consistency_loss: float = 0.0
    reanalysis_coverage: float = 0.0
    reanalysis_target_drift: float = 0.0
    reanalysis_policy_drift: float = 0.0
    consistency_pairs: float = 0.0
    aux_objective_loss: float = 0.0
    aux_intent_loss: float = 0.0
    aux_multi_vp_loss: float = 0.0
    aux_threat_loss: float = 0.0
    aux_attrition_loss: float = 0.0
    aux_morale_loss: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        d = super().to_dict()
        d["consistency_loss"] = float(self.consistency_loss)
        d["reanalysis_coverage"] = float(self.reanalysis_coverage)
        d["reanalysis_target_drift"] = float(self.reanalysis_target_drift)
        d["reanalysis_policy_drift"] = float(self.reanalysis_policy_drift)
        d["consistency_pairs"] = float(self.consistency_pairs)
        d["aux_objective_loss"] = float(self.aux_objective_loss)
        d["aux_intent_loss"] = float(self.aux_intent_loss)
        d["aux_multi_vp_loss"] = float(self.aux_multi_vp_loss)
        d["aux_threat_loss"] = float(self.aux_threat_loss)
        d["aux_attrition_loss"] = float(self.aux_attrition_loss)
        d["aux_morale_loss"] = float(self.aux_morale_loss)
        return d


class EfficientZeroV2Trainer(EfficientZeroV2BaseTrainer):
    """EfficientZero v2 trainer with reanalysis + K-step consistency."""

    def __init__(
        self,
        model: EfficientZeroV2Network,
        lr: float = 1e-3,
        device: str = "cpu",
        objective_loss_weight: float = 0.0,
        objective_target_mode: str = "progress",
        objective_pos_weight: float = 1.0,
        objective_opportunity_max_dist: float = 2.0,
        objective_progress_positive_threshold: float = 0.0,
        consistency_loss_weight: float = 0.0,
        consistency_unroll_steps: int = 1,
        reanalysis_ratio: float = 0.0,
        reanalysis_value_mix: float = 0.5,
        reanalysis_policy_mix: float = 0.3,
        value_bootstrap_steps: int = 3,
        value_bootstrap_discount: float = 0.997,
        amp_enabled: bool = True,
        amp_dtype: str = "auto",
        aux_objective_enabled: bool = False,
        aux_objective_loss_weight: float = 0.0,
        aux_intent_loss_weight: float = 0.5,
        aux_multi_vp_loss_weight: float = 0.5,
        aux_multi_vp_feature_dim: int = 0,
        aux_threat_loss_weight: float = 0.2,
        aux_attrition_loss_weight: float = 0.2,
        aux_morale_loss_weight: float = 0.2,
        compute_grad_norm: bool = True,
        progress_callback: Callable[[str], None] | None = None,
        gradient_balance_mode: str = "none",
    ):
        super().__init__(
            model=model,
            lr=lr,
            device=device,
            objective_loss_weight=objective_loss_weight,
            objective_target_mode=objective_target_mode,
            objective_pos_weight=objective_pos_weight,
            objective_opportunity_max_dist=objective_opportunity_max_dist,
            objective_progress_positive_threshold=objective_progress_positive_threshold,
        )
        self.consistency_loss_weight = float(max(0.0, consistency_loss_weight))
        self.consistency_unroll_steps = int(max(1, consistency_unroll_steps))
        self.reanalysis_ratio = float(max(0.0, min(1.0, reanalysis_ratio)))
        self.reanalysis_value_mix = float(max(0.0, min(1.0, reanalysis_value_mix)))
        self.reanalysis_policy_mix = float(max(0.0, min(1.0, reanalysis_policy_mix)))
        self.value_bootstrap_steps = int(max(1, value_bootstrap_steps))
        self.value_bootstrap_discount = float(max(0.0, min(1.0, value_bootstrap_discount)))
        self.amp_enabled = bool(amp_enabled) and str(self.device) == "cuda"
        amp_dtype_norm = str(amp_dtype or "auto").strip().lower()
        if amp_dtype_norm not in {"auto", "fp16", "bf16"}:
            amp_dtype_norm = "auto"
        if amp_dtype_norm == "fp16":
            self._amp_dtype = torch.float16
        elif amp_dtype_norm == "bf16":
            self._amp_dtype = torch.bfloat16
        else:
            bf16_ok = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
            self._amp_dtype = torch.bfloat16 if bf16_ok else torch.float16
        self._scaler = torch.amp.GradScaler(
            "cuda",
            enabled=self.amp_enabled and self._amp_dtype == torch.float16,
        )
        self.aux_objective_enabled = bool(aux_objective_enabled)
        self.aux_objective_loss_weight = float(max(0.0, aux_objective_loss_weight))
        self.aux_intent_loss_weight = float(max(0.0, aux_intent_loss_weight))
        self.aux_multi_vp_loss_weight = float(max(0.0, aux_multi_vp_loss_weight))
        self.aux_multi_vp_feature_dim = int(max(0, aux_multi_vp_feature_dim))
        self.aux_threat_loss_weight = float(max(0.0, aux_threat_loss_weight))
        self.aux_attrition_loss_weight = float(max(0.0, aux_attrition_loss_weight))
        self.aux_morale_loss_weight = float(max(0.0, aux_morale_loss_weight))
        self.compute_grad_norm = bool(compute_grad_norm)
        self._progress_callback = progress_callback
        self.gradient_balance_mode = str(gradient_balance_mode or "none").lower().strip()
        self.adaptive_scaler = (
            AdaptiveLossScaler() if self.gradient_balance_mode == "adaptive" else None
        )

    def _progress(self, message: str) -> None:
        cb = self._progress_callback
        if cb is None:
            return
        try:
            cb(str(message))
        except Exception:
            return

    def _autocast_ctx(self):
        if not self.amp_enabled:
            return nullcontext()
        return torch.autocast(device_type="cuda", dtype=self._amp_dtype)

    def _resolve_ez_model(self):
        model = self.model
        if isinstance(model, EfficientZeroV2Network):
            return model
        # torch.compile wraps nn.Module and keeps original module at _orig_mod.
        inner = getattr(model, "_orig_mod", None)
        if isinstance(inner, EfficientZeroV2Network):
            return inner
        return None

    def train_batch(self, batch: List[ReplaySample]) -> EfficientTrainMetrics:
        self._progress("start")
        if not batch:
            return EfficientTrainMetrics(
                loss=0.0,
                policy_loss=0.0,
                value_loss=0.0,
                reward_loss=0.0,
                objective_loss=0.0,
                grad_norm=0.0,
                consistency_loss=0.0,
                reanalysis_coverage=0.0,
                reanalysis_target_drift=0.0,
                reanalysis_policy_drift=0.0,
                consistency_pairs=0.0,
                aux_objective_loss=0.0,
                aux_intent_loss=0.0,
                aux_multi_vp_loss=0.0,
            )

        obs = torch.stack(
            [
                s.observation.detach().to(torch.float32)
                if isinstance(s.observation, torch.Tensor)
                else torch.tensor(s.observation, dtype=torch.float32)
                for s in batch
            ],
            dim=0,
        ).to(self.device, non_blocking=True)
        self._progress("batch_tensors_ready")
        policy_target = torch.tensor([s.policy_target for s in batch], dtype=torch.float32, device=self.device)
        value_target = torch.tensor([[s.value_target] for s in batch], dtype=torch.float32, device=self.device)
        reward_target = torch.tensor([[s.reward_target] for s in batch], dtype=torch.float32, device=self.device)
        model = self._resolve_ez_model()
        if model is None:
            base = super().train_batch(batch)
            return EfficientTrainMetrics(**base.to_dict(), consistency_loss=0.0)

        # Reanalysis: refine value/policy targets with latest network prediction on sampled states.
        reanalysis_coverage = 0.0
        reanalysis_target_drift = 0.0
        reanalysis_policy_drift = 0.0
        if self.reanalysis_ratio > 0.0 and (
            self.reanalysis_value_mix > 0.0 or self.reanalysis_policy_mix > 0.0
        ):
            self._progress("reanalysis_start")
            with torch.no_grad():
                with self._autocast_ctx():
                    _, policy_logits_rean, value_rean, _, _ = model.initial_inference(obs, return_aux=True)
            mask = (torch.rand((len(batch), 1), device=self.device) < self.reanalysis_ratio).to(torch.float32)
            if float(mask.sum().item()) > 0.0:
                if self.reanalysis_value_mix > 0.0:
                    # N-step bootstrapped value target using rollout traces.
                    boot_targets: list[list[float]] = []
                    bootstrap_obs: list[torch.Tensor] = []
                    bootstrap_pos_by_sample: dict[int, int] = {}
                    bootstrap_disc_by_sample: dict[int, float] = {}
                    for s in batch:
                        info = dict(s.info or {})
                        rewards = [float(x) for x in list(info.get("future_rewards", []) or [])]
                        fobs = list(info.get("future_observations", []) or [])
                        done_flags = [bool(x) for x in list(info.get("future_dones", []) or [])]
                        n = min(self.value_bootstrap_steps, len(rewards))
                        ret = 0.0
                        disc = 1.0
                        for t in range(n):
                            ret += disc * float(rewards[t])
                            if t < len(done_flags) and bool(done_flags[t]):
                                disc = 0.0
                                break
                            disc *= self.value_bootstrap_discount
                        if disc > 0.0 and len(fobs) >= n and n > 0:
                            bobs = fobs[n - 1]
                            bobs_t = (
                                bobs.detach().to(torch.float32)
                                if isinstance(bobs, torch.Tensor)
                                else torch.tensor(bobs, dtype=torch.float32)
                            )
                            bootstrap_pos_by_sample[len(boot_targets)] = len(bootstrap_obs)
                            bootstrap_disc_by_sample[len(boot_targets)] = float(disc)
                            bootstrap_obs.append(bobs_t)
                        elif n == 0:
                            ret = float(s.value_target)
                        boot_targets.append([float(ret)])
                    if bootstrap_obs:
                        bobs_batch = torch.stack(bootstrap_obs, dim=0).to(
                            self.device, non_blocking=True
                        )
                        with torch.no_grad():
                            with self._autocast_ctx():
                                _, _, bvals, _, _ = model.initial_inference(
                                    bobs_batch, return_aux=True
                                )
                        bvals_cpu = bvals.detach().to(device="cpu", dtype=torch.float32).view(-1)
                        for sample_idx, obs_idx in bootstrap_pos_by_sample.items():
                            disc = float(bootstrap_disc_by_sample.get(sample_idx, 0.0))
                            if disc <= 0.0:
                                continue
                            boot_targets[sample_idx][0] = float(boot_targets[sample_idx][0]) + (
                                disc * float(bvals_cpu[int(obs_idx)].item())
                            )
                    value_boot = torch.tensor(boot_targets, dtype=torch.float32, device=self.device)
                    blended = ((1.0 - self.reanalysis_value_mix) * value_target) + (
                        self.reanalysis_value_mix * value_boot
                    )
                    drift = torch.abs(value_boot - value_target)
                    value_target = (mask * blended) + ((1.0 - mask) * value_target)
                    reanalysis_target_drift = float((drift * mask).sum().item() / mask.sum().item())

                if self.reanalysis_policy_mix > 0.0:
                    policy_rean = torch.softmax(policy_logits_rean.detach(), dim=-1)
                    pol_blended = ((1.0 - self.reanalysis_policy_mix) * policy_target) + (
                        self.reanalysis_policy_mix * policy_rean
                    )
                    pol_drift = torch.mean(torch.abs(policy_rean - policy_target), dim=-1, keepdim=True)
                    policy_target = (mask * pol_blended) + ((1.0 - mask) * policy_target)
                    reanalysis_policy_drift = float((pol_drift * mask).sum().item() / mask.sum().item())
                reanalysis_coverage = float(mask.mean().item())
            self._progress("reanalysis_done")

        self._progress("forward_start")
        with self._autocast_ctx():
            hidden, policy_logits, value_pred, reward_pred, aux = model.initial_inference(obs, return_aux=True)
            # Cross-entropy / KL divergence: avoids gradient saturation of MSE on softmax
            log_policy_probs = F.log_softmax(policy_logits, dim=-1)
            policy_loss = -(policy_target * log_policy_probs).sum(dim=-1).mean()
            if getattr(self.model, "support_size", 0) > 0 and isinstance(aux, dict) and "value_logits" in aux:
                value_loss = cross_entropy_two_hot(
                    aux["value_logits"], value_target, support_size=self.model.support_size
                )
            else:
                value_loss = F.mse_loss(value_pred, value_target)

            if getattr(self.model, "support_size", 0) > 0 and isinstance(aux, dict) and "reward_logits" in aux:
                reward_loss = cross_entropy_two_hot(
                    aux["reward_logits"], reward_target, support_size=self.model.support_size
                )
            else:
                reward_loss = F.mse_loss(reward_pred, reward_target)
            objective_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if self.objective_loss_weight > 0.0 and isinstance(aux, dict) and "objective_logit" in aux:
                objective_pred = aux["objective_logit"]
                target_rows = []
                for s in batch:
                    info = (s.info or {})
                    if self.objective_target_mode == "progress":
                        delta = float(info.get("objective_progress_delta", 0.0))
                        if "objective_progress_delta" not in info:
                            target_rows.append([float(int(info.get("objective_converted", 0)) > 0)])
                        else:
                            target_rows.append(
                                [1.0 if delta > float(self.objective_progress_positive_threshold) else 0.0]
                            )
                    else:
                        target_rows.append([float(int(info.get("objective_converted", 0)) > 0)])
                objective_target = torch.tensor(target_rows, dtype=torch.float32, device=self.device)
                objective_mask = torch.tensor(
                    [[1.0 if self._objective_had_opportunity(s.info or {}) else 0.0] for s in batch],
                    dtype=torch.float32,
                    device=self.device,
                )
                if float(objective_mask.sum().item()) > 0.0:
                    pos_weight = torch.tensor([self.objective_pos_weight], dtype=torch.float32, device=self.device)
                    bce = F.binary_cross_entropy_with_logits(
                        objective_pred, objective_target, pos_weight=pos_weight, reduction="none"
                    )
                    objective_loss = (bce * objective_mask).sum() / objective_mask.sum().clamp(min=1.0)
            aux_intent_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if (
                self.aux_objective_enabled
                and self.aux_objective_loss_weight > 0.0
                and isinstance(aux, dict)
                and "objective_intent_logits" in aux
            ):
                intent_logits = aux["objective_intent_logits"]
                target_idx = []
                for s in batch:
                    vec = dict((s.info or {}).get("vp_distance_vector", {}) or {})
                    if vec:
                        best_id = min(vec.keys(), key=lambda k: float(vec.get(k, 1e9)))
                        ordered = sorted(vec.keys())
                        target_idx.append(max(0, ordered.index(best_id)))
                    else:
                        target_idx.append(0)
                target_t = torch.tensor(target_idx, dtype=torch.long, device=self.device)
                classes = int(intent_logits.shape[-1]) if intent_logits.ndim == 2 else 0
                if classes > 1:
                    target_t = torch.clamp(target_t, min=0, max=classes - 1)
                    aux_intent_loss = F.cross_entropy(intent_logits, target_t)
            aux_multi_vp_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if (
                self.aux_objective_enabled
                and self.aux_objective_loss_weight > 0.0
                and self.aux_multi_vp_feature_dim > 0
                and isinstance(aux, dict)
                and "multi_vp_pred" in aux
            ):
                target_rows = []
                for s in batch:
                    vec = dict((s.info or {}).get("vp_distance_vector", {}) or {})
                    vals = sorted(float(v) for v in list(vec.values()))
                    vals = vals[: self.aux_multi_vp_feature_dim]
                    if len(vals) < self.aux_multi_vp_feature_dim:
                        vals += [0.0] * (self.aux_multi_vp_feature_dim - len(vals))
                    target_rows.append(vals)
                multi_vp_target = torch.tensor(target_rows, dtype=torch.float32, device=self.device)
                aux_multi_vp_loss = F.smooth_l1_loss(aux["multi_vp_pred"], multi_vp_target)

            aux_threat_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if (
                isinstance(aux, dict)
                and "threat_map_pred" in aux
                and aux["threat_map_pred"] is not None
                and self.aux_threat_loss_weight > 0.0
            ):
                threat_preds = aux["threat_map_pred"]
                target_threats = []
                for s in batch:
                    info_dict = dict(s.info or {})
                    if "threat_map_target" in info_dict:
                        t = torch.as_tensor(info_dict["threat_map_target"], dtype=torch.float32)
                    elif isinstance(s.observation, torch.Tensor) and s.observation.dim() == 3 and s.observation.shape[0] > 7:
                        # Extract the enemy threat map directly from observation tensor (Channel 7: reaction_fire_threat)
                        t = s.observation[7:8].detach().to(dtype=torch.float32)
                    else:
                        t = torch.zeros((1, getattr(self.model, "observation_height", 16), getattr(self.model, "observation_width", 16)), dtype=torch.float32)
                    target_threats.append(t)
                target_threats_t = torch.stack(target_threats, dim=0).to(self.device, non_blocking=True)
                if target_threats_t.shape != threat_preds.shape:
                    try:
                        target_threats_t = target_threats_t.view_as(threat_preds)
                    except Exception:
                        if threat_preds.dim() == 2 and target_threats_t.dim() >= 3:
                            target_threats_t = target_threats_t.view(target_threats_t.shape[0], -1)
                        elif threat_preds.dim() == 4 and target_threats_t.dim() == 3:
                            target_threats_t = target_threats_t.unsqueeze(1)
                aux_threat_loss = F.binary_cross_entropy_with_logits(threat_preds, target_threats_t)

            aux_attrition_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if (
                isinstance(aux, dict)
                and "attrition_pred" in aux
                and aux["attrition_pred"] is not None
                and self.aux_attrition_loss_weight > 0.0
            ):
                target_attritions = []
                for s in batch:
                    info_dict = dict(s.info or {})
                    if "attrition_target" in info_dict:
                        target_attritions.append(list(info_dict["attrition_target"][:2]))
                    else:
                        dmg = float(info_dict.get("damage_dealt", 0.0) or 0.0)
                        edmg = float(info_dict.get("enemy_damage", 0.0) or info_dict.get("damage_received", 0.0) or 0.0)
                        kills = float(info_dict.get("kills_dealt", 0) or 0)
                        target_attritions.append([min(1.0, (edmg + 5.0 * kills) / 10.0), min(1.0, dmg / 10.0)])
                attrition_targets_t = torch.tensor(target_attritions, dtype=torch.float32, device=self.device)
                aux_attrition_loss = F.smooth_l1_loss(aux["attrition_pred"], attrition_targets_t)

            aux_morale_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if (
                isinstance(aux, dict)
                and "morale_pred" in aux
                and aux["morale_pred"] is not None
                and self.aux_morale_loss_weight > 0.0
            ):
                target_morales = []
                for s in batch:
                    info_dict = dict(s.info or {})
                    if "morale_target" in info_dict:
                        target_morales.append(int(info_dict["morale_target"]))
                    else:
                        is_supp = bool(info_dict.get("suppressed", False))
                        is_pin = bool(info_dict.get("pinned", False))
                        dmg_rec = float(info_dict.get("damage_received", 0.0) or 0.0)
                        rf_risk = float(info_dict.get("obs_enemy_reaction_fire_risk", 0.0) or 0.0)
                        if is_supp or dmg_rec >= 2.0:
                            target_morales.append(3)
                        elif is_pin or dmg_rec > 0.0:
                            target_morales.append(2)
                        elif rf_risk > 0.25:
                            target_morales.append(1)
                        else:
                            target_morales.append(0)
                morale_targets_t = torch.tensor(target_morales, dtype=torch.long, device=self.device)
                morale_classes = int(aux["morale_pred"].shape[-1])
                morale_targets_t = torch.clamp(morale_targets_t, min=0, max=morale_classes - 1)
                aux_morale_loss = F.cross_entropy(aux["morale_pred"], morale_targets_t)

            aux_objective_loss = (
                (self.aux_intent_loss_weight * aux_intent_loss)
                + (self.aux_multi_vp_loss_weight * aux_multi_vp_loss)
                + (self.aux_threat_loss_weight * aux_threat_loss)
                + (self.aux_attrition_loss_weight * aux_attrition_loss)
                + (self.aux_morale_loss_weight * aux_morale_loss)
            )

            consistency_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            consistency_pairs = 0
            if self.consistency_loss_weight > 0.0 and self.consistency_unroll_steps > 0:
                sample_future_obs: list[list] = []
                sample_future_actions: list[list[int]] = []
                sample_k_lims: list[int] = []
                active_indices: list[int] = []
                action_dim = int(model.action_dim)
                for i, s in enumerate(batch):
                    info = dict(s.info or {})
                    future_obs = list(info.get("future_observations", []) or [])
                    future_actions = [int(x) for x in list(info.get("future_actions", []) or [])]
                    k_lim = min(self.consistency_unroll_steps, len(future_obs), len(future_actions))
                    sample_future_obs.append(future_obs)
                    sample_future_actions.append(future_actions)
                    sample_k_lims.append(int(k_lim))
                    if k_lim > 0:
                        active_indices.append(i)
                if active_indices:
                    pred_hidden_by_index: dict[int, torch.Tensor] = {
                        i: hidden[i : i + 1] for i in active_indices
                    }
                    max_k = max(sample_k_lims) if sample_k_lims else 0
                    for k in range(int(max_k)):
                        step_indices: list[int] = []
                        step_actions: list[int] = []
                        step_obs_tensors: list[torch.Tensor] = []
                        for i in list(active_indices):
                            if k >= int(sample_k_lims[i]):
                                continue
                            act_idx = int(sample_future_actions[i][k])
                            if act_idx < 0 or act_idx >= action_dim:
                                continue
                            tgt_obs = sample_future_obs[i][k]
                            tgt_obs_t = (
                                tgt_obs.detach().to(torch.float32)
                                if isinstance(tgt_obs, torch.Tensor)
                                else torch.tensor(tgt_obs, dtype=torch.float32)
                            )
                            step_indices.append(i)
                            step_actions.append(act_idx)
                            step_obs_tensors.append(tgt_obs_t)
                        if not step_indices:
                            continue
                        pred_hidden_in = torch.cat(
                            [pred_hidden_by_index[i] for i in step_indices], dim=0
                        )
                        a = torch.zeros(
                            (len(step_indices), action_dim),
                            dtype=torch.float32,
                            device=self.device,
                        )
                        for row_i, act_idx in enumerate(step_actions):
                            a[row_i, int(act_idx)] = 1.0
                        pred_hidden_next, _, _, _ = model.recurrent_inference(
                            pred_hidden_in, a, return_aux=False
                        )
                        for row_i, i in enumerate(step_indices):
                            pred_hidden_by_index[i] = pred_hidden_next[row_i : row_i + 1]
                        tgt_obs_batch = torch.stack(step_obs_tensors, dim=0).to(
                            self.device, non_blocking=True
                        )
                        with torch.no_grad():
                            with self._autocast_ctx():
                                tgt_hidden, _, _, _, _ = model.initial_inference(
                                    tgt_obs_batch, return_aux=True
                                )
                        z_pred = model.consistency_embedding(pred_hidden_next)
                        z_tgt = model.consistency_embedding(tgt_hidden).detach()
                        pair_mse = F.mse_loss(z_pred, z_tgt, reduction="none")
                        pair_mse = pair_mse.view(pair_mse.shape[0], -1).mean(dim=1)
                        consistency_loss = consistency_loss + pair_mse.sum()
                        consistency_pairs += int(len(step_indices))
                if consistency_pairs > 0:
                    consistency_loss = consistency_loss / float(consistency_pairs)
                else:
                    consistency_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)

            eff_aux_weight = self.aux_objective_loss_weight
            if self.adaptive_scaler is not None:
                eff_aux_weight = self.adaptive_scaler.compute_scaled_weight(
                    policy_loss + value_loss, aux_objective_loss, self.aux_objective_loss_weight
                )
            loss = (
                policy_loss
                + value_loss
                + reward_loss
                + (self.objective_loss_weight * objective_loss)
                + (self.consistency_loss_weight * consistency_loss)
                + (eff_aux_weight * aux_objective_loss)
            )
        self._progress("forward_done")
        self.optimizer.zero_grad(set_to_none=True)
        self._progress("backward_start")
        if self.gradient_balance_mode == "pcgrad" and not self._scaler.is_enabled():
            task_losses = [policy_loss, value_loss, reward_loss]
            if self.objective_loss_weight > 0.0:
                task_losses.append(self.objective_loss_weight * objective_loss)
            if self.consistency_loss_weight > 0.0:
                task_losses.append(self.consistency_loss_weight * consistency_loss)
            if eff_aux_weight > 0.0:
                task_losses.append(eff_aux_weight * aux_objective_loss)
            pcgrad_backward(task_losses, self.optimizer, self.model.parameters())
        elif self._scaler.is_enabled():
            self._scaler.scale(loss).backward()
        else:
            loss.backward()
        self._progress("backward_done")
        if self._scaler.is_enabled():
            self._scaler.unscale_(self.optimizer)
            grad_norm_t = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if self.compute_grad_norm:
                grad_norm_t = torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), max_norm=float("inf")
                ).detach()
            self._progress("optimizer_step_start")
            self._scaler.step(self.optimizer)
            self._scaler.update()
        else:
            grad_norm_t = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            if self.compute_grad_norm:
                grad_norm_t = torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), max_norm=float("inf")
                ).detach()
            self._progress("optimizer_step_start")
            self.optimizer.step()
        self._progress("optimizer_step_done")

        # Collapse GPU->CPU sync into one transfer instead of many .item() calls.
        metrics_gpu = torch.stack(
            [
                loss.detach().to(torch.float32),
                policy_loss.detach().to(torch.float32),
                value_loss.detach().to(torch.float32),
                reward_loss.detach().to(torch.float32),
                objective_loss.detach().to(torch.float32),
                consistency_loss.detach().to(torch.float32)
                if consistency_pairs > 0
                else torch.tensor(0.0, dtype=torch.float32, device=self.device),
                aux_objective_loss.detach().to(torch.float32),
                aux_intent_loss.detach().to(torch.float32),
                aux_multi_vp_loss.detach().to(torch.float32),
                aux_threat_loss.detach().to(torch.float32),
                aux_attrition_loss.detach().to(torch.float32),
                aux_morale_loss.detach().to(torch.float32),
                grad_norm_t.detach().to(torch.float32),
            ],
            dim=0,
        ).to(device="cpu")
        mv = metrics_gpu.tolist()

        return EfficientTrainMetrics(
            loss=float(mv[0]),
            policy_loss=float(mv[1]),
            value_loss=float(mv[2]),
            reward_loss=float(mv[3]),
            objective_loss=float(mv[4]),
            grad_norm=float(mv[12]),
            consistency_loss=float(mv[5]),
            reanalysis_coverage=float(reanalysis_coverage),
            reanalysis_target_drift=float(reanalysis_target_drift),
            reanalysis_policy_drift=float(reanalysis_policy_drift),
            consistency_pairs=float(consistency_pairs),
            aux_objective_loss=float(mv[6]),
            aux_intent_loss=float(mv[7]),
            aux_multi_vp_loss=float(mv[8]),
            aux_threat_loss=float(mv[9]),
            aux_attrition_loss=float(mv[10]),
            aux_morale_loss=float(mv[11]),
        )

