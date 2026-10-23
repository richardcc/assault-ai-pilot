from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class OutcomeClass(str, Enum):
    """
    Canonical outcome classification for scenario evaluation.
    Enforces consistent types across engine, simulator, benchmark, and reporting.
    """
    TOTAL_VICTORY = "total_victory"
    VICTORY = "victory"
    DRAW = "draw"
    DEFEAT = "defeat"
    TOTAL_DEFEAT = "total_defeat"
    UNKNOWN = "unknown"

    @property
    def dual(self) -> "OutcomeClass":
        """
        Opponent outcome in a zero-sum two-player confrontation.
        Guarantees bilateral consistency:
        total_victory <-> total_defeat
        victory       <-> defeat
        draw          <-> draw
        """
        if self == OutcomeClass.TOTAL_VICTORY:
            return OutcomeClass.TOTAL_DEFEAT
        if self == OutcomeClass.VICTORY:
            return OutcomeClass.DEFEAT
        if self == OutcomeClass.DRAW:
            return OutcomeClass.DRAW
        if self == OutcomeClass.DEFEAT:
            return OutcomeClass.VICTORY
        if self == OutcomeClass.TOTAL_DEFEAT:
            return OutcomeClass.TOTAL_VICTORY
        return OutcomeClass.UNKNOWN

    @property
    def score(self) -> int:
        """Normalized outcome score: +1 for win, 0 for draw, -1 for loss."""
        if self in (OutcomeClass.TOTAL_VICTORY, OutcomeClass.VICTORY):
            return 1
        if self in (OutcomeClass.TOTAL_DEFEAT, OutcomeClass.DEFEAT):
            return -1
        return 0

    @property
    def is_win(self) -> bool:
        return self in (OutcomeClass.TOTAL_VICTORY, OutcomeClass.VICTORY)

    @property
    def is_loss(self) -> bool:
        return self in (OutcomeClass.TOTAL_DEFEAT, OutcomeClass.DEFEAT)

    @property
    def is_draw(self) -> bool:
        return self == OutcomeClass.DRAW

    @classmethod
    def from_str(cls, val: Any) -> "OutcomeClass":
        """
        Parse outcome class from Italian or English strings.
        Supports both raw scenario results ('Vittoria Totale', 'Pareggio')
        and serialized identifiers ('total_victory', 'win', 'defeat').
        """
        if isinstance(val, OutcomeClass):
            return val
        s = str(val or "").strip().lower().replace("_", " ")
        if s in ("total victory", "vittoria totale"):
            return cls.TOTAL_VICTORY
        if s in ("victory", "vittoria", "win"):
            return cls.VICTORY
        if s in ("draw", "pareggio", "tie"):
            return cls.DRAW
        if s in ("total defeat", "sconfitta totale"):
            return cls.TOTAL_DEFEAT
        if s in ("defeat", "sconfitta", "loss", "lose"):
            return cls.DEFEAT
        return cls.UNKNOWN


