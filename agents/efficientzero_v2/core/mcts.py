from __future__ import annotations

from dataclasses import dataclass
from math import copysign, log1p, sqrt, tanh
import random
from typing import Dict, List, Optional


@dataclass
class MCTSOutput:
    actions: List[str]
    visits: List[int]
    probs: List[float]
    chosen_action: str
    chosen_score: float = 0.0
    q_guardrail_clipped_count: int = 0
    q_guardrail_clip_limit: Optional[float] = None
    q_root_score_spread: float = 0.0
    q_root_normalization_applied: bool = False
    chance_samples_per_expansion: int = 1
    sterile_branches_pruned_count: int = 0
    root_candidate_breakdown: Optional[List[Dict[str, float]]] = None



def _clip_q_value(value: float, clip_abs: Optional[float]) -> tuple[float, bool]:
    if clip_abs is None:
        return float(value), False
    limit = float(max(0.0, clip_abs))
    if limit <= 0.0:
        return 0.0, float(value) != 0.0
    v = float(value)
    if v > limit:
        return float(limit), True
    if v < -limit:
        return float(-limit), True
    return v, False


def _stable_prior(action_id: str) -> float:
    # Deterministic pseudo-prior in [0.05, 0.95], stable across runs.
    score = sum(action_id.encode("utf-8")) % 100
    return 0.05 + 0.90 * (score / 99.0)


def _normalize_root_q(
    clipped_q: List[float],
    unclipped_q: List[float],
    mode: str,
    strength: float,
) -> tuple[List[float], bool]:
    mode_key = str(mode or "none").strip().lower()
    alpha = max(0.0, min(1.0, float(strength)))
    if alpha <= 0.0 or mode_key in {"", "none", "off"}:
        return list(clipped_q), False

    def _minmax(values: List[float]) -> List[float]:
        lo = float(min(values))
        hi = float(max(values))
        if (hi - lo) <= 1e-12:
            return [0.0 for _ in values]
        return [((2.0 * (float(v) - lo) / (hi - lo)) - 1.0) for v in values]

    normalized = _minmax(clipped_q)
    clipped_spread = float(max(clipped_q) - min(clipped_q)) if clipped_q else 0.0
    if mode_key in {"adaptive_minmax", "adaptive"} and clipped_spread <= 1e-12:
        normalized = _minmax(unclipped_q)
    blended = [
        ((1.0 - alpha) * float(base)) + (alpha * float(norm))
        for base, norm in zip(clipped_q, normalized)
    ]
    return blended, True


def compute_adaptive_simulations(
    base_simulations: int,
    priors_by_action: Optional[Dict[str, float]] = None,
    values_by_action: Optional[Dict[str, float]] = None,
    min_simulations: int = 8,
    max_multiplier: float = 2.0,
) -> int:
    """Adaptive Computation Time (PonderNet / Graves 2016) MCTS simulation budget.

    Allocates fewer simulations when a single legal action dominates the policy
    prior with low value variance, and up to ``base_simulations * max_multiplier``
    when the root policy entropy or value spread is high (critical tactical state).
    """
    base = max(1, int(base_simulations))
    if not priors_by_action or len(priors_by_action) <= 1:
        return max(1, min(base, int(min_simulations)))

    probs = [max(0.0, float(p)) for p in priors_by_action.values()]
    total_p = sum(probs)
    if total_p <= 1e-12:
        return base
    probs = [p / total_p for p in probs]
    n = len(probs)

    # Normalized Shannon entropy in [0, 1]
    from math import log
    entropy = -sum(p * log(max(p, 1e-12)) for p in probs if p > 0.0)
    max_entropy = max(1e-6, log(float(n)))
    norm_entropy = max(0.0, min(1.0, entropy / max_entropy))

    # Value uncertainty spread in [0, 1]
    val_spread = 0.0
    if values_by_action and len(values_by_action) > 1:
        vals = [float(v) for v in values_by_action.values()]
        val_spread = max(0.0, min(1.0, (max(vals) - min(vals)) * 0.5))

    complexity = 0.65 * norm_entropy + 0.35 * val_spread
    scale = 0.5 + complexity * max(0.5, float(max_multiplier) - 0.5)
    target = int(round(base * scale))
    return max(int(min_simulations), min(int(round(base * float(max_multiplier))), target))


