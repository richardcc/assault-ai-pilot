from typing import Dict, List, Optional
import os

from assault_model.map.map import Map
from assault_model.map.hex_ownership import HexOwnership
from assault_model.map.hex_state import HexState
from assault_model.units.unit_instance import UnitInstance
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.core.vp_tracker import VictoryPointTracker
from assault_model.core.turn import TurnState, TurnPhase
from assault_model.core.activation import ActivationState

# --- COMBAT IMPORTS ---
from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.close_combat_context import CloseCombatContext
from assault_model.map.combat_geometry import determine_attack_sector

# --- REACTION IMPORT ---
from assault_model.combat.reaction_context import ReactionContext


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class GameState:
    """
    Canonical runtime game state.
    """

    def __init__(
        self,
        game_map: Map,
        units: List[UnitInstance],
        turn: int = 1,
        victory: Optional[VictoryConditions] = None,
    ) -> None:
        self.game_map = game_map
        self.units = units
        self.turn = turn

        # === TURN / ACTIVATION STATE ===
        self.turn_state = TurnState(turn_number=turn)
        self.activation_state = ActivationState(units)

        # === HEX STATE STORAGE ===
        self.hex_states: Dict[tuple[int, int], HexState] = {
            (h.q, h.r): HexState(h) for h in game_map.hexes
        }

        # === VICTORY CONDITIONS ===
        self.victory = victory
        self.vp_tracker = VictoryPointTracker(victory) if victory else None

        # === REACTION STATE ===
        # When not None, the game is paused waiting for a reaction decision
        self.reaction_context: Optional[ReactionContext] = None

    @classmethod
    def from_scenario(cls, scenario) -> "GameState":
        return cls(
            game_map=scenario.game_map,
            units=scenario.units,
            turn=1,
            victory=scenario.vp_conditions,
        )

    # ---------- ACTIVATION ----------
    @property
    def active_unit(self) -> Optional[UnitInstance]:
        return self.activation_state.active_unit

    def start_action_phase(self) -> None:
        self.turn_state.phase = TurnPhase.ACTION
        self.activation_state.reset(self.units)
        self.activation_state.next_unit()

    def end_active_unit(self) -> None:
        next_unit = self.activation_state.next_unit()
        if next_unit is None:
            self.end_turn()
            self.start_action_phase()

    # ---------- HEX CONTROL ----------
    def set_hex_owner(self, q: int, r: int, owner: HexOwnership) -> None:
        self.hex_states[(q, r)].ownership = owner
        self.hex_states[(q, r)].contested = False

    def set_hex_contested(self, q: int, r: int) -> None:
        self.hex_states[(q, r)].contested = True

    def get_hex_state(self, q: int, r: int) -> HexState:
        return self.hex_states[(q, r)]

    # ---------- TURN END ----------
    def end_turn(self) -> None:
        if self.vp_tracker:
            ownership_map = {
                coords: hs.ownership
                for coords, hs in self.hex_states.items()
            }
            self.vp_tracker.apply_turn(ownership_map)

        self.turn += 1
        self.turn_state.advance_turn()

    # =================================================
    # COMBAT CONTEXT CREATION
    # =================================================
    def create_combat_context(self, action):
        attacker = next(
            (u for u in self.units if u.unit_id == action.unit_id),
            None,
        )
        if attacker is None:
            raise ValueError(f"Attacker unit {action.unit_id} not found")

        defender = next(
            (u for u in self.units if u.unit_id == action.target_id),
            None,
        )
        if defender is None:
            raise ValueError(f"Defender unit {action.target_id} not found")

        if action.combat_mode != CombatMode.ASSAULT:
            raise NotImplementedError(
                f"Combat mode {action.combat_mode} not supported"
            )

        defender_facing = getattr(defender, "facing", "N")

        attack_sector = determine_attack_sector(
            attacker_pos=attacker.position,
            defender_pos=defender.position,
            defender_facing=defender_facing,
        )

        _trace(
            "ATTACK_SECTOR",
            attacker_pos=attacker.position,
            defender_pos=defender.position,
            defender_facing=defender_facing,
            sector=attack_sector,
        )

        _trace(
            "CC_CONTEXT_INIT",
            attacker_id=attacker.unit_id,
            attacker_code=attacker.unit_type.code,
            defender_id=defender.unit_id,
            defender_code=defender.unit_type.code,
            sector=attack_sector,
        )

        return CloseCombatContext(
            attacker=attacker,
            defender=defender,
            combat_mode=action.combat_mode,
            attack_sector=attack_sector,
        )

    # =================================================
    # REACTION STATE MANAGEMENT
    # =================================================
    def enter_reaction(self, context: ReactionContext) -> None:
        """
        Enter a reaction window.
        The game is paused until the reaction is resolved.
        """
        _trace(
            "REACTION_ENTER",
            trigger=context.trigger,
            reactor=context.reactor.unit_id,
            target=context.moving_unit.unit_id,
        )
        self.reaction_context = context

    def clear_reaction(self) -> None:
        """
        Exit the reaction window and resume normal play.
        """
        if self.reaction_context is not None:
            _trace("REACTION_CLEAR")
        self.reaction_context = None