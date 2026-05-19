"""
GameState represents the canonical, observable state of the game.
"""

from typing import Dict, List, Optional, TYPE_CHECKING
import os

from assault_model.map.map import Map
from assault_model.map.hex_ownership import HexOwnership
from assault_model.map.hex_state import HexState
from assault_model.units.unit_instance import UnitInstance
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.core.vp_tracker import VictoryPointTracker
from assault_model.state.turn import TurnState
from assault_model.map.hex_coord import HexCoord

# --- COMBAT IMPORTS ---
from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.close_combat_context import CombatResolutionContext
from assault_model.map.combat_geometry import determine_attack_sector

# --- TYPING-ONLY ---
if TYPE_CHECKING:
    from assault_model.combat.reaction_context import ReactionContext


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class GameState:
    """
    ✅ Pure state container
    ✅ No activation logic
    ✅ Deterministic and RL-safe
    """

    def __init__(
        self,
        game_map: Map,
        units: List[UnitInstance],
        turn: int = 1,
        victory: Optional[VictoryConditions] = None,
    ) -> None:

        # -----------------------------
        # CORE STATE
        # -----------------------------
        self.game_map = game_map
        self.units = units
        self.turn = turn

        self.turn_state = TurnState(turn_number=turn)

        # -----------------------------
        # ✅ TURN ORDER (CRÍTICO)
        # -----------------------------
        self.turn_order = self._build_turn_order(units)

        # -----------------------------
        # ✅ SIDE → OWNERSHIP
        # -----------------------------
        self.side_to_ownership = self._build_side_ownership()

        # -----------------------------
        # MAP STATE
        # -----------------------------
        self.hex_states: Dict[tuple[int, int], HexState] = {
            (h.q, h.r): HexState(h) for h in game_map.hexes
        }

        # -----------------------------
        # VICTORY SYSTEM
        # -----------------------------
        self.victory = victory
        self.vp_tracker = VictoryPointTracker(victory) if victory else None

        # -----------------------------
        # REACTION
        # -----------------------------
        self.reaction_context: Optional["ReactionContext"] = None

        # -----------------------------
        # TERMINAL STATE
        # -----------------------------
        self.done: bool = False
        self.winner: Optional[str] = None
        self.end_reason: Optional[str] = None

        # init
        self.recalculate_hex_control()

    # =================================================
    # TURN ORDER
    # =================================================
    def _build_turn_order(self, units: List[UnitInstance]) -> List[str]:
        return sorted({u.side for u in units if u.alive})

    # =================================================
    # SIDE → OWNERSHIP
    # =================================================
    def _build_side_ownership(self) -> Dict[str, HexOwnership]:
        ownership_values = list(HexOwnership)

        if len(self.turn_order) > len(ownership_values):
            raise ValueError("More sides than HexOwnership values")

        return {
            side: ownership_values[i]
            for i, side in enumerate(self.turn_order)
        }

    # =================================================
    # FACTORY
    # =================================================
    @classmethod
    def from_scenario(cls, scenario) -> "GameState":
        return cls(
            game_map=scenario.game_map,
            units=scenario.units,
            turn=1,
            victory=scenario.vp_conditions,
        )

    # =================================================
    # HEX CONTROL
    # =================================================
    def recalculate_hex_control(self) -> None:

        units_by_hex: Dict[tuple[int, int], set[str]] = {}

        for unit in self.units:
            if not unit.alive or not unit.position:
                continue

            coords = (unit.position.q, unit.position.r)
            units_by_hex.setdefault(coords, set()).add(unit.side)

        for coords, hex_state in self.hex_states.items():
            present_sides = units_by_hex.get(coords, set())

            if len(present_sides) == 1:
                side = next(iter(present_sides))
                hex_state.ownership = self.side_to_ownership.get(
                    side,
                    HexOwnership.NONE,
                )
                hex_state.contested = False

            elif len(present_sides) > 1:
                hex_state.ownership = HexOwnership.NONE
                hex_state.contested = True

            else:
                hex_state.ownership = HexOwnership.NONE
                hex_state.contested = False

    # =================================================
    # TURN END
    # =================================================
    def end_turn(self) -> None:

        self.recalculate_hex_control()

        if self.vp_tracker:
            ownership_map = {
                coords: hs.ownership
                for coords, hs in self.hex_states.items()
            }
            self.vp_tracker.apply_turn(ownership_map)

        self.turn += 1
        self.turn_state.advance_turn()

    # =================================================
    # COMBAT CONTEXT
    # =================================================
    def create_combat_context(self, action):

        attacker = next(
            (u for u in self.units if u.unit_id == action.unit_id),
            None,
        )
        defender = next(
            (u for u in self.units if u.unit_id == action.target_id),
            None,
        )

        if attacker is None or defender is None:
            raise ValueError("Combat units not found")

        attack_sector = determine_attack_sector(
            attacker_pos=attacker.position,
            defender_pos=defender.position,
            defender_facing=getattr(defender, "facing", "N"),
        )

        return CombatResolutionContext(
            attacker=attacker,
            defender=defender,
            combat_mode=action.combat_mode,
            attack_sector=attack_sector,
        )

    # =================================================
    # REACTION STATE
    # =================================================
    def enter_reaction(self, context: "ReactionContext") -> None:
        self.reaction_context = context

    def clear_reaction(self) -> None:
        self.reaction_context = None