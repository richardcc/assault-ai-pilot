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
    asym_zero_boost: bool = False,
    zero_power: float = 0.75,
) -> torch.Tensor:
    """
    Encodes scalar values into a discrete two-hot probability distribution over
    the support range [-support_size, +support_size].

    When asym_zero_boost=True, applies a power warp sign(x) * |x|^zero_power (default 0.75)
    to expand small values near zero (e.g. 0.05 -> 0.105), allowing the 61 discrete atoms
    to discriminate fine-grained tactical attrition micro-advantages.

    Output shape: (*scalar.shape, 2 * support_size + 1)
    """
    if asym_zero_boost:
        # Non-linear warp around zero to discriminate micro-attrition:
        sign = torch.sign(scalar)
        warped = sign * torch.pow(torch.abs(scalar), zero_power)
        if use_phi:
            transformed = phi_transform(warped, eps=eps)
        else:
            transformed = warped
    elif use_phi:
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
    asym_zero_boost: bool = False,
    zero_power: float = 0.75,
) -> torch.Tensor:
    """
    Converts two-hot support logits into continuous scalar values by taking the expected
    value across the support grid and applying the inverse transformation phi^-1 (and un-warping if asym_zero_boost).

    Output shape: (*logits.shape[:-1], 1)
    """
    probs = F.softmax(logits, dim=-1)
    num_atoms = 2 * support_size + 1
    support_grid = torch.arange(
        -support_size, support_size + 1, dtype=torch.float32, device=logits.device
    )
    expected_transformed = (probs * support_grid).sum(dim=-1, keepdim=True)
    if use_phi:
        unwarped = phi_inverse(expected_transformed, eps=eps)
    else:
        unwarped = expected_transformed

    if asym_zero_boost:
        # Invert the power-warp: sign(y) * |y|^(1 / zero_power)
        inv_power = 1.0 / max(1e-4, float(zero_power))
        return torch.sign(unwarped) * torch.pow(torch.abs(unwarped), inv_power)
    return unwarped


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


def symlog(x: torch.Tensor) -> torch.Tensor:
    """
    Symmetric logarithmic compression function: symlog(x) = sign(x) * ln(|x| + 1).
    Used in DreamerV3 and modern model-based RL to compress values across multiple orders of magnitude.
    """
    return torch.sign(x) * torch.log1p(torch.abs(x))


def symexp(y: torch.Tensor) -> torch.Tensor:
    """
    Inverse of symmetric logarithmic compression: symexp(y) = sign(y) * (exp(|y|) - 1).
    """
    return torch.sign(y) * torch.expm1(torch.abs(y))


def scalar_to_hl_gauss(
    scalar: torch.Tensor,
    support_size: int = 30,
    sigma: float = 0.75,
    use_phi: bool = True,
    use_symlog: bool = False,
    eps: float = 0.001,
) -> torch.Tensor:
    """
    Encodes scalar values into an HL-Gauss (Histogram Loss with Gaussian Targets)
    distribution across the support grid [-support_size, +support_size].
    Introduced in DeepMind's 'Stop Regressing' (2024) to provide smooth, non-overfitting
    targets for RL value and reward distributions.
    """
    if use_symlog:
        transformed = symlog(scalar)
    elif use_phi:
        transformed = phi_transform(scalar, eps=eps)
    else:
        transformed = scalar

    clamped = torch.clamp(transformed, -float(support_size), float(support_size))
    # Support grid: [-K, ..., 0, ..., +K] -> shape (2K + 1)
    support_grid = torch.arange(
        -support_size, support_size + 1, dtype=torch.float32, device=scalar.device
    )
    diff = support_grid - clamped.unsqueeze(-1)
    # Gaussian density: exp(-0.5 * (diff / sigma)^2)
    weights = torch.exp(-0.5 * torch.square(diff / max(1e-4, sigma)))
    # Normalize across atoms so probabilities sum to 1.0
    probs = weights / torch.clamp(weights.sum(dim=-1, keepdim=True), min=1e-8)
    return probs


def cross_entropy_hl_gauss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    support_size: int = 30,
    sigma: float = 0.75,
    use_phi: bool = True,
    use_symlog: bool = False,
    reduction: str = "mean",
) -> torch.Tensor:
    """
    Computes cross-entropy loss against an HL-Gauss smoothed target distribution.
    """
    target_dist = scalar_to_hl_gauss(
        targets, support_size=support_size, sigma=sigma, use_phi=use_phi, use_symlog=use_symlog
    )
    log_probs = F.log_softmax(logits, dim=-1)
    loss = -(target_dist * log_probs).sum(dim=-1)
    if reduction == "mean":
        return loss.mean()
    elif reduction == "sum":
        return loss.sum()
    return loss


def compute_potential_difference(
    phi_before: float,
    phi_after: float,
    gamma: float = 0.997,
    done: bool = False,
    shaping_scale: float = 1.0,
) -> float:
    """
    Computes invariant potential-based reward shaping difference (Ng et al. 1999):
        F(s, a, s') = gamma * Phi(s') - Phi(s)   [non-terminal]
        F(s, a, s') = -Phi(s)                     [terminal: Phi(s') = 0.0]

    Theorem 1 (Ng, Harada & Russell 1999):
        Preserves optimal policy invariance: argmax_a Q*_{M'}(s, a) = argmax_a Q*_M(s, a).
    """
    effective_phi_after = 0.0 if bool(done) else float(phi_after)
    delta = (float(gamma) * effective_phi_after) - float(phi_before)
    return float(delta * float(shaping_scale))


