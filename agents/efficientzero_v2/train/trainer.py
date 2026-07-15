from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Dict, List

import torch
import torch.nn.functional as F

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.replay import ReplaySample
from agents.efficientzero_v2.train.trainer_base import EfficientZeroV2BaseTrainer, TrainMetrics


@dataclass
class EfficientTrainMetrics(TrainMetrics):
    consistency_loss: float = 0.0
    reanalysis_coverage: float = 0.0
    reanalysis_target_drift: float = 0.0
    reanalysis_policy_drift: float = 0.0
    consistency_pairs: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        d = super().to_dict()
        d["consistency_loss"] = float(self.consistency_loss)
        d["reanalysis_coverage"] = float(self.reanalysis_coverage)
        d["reanalysis_target_drift"] = float(self.reanalysis_target_drift)
        d["reanalysis_policy_drift"] = float(self.reanalysis_policy_drift)
        d["consistency_pairs"] = float(self.consistency_pairs)
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
            )

        obs = torch.stack(
            [
                s.observation.detach().clone().to(torch.float32)
                if isinstance(s.observation, torch.Tensor)
                else torch.tensor(s.observation, dtype=torch.float32)
                for s in batch
            ],
            dim=0,
        ).to(self.device, non_blocking=True)
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
            with torch.no_grad():
                with self._autocast_ctx():
                    _, policy_logits_rean, value_rean, _, _ = model.initial_inference(obs, return_aux=True)
            mask = (torch.rand((len(batch), 1), device=self.device) < self.reanalysis_ratio).to(torch.float32)
            if float(mask.sum().item()) > 0.0:
                if self.reanalysis_value_mix > 0.0:
                    # N-step bootstrapped value target using rollout traces.
                    boot_targets = []
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
                                bobs.detach().clone().to(torch.float32)
                                if isinstance(bobs, torch.Tensor)
                                else torch.tensor(bobs, dtype=torch.float32)
                            ).unsqueeze(0).to(self.device, non_blocking=True)
                            with torch.no_grad():
                                with self._autocast_ctx():
                                    _, _, bval, _, _ = model.initial_inference(bobs_t, return_aux=True)
                            ret += disc * float(bval.detach().cpu().item())
                        elif n == 0:
                            ret = float(s.value_target)
                        boot_targets.append([float(ret)])
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

        with self._autocast_ctx():
            hidden, policy_logits, value_pred, reward_pred, aux = model.initial_inference(obs, return_aux=True)
            policy_loss = F.mse_loss(torch.softmax(policy_logits, dim=-1), policy_target)
            value_loss = F.mse_loss(value_pred, value_target)
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

            consistency_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
            consistency_pairs = 0
            if self.consistency_loss_weight > 0.0 and self.consistency_unroll_steps > 0:
                for i, s in enumerate(batch):
                    info = dict(s.info or {})
                    future_obs = list(info.get("future_observations", []) or [])
                    future_actions = list(info.get("future_actions", []) or [])
                    k_lim = min(self.consistency_unroll_steps, len(future_obs), len(future_actions))
                    if k_lim <= 0:
                        continue
                    pred_hidden = hidden[i : i + 1]
                    for k in range(k_lim):
                        act_idx = int(future_actions[k])
                        if act_idx < 0 or act_idx >= int(model.action_dim):
                            continue
                        a = torch.zeros((1, int(model.action_dim)), dtype=torch.float32, device=self.device)
                        a[0, act_idx] = 1.0
                        pred_hidden, _, _, _ = model.recurrent_inference(pred_hidden, a, return_aux=False)
                        tgt_obs = future_obs[k]
                        tgt_obs_t = (
                            tgt_obs.detach().clone().to(torch.float32)
                            if isinstance(tgt_obs, torch.Tensor)
                            else torch.tensor(tgt_obs, dtype=torch.float32)
                        ).unsqueeze(0).to(self.device, non_blocking=True)
                        with torch.no_grad():
                            tgt_hidden, _, _, _, _ = model.initial_inference(tgt_obs_t, return_aux=True)
                        z_pred = model.consistency_embedding(pred_hidden)
                        z_tgt = model.consistency_embedding(tgt_hidden).detach()
                        consistency_loss = consistency_loss + F.mse_loss(z_pred, z_tgt)
                        consistency_pairs += 1
                if consistency_pairs > 0:
                    consistency_loss = consistency_loss / float(consistency_pairs)
                else:
                    consistency_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)

            loss = (
                policy_loss
                + value_loss
                + reward_loss
                + (self.objective_loss_weight * objective_loss)
                + (self.consistency_loss_weight * consistency_loss)
            )
        self.optimizer.zero_grad()
        if self._scaler.is_enabled():
            self._scaler.scale(loss).backward()
        else:
            loss.backward()
        if self._scaler.is_enabled():
            self._scaler.unscale_(self.optimizer)
            grad_norm = float(
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=float("inf")).item()
            )
            self._scaler.step(self.optimizer)
            self._scaler.update()
        else:
            grad_norm = float(
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=float("inf")).item()
            )
            self.optimizer.step()

        return EfficientTrainMetrics(
            loss=float(loss.detach().cpu().item()),
            policy_loss=float(policy_loss.detach().cpu().item()),
            value_loss=float(value_loss.detach().cpu().item()),
            reward_loss=float(reward_loss.detach().cpu().item()),
            objective_loss=float(objective_loss.detach().cpu().item()),
            grad_norm=float(grad_norm),
            consistency_loss=float(consistency_loss.detach().cpu().item())
            if consistency_pairs > 0
            else 0.0,
            reanalysis_coverage=float(reanalysis_coverage),
            reanalysis_target_drift=float(reanalysis_target_drift),
            reanalysis_policy_drift=float(reanalysis_policy_drift),
            consistency_pairs=float(consistency_pairs),
        )

