from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction

# Direct ranged fire action
from assault_model.actions.ranged_direct import RangedDirectAttack

from assault_model.rules.movement_rules import MovementRules
from assault_model.rules.movement_outcome import MovementOutcome

from assault_model.map.hex_utils import hex_distance
from assault_model.combat.line_of_sight import has_line_of_sight

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class ActionCatalog:

    def __init__(self, game_state):
        self.gs = game_state

    def actions(self):
        active = self.gs.active_unit

        if active is None:
            return [WaitAction(None)]

        actions = []

        _trace(
            "ACTION_CATALOG_START",
            unit=active.unit_id,
        )

        # ----------------------------------
        # MOVEMENT
        # ----------------------------------
        movement_paths = MovementRules.get_legal_paths(self.gs, active)

        for mp in movement_paths:

            _trace(
                "MOVEMENT_PATH_EVAL",
                unit=active.unit_id,
                outcome=str(mp.outcome),
                target=mp.target_unit_id,
            )

            if mp.outcome == MovementOutcome.END_IN_EMPTY_HEX:
                actions.append(
                    MoveAction(
                        unit_id=active.unit_id,
                        path=mp.path,
                    )
                )

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
        # RANGED FIRE
        # ----------------------------------
        actions.extend(self._ranged_fire_actions(active))

        # ----------------------------------
        # WAIT
        # ----------------------------------
        actions.append(WaitAction(active.unit_id))

        _trace(
            "ACTION_CATALOG_END",
            unit=active.unit_id,
            action_count=len(actions),
        )

        return actions

    # ==================================================
    # RANGED FIRE (DIRECT + INDIRECT)
    # ==================================================
    def _ranged_fire_actions(self, active):

        actions = []

        if not getattr(active, "can_fire", True):
            return actions

        for other in self.gs.units:

            if other.side == active.side:
                continue

            if not other.alive:
                continue

            # ✅ Distance
            distance = hex_distance(active.position, other.position)

            # ✅ Weapon range (based on unit attack tables)
            if not self._in_weapon_range(active, other):
                continue

            # ✅ Determine mode
            mode = active.unit_type._resolve_attack_mode(distance)

            # ✅ Mortar min range (block short range)
            if mode == "INDIRECT_FIRE" and distance < 3:
                continue

            # ✅ LOS only for direct fire
            if mode == "DIRECT_FIRE":
                if not self._has_line_of_sight(active, other):
                    continue

            # ✅ Add action
            _trace(
                "ACTION_ADD",
                action="RangedDirectAttack",
                attacker=active.unit_id,
                target=other.unit_id,
                mode=mode,
            )

            actions.append(
                RangedDirectAttack(
                    active.unit_id,
                    other.unit_id,
                )
            )

        return actions

    # ==================================================
    # RANGE CHECK (BASED ON UNIT CARDS)
    # ==================================================
    def _in_weapon_range(self, attacker, target):

        distance = hex_distance(attacker.position, target.position)

        attack = attacker.unit_type._attack_raw

        for mode_data in attack.values():

            table = mode_data.get(target.unit_type.category.value)
            if not table:
                continue

            for key in table.keys():

                if "-" in key:
                    start, end = map(int, key.split("-"))
                    if start <= distance <= end:
                        return True
                else:
                    if int(key) == distance:
                        return True

        return False

    # ==================================================
    # LOS
    # ==================================================
    def _has_line_of_sight(self, attacker, target):
        return has_line_of_sight(attacker, target, self.gs.game_map)