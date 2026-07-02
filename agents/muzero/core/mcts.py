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

    visits = [0] * n
    value_sums = [0.0] * n

    for _ in range(max(1, num_simulations)):
        total_visits = sum(visits)
        best_idx = 0
        best_score = float("-inf")
        root_sqrt = sqrt(max(1, total_visits))
        for i in range(n):
            q_value = (value_sums[i] / visits[i]) if visits[i] > 0 else 0.0
            u_value = c_puct * priors[i] * (root_sqrt / (1 + visits[i]))
            score = q_value + u_value
            if score > best_score:
                best_score = score
                best_idx = i

        if values_by_action:
            simulated_value = float(values_by_action.get(legal_actions[best_idx], 0.0))
        else:
            # Deterministic fallback proxy in [-1, 1] when model values are absent.
            simulated_value = (2.0 * priors[best_idx]) - 1.0
        if value_sign_by_action:
            sign = int(value_sign_by_action.get(legal_actions[best_idx], 1))
            simulated_value *= -1.0 if sign < 0 else 1.0
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
    chosen_idx = max(range(n), key=lambda i: probs_temp[i])

    return MCTSOutput(
        actions=legal_actions,
        visits=visits,
        probs=probs_temp,
        chosen_action=legal_actions[chosen_idx],
    )
