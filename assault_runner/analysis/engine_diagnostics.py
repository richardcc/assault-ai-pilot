"""
Engine Diagnostics Collector.

This module observes the GAME ENGINE (not the agent) during play.

It answers questions like:
- Was an assault possible?
- Was VP capture possible?
- Was any offensive option available?
- Did the unit avoid attacking due to risk?

This collector is passive:
- DOES NOT affect gameplay
- DOES NOT use rewards
- DOES NOT influence decisions
"""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class StepEngineContext:
    """
    Diagnostic context for a single activation.
    """

    # Opportunities provided by the engine
    assault_possible: bool
    ranged_fire_possible: bool
    vp_capture_possible: bool
    safe_move_possible: bool

    # Decision info
    chosen_action: str
    offensive_action_available: bool
    avoided_attack: bool

    # Tactical risk indicators
    zoc_risk: float
    reaction_fire_risk: float


@dataclass
class EngineDiagnosticsCollector:
    """
    Collects engine-level diagnostics during a single game session.
    """

    steps: List[StepEngineContext] = field(default_factory=list)

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def record_step(
        self,
        *,
        assault_possible: bool,
        ranged_fire_possible: bool,
        vp_capture_possible: bool,
        safe_move_possible: bool,
        chosen_action: str,
        offensive_action_available: bool,
        avoided_attack: bool,
        zoc_risk: float,
        reaction_fire_risk: float,
    ) -> None:
        """
        Records diagnostic information for one activation.
        """

        context = StepEngineContext(
            assault_possible=assault_possible,
            ranged_fire_possible=ranged_fire_possible,
            vp_capture_possible=vp_capture_possible,
            safe_move_possible=safe_move_possible,
            chosen_action=chosen_action,
            offensive_action_available=offensive_action_available,
            avoided_attack=avoided_attack,
            zoc_risk=zoc_risk,
            reaction_fire_risk=reaction_fire_risk,
        )

        self.steps.append(context)

    # --------------------------------------------------
    # Aggregation helpers (used later)
    # --------------------------------------------------

    def count(self, attr: str) -> int:
        """
        Counts how many steps had attr == True.
        """
        return sum(1 for s in self.steps if getattr(s, attr))

    def ratio(self, attr: str) -> float:
        """
        Ratio of steps where attr == True.
        """
        if not self.steps:
            return 0.0
        return self.count(attr) / len(self.steps)

    def total_steps(self) -> int:
        return len(self.steps)

    # --------------------------------------------------
    # Debug export (raw)
    # --------------------------------------------------

    def to_dict(self) -> Dict:
        """
        Raw export of all step contexts.
        """
        return {
            "steps": [
                {
                    "assault_possible": s.assault_possible,
                    "ranged_fire_possible": s.ranged_fire_possible,
                    "vp_capture_possible": s.vp_capture_possible,
                    "safe_move_possible": s.safe_move_possible,
                    "chosen_action": s.chosen_action,
                    "offensive_action_available": s.offensive_action_available,
                    "avoided_attack": s.avoided_attack,
                    "zoc_risk": s.zoc_risk,
                    "reaction_fire_risk": s.reaction_fire_risk,
                }
                for s in self.steps
            ]
        }