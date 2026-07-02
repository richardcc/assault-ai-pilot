from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from voec_sim.contracts.types import StateSnapshot


SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class TransitionEvent:
    schema_version: str
    turn: int
    to_play: str | None
    action_id: str
    reward: float
    done: bool
    units: List[Dict[str, Any]]

    @classmethod
    def from_snapshot(
        cls, snapshot: StateSnapshot, action_id: str, reward: float, done: bool
    ) -> "TransitionEvent":
        return cls(
            schema_version=SCHEMA_VERSION,
            turn=snapshot.turn,
            to_play=snapshot.to_play,
            action_id=action_id,
            reward=reward,
            done=done,
            units=[asdict(u) for u in snapshot.units],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionResolution:
    schema_version: str
    action_id: str
    legal: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EpisodeTimeline:
    schema_version: str
    scenario_id: str
    seed: int
    transitions: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
