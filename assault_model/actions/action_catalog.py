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
    
    REVIEW:
    - This class is the single source of truth for the action space.
    - It enumerates legal actions but never applies or evaluates them.
    - It is intentionally ignorant of execution order, events, or combat resolution.
    """

    def __init__(self, game_state):
        # REVIEW: ActionCatalog holds a read-only reference to the current GameState
        self.gs = game_state

    def actions(self):
        # REVIEW: Actions are always generated relative to the CURRENT active unit
        active = self.gs.active_unit

        # REVIEW: Defensive fallback – if no active unit exists,
        # the game still exposes a valid action to avoid dead states
        if active is None:
            return [WaitAction(None)]

        actions = []
        q, r = active.position

        # ----------------------------------
        # CLOSE COMBAT (adjacent enemy)
        # ----------------------------------
        # REVIEW:
        # - Close combat is offered only when an enemy is adjacent.
        # - This checks legality only; outcome is resolved by the runtime.
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
        # REVIEW:
        # - Legal destination hexes are delegated to MovementRules.
        # - The catalog materializes each legal move as a concrete MoveAction.
        legal_moves = MovementRules.get_legal_moves(self.gs, active)
        for nq, nr in legal_moves:
            # REVIEW: Ignore no-op moves (stay-in-place)
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
        # REVIEW:
        # - WaitAction guarantees that the action space is never empty.
        # - Strategic meaning is interpreted entirely by higher layers.
        actions.append(WaitAction(active.unit_id))

        # REVIEW: Returned list is purely declarative; no side effects occur here
        return actions