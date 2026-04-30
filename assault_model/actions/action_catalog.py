from assault_model.actions.movement import MoveAction
from assault_model.actions.status import WaitAction
from assault_model.actions.assault import AssaultAction
from assault_model.rules.movement_rules import MovementRules
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import hex_distance


class ActionCatalog:
    """
    Canonical ActionCatalog of the MODEL.
    Returns CONCRETE actions understood by the runtime.
    """

    def __init__(self, game_state):
        self.gs = game_state

    def actions(self):
        active = self.gs.active_unit

        if active is None:
            return [WaitAction(None)]

        actions = []
        q, r = active.position

        # ----------------------------------
        # CLOSE COMBAT (adjacent enemy)
        # ----------------------------------
        for enemy in self.gs.units:
            if enemy.side == active.side:
                continue

            if hex_distance(active.position, enemy.position) == 1:
                actions.append(
                    AssaultAction(
                        unit_id=active.unit_id,
                        target_id=enemy.unit_id,
                    )
                )

        # ----------------------------------
        # MOVEMENT
        # ----------------------------------
        legal_moves = MovementRules.get_legal_moves(self.gs, active)
        for nq, nr in legal_moves:
            if (nq, nr) == (q, r):
                continue

            actions.append(
                MoveAction(
                    active.unit_id,
                    [HexCoord(nq, nr)],
                )
            )

        # ----------------------------------
        # WAIT
        # ----------------------------------
        actions.append(WaitAction(active.unit_id))

        return actions