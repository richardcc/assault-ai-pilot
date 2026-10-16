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

    task_grads: List[List[torch.Tensor]] = []
    
    # 1. Compute per-loss gradients
    for idx, loss in enumerate(losses):
        if not loss.requires_grad or float(loss.detach().item()) == 0.0:
            task_grads.append([torch.zeros_like(p) for p in params])
            continue
        grads = torch.autograd.grad(
            loss,
            params,
            retain_graph=(idx < len(losses) - 1),
            allow_unused=True,
        )
        task_grads.append(
            [g.clone() if g is not None else torch.zeros_like(p) for g, p in zip(grads, params)]
        )

    num_tasks = len(task_grads)
    # 2. Project conflicting gradients
    projected_grads = [[g.clone() for g in t_grads] for t_grads in task_grads]
    
    for i in range(num_tasks):
        for j in range(num_tasks):
            if i == j:
                continue
            # Compute dot product between task i and task j gradients
            g_i = projected_grads[i]
            g_j = task_grads[j]
            dot_prod = sum((gi * gj).sum() for gi, gj in zip(g_i, g_j))
            if dot_prod < 0.0:
                norm_sq = sum((gj * gj).sum() for gj in g_j)
                if norm_sq > 1e-12:
                    scale = dot_prod / norm_sq
                    for k in range(len(params)):
                        projected_grads[i][k] = projected_grads[i][k] - scale * g_j[k]

    # 3. Sum projected gradients and assign to parameter grad attributes
    optimizer.zero_grad(set_to_none=True)
    grad_sq_sum = 0.0
    for p_idx, p in enumerate(params):
        combined_g = sum(projected_grads[t_idx][p_idx] for t_idx in range(num_tasks))
        p.grad = combined_g
        grad_sq_sum += float((combined_g * combined_g).sum().item())

    return float(grad_sq_sum**0.5)


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
