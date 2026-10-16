from __future__ import annotations

import math
import torch
import torch.nn.functional as F


def phi_transform(x: torch.Tensor, eps: float = 0.001) -> torch.Tensor:
    """
    Contractive scalar transformation h(x) = sign(x) * (sqrt(|x| + 1) - 1) + eps * x.
    Used in MuZero/EfficientZero to compress dynamic range of rewards and values.
    """
    return torch.sign(x) * (torch.sqrt(torch.abs(x) + 1.0) - 1.0) + eps * x


def phi_inverse(y: torch.Tensor, eps: float = 0.001) -> torch.Tensor:
    """
    Inverse of the contractive scalar transformation h^-1(y).
    """
    if eps == 0.0:
        return torch.sign(y) * (torch.square(torch.abs(y) + 1.0) - 1.0)
    
    # Quadratic solution for sqrt(|x| + 1):
    # eps * (|x| + 1) + sqrt(|x| + 1) - (1 + eps + |y|) = 0
    abs_y = torch.abs(y)
    sqrt_term = torch.sqrt(1.0 + 4.0 * eps * (abs_y + 1.0 + eps))
    sqrt_val = (-1.0 + sqrt_term) / (2.0 * eps)
    x = torch.square(sqrt_val) - 1.0
    return torch.sign(y) * torch.clamp(x, min=0.0)


def scalar_to_two_hot(
    scalar: torch.Tensor,
    support_size: int = 30,
    use_phi: bool = True,
    eps: float = 0.001,
) -> torch.Tensor:
    """
    Encodes scalar values into a discrete two-hot probability distribution over
    the support range [-support_size, +support_size].

    Output shape: (*scalar.shape, 2 * support_size + 1)
    """
    if use_phi:
        transformed = phi_transform(scalar, eps=eps)
    else:
        transformed = scalar

    # Clamp transformed values to valid support bounds
    clamped = torch.clamp(transformed, -float(support_size), float(support_size))
    
    # Offset coordinates so minimum index is 0 (mapping [-K, +K] -> [0, 2K])
    shifted = clamped + float(support_size)
    low_idx = torch.floor(shifted).long()
    high_idx = torch.ceil(shifted).long()
    
    high_weight = shifted - low_idx.float()
    low_weight = 1.0 - high_weight

    num_atoms = 2 * support_size + 1
    # Create target tensor
    out_shape = list(scalar.shape) + [num_atoms]
    target = torch.zeros(out_shape, dtype=torch.float32, device=scalar.device)

    # Handle exact integer alignments where low_idx == high_idx
    low_idx_clamped = torch.clamp(low_idx, 0, num_atoms - 1)
    high_idx_clamped = torch.clamp(high_idx, 0, num_atoms - 1)

    target.scatter_(-1, low_idx_clamped.unsqueeze(-1), low_weight.unsqueeze(-1))
    target.scatter_add_(-1, high_idx_clamped.unsqueeze(-1), high_weight.unsqueeze(-1))
    return target


def support_to_scalar(
    logits: torch.Tensor,
    support_size: int = 30,
    use_phi: bool = True,
    eps: float = 0.001,
) -> torch.Tensor:
    """
    Converts two-hot support logits into continuous scalar values by taking the expected
    value across the support grid and applying the inverse transformation phi^-1.

    Output shape: (*logits.shape[:-1], 1)
    """
    probs = F.softmax(logits, dim=-1)
    num_atoms = 2 * support_size + 1
    support_grid = torch.arange(
        -support_size, support_size + 1, dtype=torch.float32, device=logits.device
    )
    expected_transformed = (probs * support_grid).sum(dim=-1, keepdim=True)
    if use_phi:
        return phi_inverse(expected_transformed, eps=eps)
    return expected_transformed


def cross_entropy_two_hot(
    logits: torch.Tensor,
    targets: torch.Tensor,
    support_size: int = 30,
    use_phi: bool = True,
    reduction: str = "mean",
) -> torch.Tensor:
    """
    Computes cross-entropy loss between predicted logits and two-hot encoded scalar targets.
    """
    target_dist = scalar_to_two_hot(targets, support_size=support_size, use_phi=use_phi)
    log_probs = F.log_softmax(logits, dim=-1)
    loss = -(target_dist * log_probs).sum(dim=-1)
    if reduction == "mean":
        return loss.mean()
    elif reduction == "sum":
        return loss.sum()
    return loss