def run_mcts_puct(
    legal_actions: List[str],
    num_simulations: int = 32,
    c_puct: float = 1.5,
    priors_by_action: Optional[Dict[str, float]] = None,
    values_by_action: Optional[Dict[str, float]] = None,
    value_sign_by_action: Optional[Dict[str, int]] = None,
    temperature: float = 1.0,
    dirichlet_alpha: float = 0.3,
    dirichlet_epsilon: float = 0.0,
    q_clip_abs: Optional[float] = 10.0,
    q_root_normalization_mode: str = "adaptive_minmax",
    q_root_normalization_strength: float = 0.35,
    chance_mode: str = "off",
    chance_samples_per_expansion: int = 1,
    chance_value_noise_std: float = 0.0,
    success_prob_by_action: Optional[Dict[str, float]] = None,
    success_prob_enabled: bool = False,
    success_prob_alpha: float = 0.0,
    success_prob_center: float = 0.5,
    success_prob_scale: float = 0.5,
    success_prob_centered_clip_abs: float = 1.0,
    min_root_visits_per_action: int = 0,
    min_root_visits_top_n: int = 0,
    value_rescale_mode: str = "tanh",
    value_rescale_temperature: float = 10.0,
    vp_race_prior_biasing: bool = False,
    vp_race_bonus_by_action: Optional[Dict[str, float]] = None,
    sterile_action_mask: Optional[Dict[str, bool]] = None,
    sterile_prune_penalty: float = 0.40,
) -> MCTSOutput:
    if not legal_actions:
        return MCTSOutput(actions=[], visits=[], probs=[], chosen_action="")

    n = len(legal_actions)
    if priors_by_action:
        priors = [float(priors_by_action.get(a, 0.0)) for a in legal_actions]
        if sum(priors) <= 0.0:
            priors = [_stable_prior(a) for a in legal_actions]
    else:
        priors = [_stable_prior(a) for a in legal_actions]
    prior_sum = sum(priors)
    priors = [p / prior_sum for p in priors]

    # Task 2.2: VP Race Prior Biasing and Sterile Wandering Pruning (~40%)
    sterile_branches_pruned_count = 0
    if vp_race_prior_biasing and (vp_race_bonus_by_action or sterile_action_mask):
        biasing_bonus = dict(vp_race_bonus_by_action or {})
        sterile_mask = dict(sterile_action_mask or {})
        adjusted_priors: list[float] = []
        for a, p in zip(legal_actions, priors):
            p_val = float(p)
            bonus = float(biasing_bonus.get(a, 0.0) or 0.0)
            if bonus > 0.0:
                p_val *= (1.0 + bonus)
            if sterile_mask.get(a, False) and sterile_prune_penalty > 0.0:
                p_val *= max(0.01, 1.0 - float(sterile_prune_penalty))
                sterile_branches_pruned_count += 1
            adjusted_priors.append(max(1e-8, p_val))
        adj_sum = sum(adjusted_priors)
        if adj_sum > 0.0:
            priors = [x / adj_sum for x in adjusted_priors]

    if dirichlet_epsilon > 0.0:

        noise = [random.gammavariate(dirichlet_alpha, 1.0) for _ in range(n)]
        noise_sum = sum(noise)
        if noise_sum > 0.0:
            noise = [x / noise_sum for x in noise]
            priors = [
                ((1.0 - dirichlet_epsilon) * p) + (dirichlet_epsilon * e)
                for p, e in zip(priors, noise)
            ]

    visits = [0] * n
    value_sums = [0.0] * n
    q_guardrail_clipped_count = 0
    q_root_score_spread = 0.0
    q_root_normalization_applied = False

    chance_mode_key = str(chance_mode or "off").strip().lower()
    chance_k = max(1, int(chance_samples_per_expansion))
    chance_noise_std = max(0.0, float(chance_value_noise_std))
    chance_enabled = chance_mode_key in {"sampled_expectation", "sampled", "mc"} and chance_k > 1
    success_enabled = bool(success_prob_enabled) and float(success_prob_alpha) != 0.0
    success_alpha = float(success_prob_alpha)
    success_center = float(success_prob_center)
    success_scale = max(1e-6, abs(float(success_prob_scale)))
    success_centered_clip = max(0.0, float(success_prob_centered_clip_abs))
    min_root_k = max(0, int(min_root_visits_per_action))
    configured_top_n = int(min_root_visits_top_n)
    # Contract: top_n <= 0 means "apply to all legal root actions".
    min_root_n = n if configured_top_n <= 0 else max(0, min(configured_top_n, n))
    forced_root_indices: list[int] = []
    if min_root_k > 0 and min_root_n > 0:
        forced_root_indices = sorted(range(n), key=lambda i: float(priors[i]), reverse=True)[:min_root_n]

    def _rescale_value_estimate(value: float) -> float:
        mode = str(value_rescale_mode or "tanh").strip().lower()
        if mode in {"", "off", "none"}:
            return float(value)
        temp = max(1e-6, float(value_rescale_temperature))
        if mode == "tanh":
            return float(tanh(float(value) / temp))
        if mode in {"signed_log_tanh", "log_tanh"}:
            v = float(value)
            signed_log = copysign(log1p(abs(v)), v)
            return float(tanh(signed_log / temp))
        # Unknown mode defaults to tanh for safety.
        return float(tanh(float(value) / temp))

    def _success_components(action_id: str) -> tuple[float, float, float]:
        if not success_enabled:
            return 0.5, 0.0, 0.0
        raw = 0.5
        if success_prob_by_action:
            try:
                raw = float(success_prob_by_action.get(action_id, 0.5))
            except Exception:
                raw = 0.5
        raw = max(0.0, min(1.0, raw))
        centered = (raw - success_center) / success_scale
        if success_centered_clip > 0.0:
            centered = max(-success_centered_clip, min(success_centered_clip, centered))
        comp = success_alpha * centered
        return float(raw), float(centered), float(comp)

    required_root_visits = int(min_root_k * min_root_n) if (min_root_k > 0 and min_root_n > 0) else 0
    total_simulations = max(1, int(num_simulations), int(required_root_visits))

    # Precomputed caches outside simulation loop to eliminate redundant function calls and lookups (Task 2.9)
    precomputed_success_comps = [
        _success_components(legal_actions[i])[2] for i in range(n)
    ]
    priors_c_puct = [c_puct * priors[i] for i in range(n)]
    if values_by_action:
        base_simulated_values = [
            float(values_by_action.get(legal_actions[i], 0.0)) for i in range(n)
        ]
    else:
        # Deterministic fallback proxy in [-1, 1] when model values are absent.
        base_simulated_values = [(2.0 * priors[i]) - 1.0 for i in range(n)]
    if value_sign_by_action:
        signs = [-1.0 if int(value_sign_by_action.get(legal_actions[i], 1)) < 0 else 1.0 for i in range(n)]
        base_simulated_values = [v * s for v, s in zip(base_simulated_values, signs)]

    for _ in range(total_simulations):
        total_visits = sum(visits)
        best_idx = 0
        best_score = float("-inf")
        if forced_root_indices and min_root_k > 0:
            pending = [i for i in forced_root_indices if int(visits[i]) < min_root_k]
            if pending:
                best_idx = max(pending, key=lambda i: float(priors[i]))
                best_score = float("inf")
        root_sqrt = sqrt(max(1, total_visits))
        unclipped_q_values: list[float] = []
        clipped_q_values: list[float] = []
        for i in range(n):
            q_unclipped = (value_sums[i] / visits[i]) if visits[i] > 0 else 0.0
            q_value, q_clipped = _clip_q_value(q_unclipped, q_clip_abs)
            if q_clipped:
                q_guardrail_clipped_count += 1
            unclipped_q_values.append(float(q_unclipped))
            clipped_q_values.append(float(q_value))
        normalized_q_values, norm_applied = _normalize_root_q(
            clipped_q=clipped_q_values,
            unclipped_q=unclipped_q_values,
            mode=q_root_normalization_mode,
            strength=q_root_normalization_strength,
        )
        q_root_normalization_applied = bool(q_root_normalization_applied or norm_applied)
        q_root_score_spread = (
            float(max(normalized_q_values) - min(normalized_q_values))
            if normalized_q_values
            else 0.0
        )
        if best_score != float("inf"):
            for i in range(n):
                q_value = float(normalized_q_values[i])
                u_value = priors_c_puct[i] * (root_sqrt / (1 + visits[i]))
                score = q_value + u_value + precomputed_success_comps[i]
                if score > best_score:
                    best_score = score
                    best_idx = i

        simulated_value = base_simulated_values[best_idx]
        simulated_value = _rescale_value_estimate(simulated_value)
        if chance_enabled:
            sample_sum = 0.0
            for _sample_idx in range(chance_k):
                sample_v = float(simulated_value)
                if chance_noise_std > 0.0:
                    sample_v += float(random.gauss(0.0, chance_noise_std))
                sample_sum += float(sample_v)
            simulated_value = float(sample_sum / float(max(1, chance_k)))
        _, q_clipped = _clip_q_value(simulated_value, q_clip_abs)
        if q_clipped:
            q_guardrail_clipped_count += 1
        visits[best_idx] += 1
        value_sums[best_idx] += simulated_value

    visit_sum = sum(visits)
    probs = [v / visit_sum for v in visits]
    temp = max(float(temperature), 1e-6)
    if temp < 1e-3:
        probs_temp = [1.0 if i == max(range(n), key=lambda j: visits[j]) else 0.0 for i in range(n)]
    else:
        powered = [pow(max(v, 1e-12), 1.0 / temp) for v in probs]
        powered_sum = sum(powered)
        probs_temp = [p / powered_sum for p in powered]
    if temp < 1e-3:
        chosen_idx = max(range(n), key=lambda i: probs_temp[i])
    else:
        chosen_idx = int(random.choices(range(n), weights=probs_temp, k=1)[0])
    total_visits = sum(visits)
    root_sqrt = sqrt(max(1, total_visits))
    root_candidate_breakdown: list[dict[str, float]] = []
    unclipped_q_values: list[float] = []
    clipped_q_values: list[float] = []
    for i in range(n):
        q_unclipped = (value_sums[i] / visits[i]) if visits[i] > 0 else 0.0
        q_value, _ = _clip_q_value(q_unclipped, q_clip_abs)
        unclipped_q_values.append(float(q_unclipped))
        clipped_q_values.append(float(q_value))
    normalized_q_values, _ = _normalize_root_q(
        clipped_q=clipped_q_values,
        unclipped_q=unclipped_q_values,
        mode=q_root_normalization_mode,
        strength=q_root_normalization_strength,
    )
    chosen_score = 0.0
    for i in range(n):
        q_value = float(normalized_q_values[i])
        q_unclipped = float(unclipped_q_values[i]) if i < len(unclipped_q_values) else 0.0
        q_clipped = float(clipped_q_values[i]) if i < len(clipped_q_values) else q_value
        u_value = c_puct * priors[i] * (root_sqrt / (1 + visits[i]))
        success_prob, success_centered, success_component = _success_components(legal_actions[i])
        puct_score = float(q_value + u_value + success_component)
        if i == chosen_idx:
            chosen_score = puct_score
        root_candidate_breakdown.append(
            {
                "action_id": str(legal_actions[i]),
                "q_value": float(q_value),
                "q_unclipped": float(q_unclipped),
                "q_clipped": float(q_clipped),
                "q_norm_applied": bool(q_root_normalization_applied),
                "u_value": float(u_value),
                "success_prob_proxy": float(success_prob),
                "success_prob_centered": float(success_centered),
                "success_component": float(success_component),
                "puct_score": puct_score,
                "vp_race_bonus": float((vp_race_bonus_by_action or {}).get(str(legal_actions[i]), 0.0) or 0.0),
                "is_sterile": bool((sterile_action_mask or {}).get(str(legal_actions[i]), False)),
            }
        )

    return MCTSOutput(
        actions=legal_actions,
        visits=visits,
        probs=probs_temp,
        chosen_action=legal_actions[chosen_idx],
        chosen_score=float(chosen_score),
        q_guardrail_clipped_count=int(q_guardrail_clipped_count),
        q_guardrail_clip_limit=(float(q_clip_abs) if q_clip_abs is not None else None),
        q_root_score_spread=float(q_root_score_spread),
        q_root_normalization_applied=bool(q_root_normalization_applied),
        chance_samples_per_expansion=(int(chance_k) if chance_enabled else 1),
        sterile_branches_pruned_count=int(sterile_branches_pruned_count),
        root_candidate_breakdown=list(root_candidate_breakdown),
    )

