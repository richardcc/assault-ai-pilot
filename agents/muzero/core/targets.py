from __future__ import annotations

from typing import Any, List

from agents.muzero.core.replay import ReplaySample


def one_hot_policy(action_index: int, action_dim: int) -> List[float]:
    policy = [0.0] * action_dim
    if 0 <= action_index < action_dim:
        policy[action_index] = 1.0
    return policy


def build_sample(
    observation: Any,
    action_index: int,
    action_dim: int,
    reward: float,
    done: bool,
    info: dict | None = None,
) -> ReplaySample:
    value_target = reward if done else 0.0
    payload_info = {"done": done}
    if info:
        payload_info.update(info)
    return ReplaySample(
        observation=observation,
        policy_target=one_hot_policy(action_index, action_dim),
        value_target=value_target,
        reward_target=reward,
        info=payload_info,
    )
