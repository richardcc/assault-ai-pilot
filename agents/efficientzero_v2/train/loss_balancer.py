from __future__ import annotations

from typing import List, Sequence
import torch


def pcgrad_backward(
    losses: Sequence[torch.Tensor],
    optimizer: torch.optim.Optimizer,
    shared_parameters: Sequence[torch.nn.Parameter],
) -> float:
    """
    Projecting Conflicting Gradients (PCGrad).
    
    When two tasks i and j have conflicting gradients (dot product g_i . g_j < 0),
    projects g_i onto the normal plane of g_j:
        g_i = g_i - (g_i . g_j / ||g_j||^2) * g_j
        
    This prevents auxiliary heads from destroying the representations learned by
    the core policy and value heads.
    """
    params = [p for p in shared_parameters if p.requires_grad]
    if not params or not losses:
        return 0.0

    task_flat_grads: List[torch.Tensor] = []
    
    # 1. Compute per-loss gradients and flatten into contiguous 1D tensors
    for idx, loss in enumerate(losses):
        if not loss.requires_grad or float(loss.detach().item()) == 0.0:
            total_elements = sum(p.numel() for p in params)
            task_flat_grads.append(torch.zeros(total_elements, device=params[0].device, dtype=params[0].dtype))
            continue
        grads = torch.autograd.grad(
            loss,
            params,
            retain_graph=(idx < len(losses) - 1),
            allow_unused=True,
        )
        flat = torch.cat([
            (g if g is not None else torch.zeros_like(p)).reshape(-1)
            for g, p in zip(grads, params)
        ])
        task_flat_grads.append(flat)

    num_tasks = len(task_flat_grads)
    # 2. Project conflicting gradients in vectorized 1D tensor space
    projected = [g.clone() for g in task_flat_grads]
    
    for i in range(num_tasks):
        for j in range(num_tasks):
            if i == j:
                continue
            dot_prod = torch.dot(projected[i], task_flat_grads[j])
            if dot_prod < 0.0:
                norm_sq = torch.dot(task_flat_grads[j], task_flat_grads[j])
                if norm_sq > 1e-12:
                    projected[i] = projected[i] - (dot_prod / norm_sq) * task_flat_grads[j]

    # 3. Sum projected gradients and unflatten directly to parameter grad
    optimizer.zero_grad(set_to_none=True)
    combined_flat = torch.stack(projected, dim=0).sum(dim=0)
    
    offset = 0
    for p in params:
        numel = p.numel()
        p.grad = combined_flat[offset : offset + numel].view_as(p).clone()
        offset += numel

    grad_norm = float(torch.linalg.vector_norm(combined_flat).item())
    return grad_norm


class AdaptiveLossScaler:
    """
    Dynamically scales auxiliary loss weights based on the ratio of primary
    gradients (policy + value) to auxiliary gradients. Prevents auxiliary losses
    from dominating optimization.
    """
    def __init__(
        self,
        target_aux_ratio: float = 0.25,
        min_scale: float = 0.01,
        max_scale: float = 2.0,
        momentum: float = 0.9,
    ):
        self.target_aux_ratio = float(target_aux_ratio)
        self.min_scale = float(min_scale)
        self.max_scale = float(max_scale)
        self.momentum = float(momentum)
        self._running_scale: float = 1.0

    def compute_scaled_weight(
        self,
        primary_loss: torch.Tensor,
        aux_loss: torch.Tensor,
        nominal_weight: float,
    ) -> float:
        if nominal_weight <= 0.0:
            return 0.0
        p_val = float(primary_loss.detach().item())
        a_val = float(aux_loss.detach().item())
        if a_val <= 1e-8:
            return nominal_weight
        
        desired_weight = (p_val * self.target_aux_ratio) / a_val
        bounded = max(self.min_scale, min(self.max_scale, desired_weight))
        self._running_scale = (self.momentum * self._running_scale) + ((1.0 - self.momentum) * bounded)
        return float(nominal_weight * self._running_scale)
