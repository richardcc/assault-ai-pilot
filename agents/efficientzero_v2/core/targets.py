from __future__ import annotations

from typing import Any

from agents.efficientzero_v2.core.replay import ReplaySample


def one_hot_policy(action_index: int, action_dim: int) -> list[float]:
    policy = [0.0] * int(action_dim)
    if 0 <= int(action_index) < int(action_dim):
        policy[int(action_index)] = 1.0
    return policy


def build_sample(
    observation: Any,
    action_index: int,
    action_dim: int,
    reward: float,
    done: bool,
    info: dict | None = None,
) -> ReplaySample:
    value_target = float(reward) if bool(done) else 0.0
    payload_info: dict = {"done": bool(done)}
    if info:
        payload_info.update(info)
    return ReplaySample(
        observation=observation,
        policy_target=one_hot_policy(int(action_index), int(action_dim)),
        value_target=float(value_target),
        reward_target=float(reward),
        info=payload_info,
    )

