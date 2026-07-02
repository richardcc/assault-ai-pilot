from __future__ import annotations

from typing import Callable, Dict

from voec_sim.core.simulator import VOECSimulator
from voec_sim.ui_contract.events import EpisodeTimeline, SCHEMA_VERSION, TransitionEvent


def build_episode_timeline(
    sim: VOECSimulator,
    scenario_id: str,
    seed: int,
    policy_fn: Callable[[list[str]], str],
    max_steps: int = 200,
) -> EpisodeTimeline:
    sim.new_episode(scenario_id=scenario_id, seed=seed)
    transitions: list[Dict] = []

    for _ in range(max_steps):
        legal = sim.legal_actions()
        if not legal:
            break
        action_id = policy_fn(legal)
        tr = sim.step(action_id)
        evt = TransitionEvent.from_snapshot(tr.state, tr.action_id, tr.reward, tr.done)
        transitions.append(evt.to_dict())
        if tr.done:
            break

    return EpisodeTimeline(
        schema_version=SCHEMA_VERSION,
        scenario_id=scenario_id,
        seed=seed,
        transitions=transitions,
    )
