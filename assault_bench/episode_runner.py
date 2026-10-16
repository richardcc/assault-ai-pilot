from __future__ import annotations

from typing import Any, Tuple

from assault_bench.episode_execution import execute_benchmark_seed_task
from assault_bench.model_state_utils import load_state_dict


def benchmark_seed_task(payload: dict) -> Tuple:
    return execute_benchmark_seed_task(
        payload=payload,
        load_state_dict_fn=load_state_dict,
        run_episode_with_policy_fn=run_episode_with_policy,
    )


def benchmark_seed_task_batch(payload_batch: list[dict]) -> list[Tuple]:
    rows: list[Tuple] = []
    for payload in list(payload_batch or []):
        rows.append(
            execute_benchmark_seed_task(
                payload=dict(payload or {}),
                load_state_dict_fn=load_state_dict,
                run_episode_with_policy_fn=run_episode_with_policy,
            )
        )
    return rows


def run_episode_with_policy(*, adapter, **kwargs) -> Any:
    from assault_bench.episode_runner_impl import _run_episode_with_policy_impl

    return _run_episode_with_policy_impl(adapter=adapter, **kwargs)
