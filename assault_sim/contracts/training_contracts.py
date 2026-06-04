from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrajectoryStep:
    obs: Any
    action: int
    attack_mode: int
    logp: Any
    value: Any
    reward: float
    done: bool
    teacher: int
    l2: str
    l2_sampled: str


@dataclass(frozen=True)
class RolloutBatch:
    obs: list[Any]
    actions: list[int]
    attack_modes: list[int]
    logp: list[Any]
    values: list[Any]
    rewards: list[float]
    dones: list[bool]
    teacher_actions: list[int]
    l2: list[str]
    l2_sampled: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "obs": self.obs,
            "actions": self.actions,
            "attack_modes": self.attack_modes,
            "logp": self.logp,
            "values": self.values,
            "rewards": self.rewards,
            "dones": self.dones,
            "teacher_actions": self.teacher_actions,
            "l2": self.l2,
            "l2_sampled": self.l2_sampled,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "RolloutBatch":
        return RolloutBatch(
            obs=list(payload.get("obs", [])),
            actions=list(payload.get("actions", [])),
            attack_modes=list(payload.get("attack_modes", [])),
            logp=list(payload.get("logp", [])),
            values=list(payload.get("values", [])),
            rewards=list(payload.get("rewards", [])),
            dones=list(payload.get("dones", [])),
            teacher_actions=list(payload.get("teacher_actions", [])),
            l2=list(payload.get("l2", [])),
            l2_sampled=list(payload.get("l2_sampled", [])),
        )


@dataclass(frozen=True)
class EvalResult:
    winner: str | None
    vp: int
    steps: int
    avg_reward: float
    combat: dict[str, Any]
    side: dict[str, Any]
    l1: dict[str, Any]
    l1_efficiency: dict[str, Any]
    units: dict[str, Any]
    option_counts: dict[str, int]
    formation_counts: dict[str, int]
    strategy_option_map: dict[str, dict[str, int]]
    decision_alignment: dict[str, Any]
    events: list[dict[str, Any]]
    advanced: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "vp": self.vp,
            "steps": self.steps,
            "avg_reward": self.avg_reward,
            "combat": self.combat,
            "side": self.side,
            "l1": self.l1,
            "l1_efficiency": self.l1_efficiency,
            "units": self.units,
            "option_counts": self.option_counts,
            "formation_counts": self.formation_counts,
            "strategy_option_map": self.strategy_option_map,
            "decision_alignment": self.decision_alignment,
            "events": self.events,
            "advanced": self.advanced,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "EvalResult":
        return EvalResult(
            winner=payload.get("winner"),
            vp=int(payload.get("vp", 0)),
            steps=int(payload.get("steps", 0)),
            avg_reward=float(payload.get("avg_reward", 0.0)),
            combat=dict(payload.get("combat", {})),
            side=dict(payload.get("side", {})),
            l1=dict(payload.get("l1", {})),
            l1_efficiency=dict(payload.get("l1_efficiency", {})),
            units=dict(payload.get("units", {})),
            option_counts=dict(payload.get("option_counts", {})),
            formation_counts=dict(payload.get("formation_counts", {})),
            strategy_option_map=dict(payload.get("strategy_option_map", {})),
            decision_alignment=dict(payload.get("decision_alignment", {})),
            events=list(payload.get("events", [])),
            advanced=dict(payload.get("advanced", {})),
        )
