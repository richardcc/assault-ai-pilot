from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class UnitSnapshot:
    unit_id: str
    unit_key: str
    unit_label: str
    art_ref: Optional[str]
    side: str
    q: Optional[int]
    r: Optional[int]
    hp: Optional[int]
    alive: bool


@dataclass(frozen=True)
class StateSnapshot:
    turn: int
    to_play: Optional[str]
    done: bool
    winner: Optional[str]
    end_reason: Optional[str]
    units: List[UnitSnapshot]


@dataclass(frozen=True)
class TransitionRecord:
    action_id: str
    reward: float
    done: bool
    info: Dict[str, Any]
    state: StateSnapshot
