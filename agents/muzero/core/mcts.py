from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
import random
from typing import Dict, List, Optional


@dataclass
class MCTSOutput:
    actions: List[str]
    visits: List[int]
    probs: List[float]
    chosen_action: str
    q_guardrail_clipped_count: int = 0
    q_guardrail_clip_limit: Optional[float] = None
    chance_samples_per_expansion: int = 1


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
    chance_mode: str = "off",
    chance_samples_per_expansion: int = 1,
    chance_value_noise_std: float = 0.0,
    min_root_visits_per_action: int = 0,
    min_root_visits_top_n: int = 0,
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
    if dirichlet_epsilon > 0.0:
        noise = [random.gammavariate(dirichlet_alpha, 1.0) for _ in range(n)]
        noise_sum = sum(noise)
        if noise_sum > 0.0:
            noise = [x / noise_sum for x in noise]
            priors = [
                ((1.0 - dirichlet_epsilon) * p) + (dirichlet_epsilon * e)
                for p, e in zip(priors, noise)
            ]

    values_lookup: Optional[Dict[str, float]] = None
    values_preclip_count = 0
    if values_by_action:
        values_lookup = {}
        for action_id, raw_value in dict(values_by_action).items():
            clipped_value, was_clipped = _clip_q_value(float(raw_value), q_clip_abs)
            values_lookup[str(action_id)] = float(clipped_value)
            if was_clipped:
                values_preclip_count += 1

    visits = [0] * n
    value_sums = [0.0] * n
    q_guardrail_clipped_count = int(values_preclip_count)
    chance_mode_key = str(chance_mode or "off").strip().lower()
    chance_k = max(1, int(chance_samples_per_expansion))
    chance_noise_std = max(0.0, float(chance_value_noise_std))
    chance_enabled = chance_mode_key in {"sampled_expectation", "sampled", "mc"} and chance_k > 1
    min_root_k = max(0, int(min_root_visits_per_action))
    configured_top_n = int(min_root_visits_top_n)
    # Contract parity with EZv2: top_n <= 0 means force coverage on all legal root actions.
    min_root_n = n if configured_top_n <= 0 else max(0, min(configured_top_n, n))
    forced_root_indices: list[int] = []
    if min_root_k > 0 and min_root_n > 0:
        forced_root_indices = sorted(range(n), key=lambda i: float(priors[i]), reverse=True)[:min_root_n]

    required_root_visits = int(min_root_k * min_root_n) if (min_root_k > 0 and min_root_n > 0) else 0
    total_simulations = max(1, int(num_simulations), int(required_root_visits))
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
        if best_score != float("inf"):
            for i in range(n):
                q_value = (value_sums[i] / visits[i]) if visits[i] > 0 else 0.0
                q_value, q_clipped = _clip_q_value(q_value, q_clip_abs)
                if q_clipped:
                    q_guardrail_clipped_count += 1
                u_value = c_puct * priors[i] * (root_sqrt / (1 + visits[i]))
                score = q_value + u_value
                if score > best_score:
                    best_score = score
                    best_idx = i

        if values_lookup is not None:
            simulated_value = float(values_lookup.get(legal_actions[best_idx], 0.0))
        else:
            # Deterministic fallback proxy in [-1, 1] when model values are absent.
            simulated_value = (2.0 * priors[best_idx]) - 1.0
        if value_sign_by_action:
            sign = int(value_sign_by_action.get(legal_actions[best_idx], 1))
            simulated_value *= -1.0 if sign < 0 else 1.0
        if chance_enabled:
            sample_sum = 0.0
            for _sample_idx in range(chance_k):
                sample_v = float(simulated_value)
                if chance_noise_std > 0.0:
                    sample_v += float(random.gauss(0.0, chance_noise_std))
                sample_sum += float(sample_v)
            simulated_value = float(sample_sum / float(max(1, chance_k)))
        simulated_value, q_clipped = _clip_q_value(simulated_value, q_clip_abs)
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

    return MCTSOutput(
        actions=legal_actions,
        visits=visits,
        probs=probs_temp,
        chosen_action=legal_actions[chosen_idx],
        q_guardrail_clipped_count=int(q_guardrail_clipped_count),
        q_guardrail_clip_limit=(float(q_clip_abs) if q_clip_abs is not None else None),
        chance_samples_per_expansion=(int(chance_k) if chance_enabled else 1),
    )
