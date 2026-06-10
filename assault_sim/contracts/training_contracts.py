from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


PlanIntent = Literal["CAPTURE", "DENY", "ATTRIT", "PRESERVE", "UNKNOWN"]
UnitRole = Literal["ASSAULT", "SUPPORT_FIRE", "SCREEN", "HOLD_VP", "RESERVE", "UNKNOWN"]
PlanBudgetState = Literal["UNBOUNDED", "BUDGETED", "EXHAUSTED", "UNKNOWN"]


class PlanStateContract(TypedDict):
    intent: PlanIntent
    unit_role: UnitRole
    focus_vp_id: str | None
    plan_step_id: int
    budget_state: PlanBudgetState
    plan_progress_stub: float
    intent_alignment_stub: float


def normalize_plan_state(payload: dict[str, Any] | None) -> PlanStateContract:
    data = dict(payload or {})

    valid_intents = {"CAPTURE", "DENY", "ATTRIT", "PRESERVE", "UNKNOWN"}
    valid_roles = {"ASSAULT", "SUPPORT_FIRE", "SCREEN", "HOLD_VP", "RESERVE", "UNKNOWN"}
    valid_budget = {"UNBOUNDED", "BUDGETED", "EXHAUSTED", "UNKNOWN"}

    intent_raw = str(data.get("intent", "UNKNOWN") or "UNKNOWN").upper()
    role_raw = str(data.get("unit_role", "UNKNOWN") or "UNKNOWN").upper()
    budget_raw = str(data.get("budget_state", "UNBOUNDED") or "UNBOUNDED").upper()

    intent: PlanIntent = intent_raw if intent_raw in valid_intents else "UNKNOWN"
    unit_role: UnitRole = role_raw if role_raw in valid_roles else "UNKNOWN"
    budget_state: PlanBudgetState = budget_raw if budget_raw in valid_budget else "UNKNOWN"

    focus_vp_id_raw = data.get("focus_vp_id")
    focus_vp_id = str(focus_vp_id_raw) if focus_vp_id_raw not in (None, "") else None

    try:
        plan_step_id = max(0, int(data.get("plan_step_id", 0)))
    except Exception:
        plan_step_id = 0

    try:
        plan_progress_stub = float(data.get("plan_progress_stub", 0.0))
    except Exception:
        plan_progress_stub = 0.0
    plan_progress_stub = max(-1.0, min(1.0, plan_progress_stub))

    try:
        intent_alignment_stub = float(data.get("intent_alignment_stub", 0.0))
    except Exception:
        intent_alignment_stub = 0.0
    intent_alignment_stub = max(0.0, min(1.0, intent_alignment_stub))

    return {
        "intent": intent,
        "unit_role": unit_role,
        "focus_vp_id": focus_vp_id,
        "plan_step_id": plan_step_id,
        "budget_state": budget_state,
        "plan_progress_stub": plan_progress_stub,
        "intent_alignment_stub": intent_alignment_stub,
    }


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
    end_reason: str | None
    rl_result: str
    tracked_result: str | None
    vp: int
    vp_by_side: dict[str, int]
    vp_total_in_play: int
    steps: int
    avg_reward: float
    combat: dict[str, Any]
    victory_level: dict[str, Any] | None
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
    mission: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "end_reason": self.end_reason,
            "rl_result": self.rl_result,
            "tracked_result": self.tracked_result,
            "vp": self.vp,
            "vp_by_side": self.vp_by_side,
            "vp_total_in_play": self.vp_total_in_play,
            "steps": self.steps,
            "avg_reward": self.avg_reward,
            "combat": self.combat,
            "victory_level": self.victory_level,
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
            "mission": self.mission,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "EvalResult":
        return EvalResult(
            winner=payload.get("winner"),
            end_reason=payload.get("end_reason"),
            rl_result=str(payload.get("rl_result", "draw")),
            tracked_result=payload.get("tracked_result"),
            vp=int(payload.get("vp", 0)),
            vp_by_side=dict(payload.get("vp_by_side", {})),
            vp_total_in_play=int(payload.get("vp_total_in_play", 0)),
            steps=int(payload.get("steps", 0)),
            avg_reward=float(payload.get("avg_reward", 0.0)),
            combat=dict(payload.get("combat", {})),
            victory_level=(
                dict(payload.get("victory_level", {}))
                if payload.get("victory_level") is not None
                else None
            ),
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
            mission=dict(payload.get("mission", {})),
        )
