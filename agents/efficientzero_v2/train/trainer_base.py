from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import torch
import torch.nn.functional as F

from agents.efficientzero_v2.core.network_base import EfficientZeroV2BaseNetwork
from agents.efficientzero_v2.core.replay import ReplaySample


@dataclass
class TrainMetrics:
    loss: float
    policy_loss: float
    value_loss: float
    reward_loss: float
    objective_loss: float = 0.0
    grad_norm: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "loss": self.loss,
            "policy_loss": self.policy_loss,
            "value_loss": self.value_loss,
            "reward_loss": self.reward_loss,
            "objective_loss": self.objective_loss,
            "grad_norm": self.grad_norm,
        }


class EfficientZeroV2BaseTrainer:
    def __init__(
        self,
        model: EfficientZeroV2BaseNetwork,
        lr: float = 1e-3,
        device: str = "cpu",
        objective_loss_weight: float = 0.0,
        objective_target_mode: str = "progress",
        objective_pos_weight: float = 1.0,
        objective_opportunity_max_dist: float = 2.0,
        objective_progress_positive_threshold: float = 0.0,
    ):
        self.device = device
        self.model = model.to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.objective_loss_weight = float(max(0.0, objective_loss_weight))
        self.objective_target_mode = str(objective_target_mode or "progress").strip().lower()
        if self.objective_target_mode not in {"progress", "conversion"}:
            self.objective_target_mode = "progress"
        self.objective_pos_weight = float(max(1.0, objective_pos_weight))
        self.objective_opportunity_max_dist = float(max(0.0, objective_opportunity_max_dist))
        self.objective_progress_positive_threshold = float(objective_progress_positive_threshold)

    def _objective_had_opportunity(self, info: dict) -> bool:
        payload = dict(info or {})
        if "objective_had_opportunity" in payload:
            return int(payload.get("objective_had_opportunity", 0)) > 0
        if int(payload.get("legal_capture_options", 0)) > 0:
            return True
        if int(payload.get("objective_converted", 0)) > 0:
            return True
        if float(payload.get("objective_progress_delta", 0.0)) > 0.0:
            return True
        before = float(
            payload.get(
                "objective_min_dist_before",
                payload.get("objective_distance_before", -1.0),
            )
        )
        after = float(
            payload.get(
                "objective_min_dist_after",
                payload.get("objective_distance_after", -1.0),
            )
        )
        dist_cap = float(self.objective_opportunity_max_dist)
        return bool((before >= 0.0 and before <= dist_cap) or (after >= 0.0 and after <= dist_cap))

    def train_batch(self, batch: List[ReplaySample]) -> TrainMetrics:
        if not batch:
            return TrainMetrics(
                loss=0.0,
                policy_loss=0.0,
                value_loss=0.0,
                reward_loss=0.0,
                objective_loss=0.0,
                grad_norm=0.0,
            )

        first_obs = batch[0].observation
        if isinstance(first_obs, torch.Tensor):
            obs = torch.stack(
                [
                    s.observation.detach().clone().to(torch.float32)
                    if isinstance(s.observation, torch.Tensor)
                    else torch.tensor(s.observation, dtype=torch.float32)
                    for s in batch
                ],
                dim=0,
            ).to(self.device)
        else:
            obs = torch.tensor([s.observation for s in batch], dtype=torch.float32, device=self.device)
        policy_target = torch.tensor([s.policy_target for s in batch], dtype=torch.float32, device=self.device)
        value_target = torch.tensor([[s.value_target] for s in batch], dtype=torch.float32, device=self.device)
        reward_target = torch.tensor([[s.reward_target] for s in batch], dtype=torch.float32, device=self.device)

        _, policy_logits, value_pred, reward_pred, aux = self.model.initial_inference(obs, return_aux=True)
        policy_loss = F.mse_loss(torch.softmax(policy_logits, dim=-1), policy_target)
        value_loss = F.mse_loss(value_pred, value_target)
        reward_loss = F.mse_loss(reward_pred, reward_target)
        objective_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
        if self.objective_loss_weight > 0.0 and isinstance(aux, dict) and "objective_logit" in aux:
            objective_pred = aux["objective_logit"]
            target_rows = []
            for s in batch:
                info = s.info or {}
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
            masked_count = float(objective_mask.sum().item())
            if masked_count > 0.0:
                pos_weight = torch.tensor([self.objective_pos_weight], dtype=torch.float32, device=self.device)
                bce = F.binary_cross_entropy_with_logits(
                    objective_pred,
                    objective_target,
                    pos_weight=pos_weight,
                    reduction="none",
                )
                objective_loss = (bce * objective_mask).sum() / objective_mask.sum().clamp(min=1.0)
        loss = policy_loss + value_loss + reward_loss + (self.objective_loss_weight * objective_loss)

        self.optimizer.zero_grad()
        loss.backward()
        grad_sq_sum = 0.0
        for p in self.model.parameters():
            if p.grad is None:
                continue
            g = p.grad.detach()
            grad_sq_sum += float((g * g).sum().item())
        grad_norm = float(grad_sq_sum**0.5)
        self.optimizer.step()

        return TrainMetrics(
            loss=float(loss.detach().cpu().item()),
            policy_loss=float(policy_loss.detach().cpu().item()),
            value_loss=float(value_loss.detach().cpu().item()),
            reward_loss=float(reward_loss.detach().cpu().item()),
            objective_loss=float(objective_loss.detach().cpu().item()),
            grad_norm=float(grad_norm),
        )
