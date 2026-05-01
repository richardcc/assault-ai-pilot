from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction
from assault_model.rules.movement_rules import MovementRules
from assault_model.rules.movement_outcome import MovementOutcome
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class ActionCatalog:
    """
    Canonical ActionCatalog of the MODEL.

    SOLO SOLDADOS (vehículos desactivados por ahora).

    Invariants:
    - Every MoveAction represents a REAL movement.
    - Close Combat is triggered by movement into an enemy hex.
    - No empty or no-op actions are ever generated.
    """

    def __init__(self, game_state):
        self.gs = game_state

    def actions(self):
        # Actions are always relative to the CURRENT active unit
        active = self.gs.active_unit

        # Defensive fallback
        if active is None:
            return [WaitAction(None)]

        actions = []

        _trace(
            "ACTION_CATALOG_START",
            active_unit=getattr(active, "unit_id", None),
        )

        # ----------------------------------
        # MOVEMENT-DRIVEN ACTIONS
        # ----------------------------------
        # MovementRules returns semantic movement paths
        movement_paths = MovementRules.get_legal_paths(self.gs, active)

        for mp in movement_paths:

            _trace(
                "MOVEMENT_PATH_EVAL",
                unit=getattr(active, "unit_id", None),
                outcome=str(mp.outcome),
                target=getattr(mp, "target_unit_id", None),
            )

            # ------------------------------
            # Normal movement (empty hex)
            # ------------------------------
            if mp.outcome == MovementOutcome.END_IN_EMPTY_HEX:
                _trace(
                    "ACTION_ADD",
                    action="MoveAction",
                    unit=active.unit_id,
                )

                actions.append(
                    MoveAction(
                        unit_id=active.unit_id,
                        path=mp.path,
                    )
                )

            # ------------------------------
            # Enemy hex → Close Combat (ASSAULT)
            # ------------------------------
            elif mp.outcome == MovementOutcome.END_IN_ENEMY_HEX:
                _trace(
                    "ACTION_ADD",
                    action="AssaultAction",
                    unit=active.unit_id,
                    target=mp.target_unit_id,
                )

                actions.append(
                    AssaultAction(
                        unit_id=active.unit_id,
                        target_id=mp.target_unit_id,
                    )
                )

            # Friendly vehicle outcome is ignored on purpose
            # (vehicles not enabled yet)

        # ----------------------------------
        # WAIT (always valid)
        # ----------------------------------
        _trace(
            "ACTION_ADD",
            action="WaitAction",
            unit=active.unit_id,
        )

        actions.append(WaitAction(active.unit_id))

        _trace(
            "ACTION_CATALOG_END",
            unit=active.unit_id,
            action_count=len(actions),
        )

        return actions