@dataclass(frozen=True)
class ScenarioOutcomeResult:
    """
    Structured result of scenario outcome resolution.
    Serves as Single Source of Truth for game engine, RL environments,
    benchmarking suites, and reporting dashboards.
    """
    winner: Optional[str]
    end_reason: str
    tracked_side: Optional[str]
    metric: Optional[str]
    timing: Optional[str]
    captured: int
    captured_by_side: Dict[str, int] = field(default_factory=dict)
    initial_captured_by_side: Dict[str, int] = field(default_factory=dict)
    vp_score_by_side: Dict[str, int] = field(default_factory=dict)
    objectives_total: int = 0
    outcome_class: OutcomeClass = OutcomeClass.UNKNOWN
    outcome_score: int = 0
    result_text: str = ""
    outcome_class_by_side: Dict[str, str] = field(default_factory=dict)
    outcome_score_by_side: Dict[str, int] = field(default_factory=dict)
    result_text_by_side: Dict[str, str] = field(default_factory=dict)
    next_scenario: Optional[str] = None
    next_page: Optional[int] = None
    matched_table_row: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict matching producer-consumer reporting contracts."""
        return {
            "winner": self.winner,
            "end_reason": self.end_reason,
            "tracked_side": self.tracked_side,
            "metric": self.metric,
            "timing": self.timing,
            "captured": self.captured,
            "captured_by_side": dict(self.captured_by_side),
            "initial_captured_by_side": dict(self.initial_captured_by_side),
            "vp_score_by_side": dict(self.vp_score_by_side),
            "objectives_total": self.objectives_total,
            "outcome_class": self.outcome_class.value,
            "outcome_score": self.outcome_score,
            "result": self.result_text,
            "result_text": self.result_text,
            "outcome_class_by_side": dict(self.outcome_class_by_side),
            "outcome_score_by_side": dict(self.outcome_score_by_side),
            "result_text_by_side": dict(self.result_text_by_side),
            "next_scenario": self.next_scenario,
            "next_page": self.next_page,
            "matched_table_row": dict(self.matched_table_row) if self.matched_table_row else None,
        }


def _canonical_result_text_for_class(cls: OutcomeClass) -> str:
    if cls == OutcomeClass.TOTAL_VICTORY:
        return "Vittoria Totale"
    if cls == OutcomeClass.VICTORY:
        return "Vittoria"
    if cls == OutcomeClass.DRAW:
        return "Pareggio"
    if cls == OutcomeClass.DEFEAT:
        return "Sconfitta"
    if cls == OutcomeClass.TOTAL_DEFEAT:
        return "Sconfitta totale"
    return cls.value.title()


def evaluate_scenario_outcome(
    state: Any = None,
    scenario: Any = None,
    final_vp_by_side: Optional[Dict[str, int]] = None,
    alive_sides: Optional[Iterable[str]] = None,
    end_reason_override: Optional[str] = None,
) -> ScenarioOutcomeResult:
    """
    Centralized, dynamic outcome evaluator.
    Evaluates scenario JSON victory conditions (`victory_outcomes` and `vp`).
    """
    # 1. Extract victory_outcomes configuration from scenario
    vo = getattr(scenario, "victory_outcomes", None)
    if vo is None and isinstance(scenario, dict):
        vo = scenario.get("victory_outcomes")
    vo = dict(vo or {})

    tracked_side = str(vo.get("tracked_side", "")).strip().upper() or None
    metric = str(vo.get("metric", "")).strip() or None
    timing = str(vo.get("timing", "")).strip() or None
    table = list(vo.get("table", []) or [])

    # 2. Extract sides participating
    sides_set: set[str] = set()
    if state is not None:
        if hasattr(state, "side_to_ownership") and state.side_to_ownership:
            sides_set.update(str(s).upper() for s in state.side_to_ownership.keys())
        if hasattr(state, "turn_order") and state.turn_order:
            sides_set.update(str(s).upper() for s in state.turn_order)
        if hasattr(state, "units") and state.units:
            sides_set.update(str(u.side).upper() for u in state.units)
    if scenario is not None:
        units = getattr(scenario, "units", None) or (scenario.get("units") if isinstance(scenario, dict) else None) or []
        for u in units:
            side_val = getattr(u, "side", None) or (u.get("side") if isinstance(u, dict) else None)
            if side_val:
                sides_set.add(str(side_val).upper())
    if final_vp_by_side:
        sides_set.update(str(s).upper() for s in final_vp_by_side.keys())
    if tracked_side:
        sides_set.add(tracked_side)

    all_sides = sorted(sides_set)

    # 3. Extract VP objectives and control
    captured_by_side: Dict[str, int] = {s: 0 for s in all_sides}
    initial_captured_by_side: Dict[str, int] = {s: 0 for s in all_sides}
    vp_score_by_side: Dict[str, int] = {s: 0 for s in all_sides}
    objectives_total = 0

    points = []
    if state is not None and getattr(state, "victory", None) and hasattr(state.victory, "points"):
        points = list(state.victory.points)
    elif scenario is not None:
        vp_obj = getattr(scenario, "vp_conditions", None) or (scenario.get("vp") if isinstance(scenario, dict) else None)
        if hasattr(vp_obj, "points"):
            points = list(vp_obj.points)

    if points and state is not None and hasattr(state, "hex_states") and hasattr(state, "side_to_ownership"):
        objectives_total = len(points)
        side_to_ownership = state.side_to_ownership
        ownership_to_side = getattr(state, "ownership_to_side", None)
        if ownership_to_side is None:
            ownership_to_side = {own: str(s).upper() for s, own in side_to_ownership.items()}
        for vp in points:
            init_owner = str(getattr(vp, "initial_owner", "") or "").strip().upper()
            if init_owner:
                initial_captured_by_side[init_owner] = initial_captured_by_side.get(init_owner, 0) + 1

            hs = state.hex_states.get(vp.hex_coords)
            if hs is None:
                continue
            owner_side = ownership_to_side.get(hs.ownership)
            if owner_side:
                captured_by_side[owner_side] = captured_by_side.get(owner_side, 0) + 1
                val = int(getattr(vp, "per_turn", 2) or 2)
                vp_score_by_side[owner_side] = vp_score_by_side.get(owner_side, 0) + val
    elif final_vp_by_side:
        for s, count in final_vp_by_side.items():
            s_up = str(s).upper()
            captured_by_side[s_up] = int(count)
        objectives_total = sum(captured_by_side.values())
        for row in table:
            cap_cfg = row.get("captured", {}) if isinstance(row, dict) else {}
            if isinstance(cap_cfg, dict) and "max" in cap_cfg:
                try:
                    objectives_total = max(objectives_total, int(cap_cfg["max"]))
                except Exception:
                    pass

    # 4. Resolve objective table if configured
    has_objective_table = bool(tracked_side and table)
    if has_objective_table:
        tracked_captured = int(captured_by_side.get(tracked_side, 0))
        matched_row: Optional[Dict[str, Any]] = None
        for row in table:
            if not isinstance(row, dict):
                continue
            cap_range = row.get("captured", {}) or {}
            try:
                min_cap = int(cap_range.get("min", -10**9))
                max_cap = int(cap_range.get("max", 10**9))
            except Exception:
                continue
            if min_cap <= tracked_captured <= max_cap:
                matched_row = row
                break

        if matched_row is None and table:
            matched_row = table[-1]

        raw_class = (matched_row or {}).get("outcome_class")
        raw_result = str((matched_row or {}).get("result", "")).strip()
        outcome_class = OutcomeClass.from_str(raw_class) if raw_class else OutcomeClass.from_str(raw_result)

        raw_score = (matched_row or {}).get("outcome_score")
        if raw_score is None:
            raw_score = (matched_row or {}).get("result_score", (matched_row or {}).get("score"))
        outcome_score = int(raw_score) if raw_score is not None else outcome_class.score

        result_text = raw_result or _canonical_result_text_for_class(outcome_class)
        next_scenario = str((matched_row or {}).get("next_scenario", "")).strip() or None
        next_page = int((matched_row or {}).get("next_page", 0)) if (matched_row or {}).get("next_page") is not None else None

        opponents = [s for s in all_sides if s != tracked_side]

        # Winner derivation from tracked perspective:
        if outcome_class.is_win:
            winner = tracked_side
        elif outcome_class.is_draw:
            if os.getenv("ASSAULT_OBJECTIVE_PAREGGIO_IS_WIN", "0") == "1":
                winner = tracked_side
            else:
                winner = None
        elif outcome_class.is_loss:
            winner = opponents[0] if len(opponents) == 1 else None
        else:
            winner = None

        if os.getenv("ASSAULT_OBJECTIVE_PAREGGIO_IS_WIN", "0") == "1" and outcome_class.is_draw:
            end_reason = "objective_outcome_resolved_draw_as_win"
        else:
            end_reason = end_reason_override or "objective_outcome_resolved"

        outcome_class_by_side = {tracked_side: outcome_class.value}
        outcome_score_by_side = {tracked_side: outcome_score}
        result_text_by_side = {tracked_side: result_text}

        # Bilateral zero-sum coherence for opposing side(s)
        dual_class = outcome_class.dual
        dual_score = dual_class.score
        dual_text = _canonical_result_text_for_class(dual_class)
        for opp in opponents:
            outcome_class_by_side[opp] = dual_class.value
            outcome_score_by_side[opp] = dual_score
            result_text_by_side[opp] = dual_text

        return ScenarioOutcomeResult(
            winner=winner,
            end_reason=end_reason,
            tracked_side=tracked_side,
            metric=metric,
            timing=timing,
            captured=tracked_captured,
            captured_by_side=captured_by_side,
            initial_captured_by_side=initial_captured_by_side,
            vp_score_by_side=vp_score_by_side,
            objectives_total=objectives_total,
            outcome_class=outcome_class,
            outcome_score=outcome_score,
            result_text=result_text,
            outcome_class_by_side=outcome_class_by_side,
            outcome_score_by_side=outcome_score_by_side,
            result_text_by_side=result_text_by_side,
            next_scenario=next_scenario,
            next_page=next_page,
            matched_table_row=matched_row,
        )

    # 5. Fallback for scenarios without objective tables (annihilation or standard VP tracker)
    alive = set(str(s).upper() for s in (alive_sides or []))
    if not alive and state is not None and hasattr(state, "units"):
        alive = {str(u.side).upper() for u in state.units if u.alive}

    if len(alive) == 1:
        winner = next(iter(alive))
        end_reason = end_reason_override or "last_side_standing"
        outcome_class = OutcomeClass.VICTORY
        outcome_score = 1
        result_text = "Vittoria"
        outcome_class_by_side = {
            s: OutcomeClass.VICTORY.value if s == winner else OutcomeClass.DEFEAT.value
            for s in all_sides
        }
        outcome_score_by_side = {s: 1 if s == winner else -1 for s in all_sides}
        result_text_by_side = {
            s: "Vittoria" if s == winner else "Sconfitta"
            for s in all_sides
        }
    elif len(alive) == 0 and state is not None and getattr(state, "done", False):
        winner = None
        end_reason = end_reason_override or "all_units_destroyed"
        outcome_class = OutcomeClass.DRAW
        outcome_score = 0
        result_text = "Pareggio"
        outcome_class_by_side = {s: OutcomeClass.DRAW.value for s in all_sides}
        outcome_score_by_side = {s: 0 for s in all_sides}
        result_text_by_side = {s: "Pareggio" for s in all_sides}
    else:
        scores = {s: sc for s, sc in vp_score_by_side.items() if sc > 0}
        if state is not None and getattr(state, "vp_tracker", None):
            tracker = state.vp_tracker
            side_to_ownership = getattr(state, "side_to_ownership", {})
            for side, ownership in side_to_ownership.items():
                s_up = str(side).upper()
                tracker_score = tracker.score.get(ownership, 0)
                if tracker_score > 0 or s_up not in scores:
                    scores[s_up] = tracker_score
        if not scores or all(v == 0 for v in scores.values()):
            scores = dict(captured_by_side)

        best_score = max(scores.values()) if scores else 0
        top_sides = [s for s, sc in scores.items() if sc == best_score]
        if len(top_sides) == 1:
            winner = top_sides[0]
            outcome_class = OutcomeClass.VICTORY
            outcome_score = 1
            result_text = "Vittoria"
            outcome_class_by_side = {
                s: OutcomeClass.VICTORY.value if s == winner else OutcomeClass.DEFEAT.value
                for s in all_sides
            }
            outcome_score_by_side = {s: 1 if s == winner else -1 for s in all_sides}
            result_text_by_side = {
                s: "Vittoria" if s == winner else "Sconfitta"
                for s in all_sides
            }
        else:
            winner = None
            outcome_class = OutcomeClass.DRAW
            outcome_score = 0
            result_text = "Pareggio"
            outcome_class_by_side = {s: OutcomeClass.DRAW.value for s in all_sides}
            outcome_score_by_side = {s: 0 for s in all_sides}
            result_text_by_side = {s: "Pareggio" for s in all_sides}
        end_reason = end_reason_override or "max_turns_vp"

    tracked_captured = int(captured_by_side.get(tracked_side, 0)) if tracked_side else 0
    return ScenarioOutcomeResult(
        winner=winner,
        end_reason=end_reason,
        tracked_side=tracked_side,
        metric=metric,
        timing=timing,
        captured=tracked_captured,
        captured_by_side=captured_by_side,
        initial_captured_by_side=initial_captured_by_side,
        vp_score_by_side=vp_score_by_side,
        objectives_total=objectives_total,
        outcome_class=outcome_class,
        outcome_score=outcome_score,
        result_text=result_text,
        outcome_class_by_side=outcome_class_by_side,
        outcome_score_by_side=outcome_score_by_side,
        result_text_by_side=result_text_by_side,
    )
