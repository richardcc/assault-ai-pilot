from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction

# Direct ranged fire action (Rulebook §10.0–§10.2)
from assault_model.actions.ranged_direct import RangedDirectAttack

from assault_model.rules.movement_rules import MovementRules
from assault_model.rules.movement_outcome import MovementOutcome

# Canonical hex distance utility
from assault_model.map.hex_utils import hex_distance

# Line of sight rules (temporary RF-R02 implementation)
from assault_model.combat.line_of_sight import has_line_of_sight

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

    Responsibilities:
    - Declare which actions are legal
    - Never decide combat resolution details

    Invariants:
    - Every MoveAction represents a REAL movement
    - Close Combat is triggered only by movement into an enemy hex
    - Ranged Fire is an explicit declared action
    - No empty or no-op actions are generated
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
            unit=active.unit_id,
        )

        # ----------------------------------
        # MOVEMENT-DRIVEN ACTIONS
        # ----------------------------------
        movement_paths = MovementRules.get_legal_paths(self.gs, active)

        for mp in movement_paths:

            _trace(
                "MOVEMENT_PATH_EVAL",
                unit=active.unit_id,
                outcome=str(mp.outcome),
                target=mp.target_unit_id,
            )

            # ------------------------------
            # Normal movement
            # ------------------------------
            if mp.outcome == MovementOutcome.END_IN_EMPTY_HEX:
                actions.append(
                    MoveAction(
                        unit_id=active.unit_id,
                        path=mp.path,
                    )
                )

            # ------------------------------
            # Close combat via movement
            # ------------------------------
            elif mp.outcome == MovementOutcome.END_IN_ENEMY_HEX:
                target = next(
                    (u for u in self.gs.units if u.unit_id == mp.target_unit_id),
                    None,
                )

                if target is not None and target.alive:
                    actions.append(
                        AssaultAction(
                            unit_id=active.unit_id,
                            target_id=mp.target_unit_id,
                        )
                    )

        # ----------------------------------
        # RANGED DIRECT FIRE ACTIONS
        # ----------------------------------
        actions.extend(self._ranged_fire_actions(active))

        # ----------------------------------
        # WAIT (always valid)
        # ----------------------------------
        actions.append(WaitAction(active.unit_id))

        _trace(
            "ACTION_CATALOG_END",
            unit=active.unit_id,
            action_count=len(actions),
        )

        return actions

    # ==================================================
    # RANGED DIRECT FIRE SUPPORT
    # ==================================================
    def _ranged_fire_actions(self, active):
        """
        Declare direct ranged fire actions.

        IMPORTANT:
        - No dice
        - No profiles
        - No weapon logic

        Combat resolution (range bands, dice pools, traits)
        is handled entirely by the combat resolver
        using the unit cards (same as close combat).
        """
        actions = []

        # Unit must be capable of firing
        if not getattr(active, "can_fire", True):
            return actions

        for other in self.gs.units:
            # Ignore friendly units
            if other.side == active.side:
                continue

            # Ignore dead units
            if not other.alive:
                continue

            # Range legality check
            if not self._in_weapon_range(active, other):
                continue

            # Line of sight check
            if not self._has_line_of_sight(active, other):
                continue

            _trace(
                "ACTION_ADD",
                action="RangedDirectAttack",
                attacker=active.unit_id,
                target=other.unit_id,
            )

            # ✅ Only DECLARE the action.
            # ✅ Resolver determines dice by distance using unit cards.
            actions.append(
                RangedDirectAttack(
                    active.unit_id,
                    other.unit_id,
                )
            )

        return actions

    def _in_weapon_range(self, attacker, target):
        """
        Coarse weapon range legality.

        Fine-grained dice selection by distance
        happens in the combat resolver via unit cards.
        """
        distance = hex_distance(attacker.position, target.position)

        # Temporary legality limits (Phase 01 / 01.5)
        min_range = getattr(attacker, "weapon_min_range", 1)
        max_range = getattr(attacker, "weapon_range", 10)

        return min_range <= distance <= max_range

    def _has_line_of_sight(self, attacker, target):
        """
        Check line of sight for direct fire.
        """
        return has_line_of_sight(attacker, target, self.gs.game_map)