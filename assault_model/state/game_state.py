"""
GameState represents the canonical, observable state of the game.
"""

from typing import Dict, List, Optional, Set, Tuple, Iterable, TYPE_CHECKING
import os

from assault_model.map.map import Map
from assault_model.map.hex_ownership import HexOwnership
from assault_model.map.hex_state import HexState
from assault_model.state.cow_state import (
    CoWHexStateMap,
    GameStateDelta,
    apply_state_delta,
    capture_full_checkpoint,
    compute_state_delta,
)
from assault_model.units.unit_instance import UnitInstance
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.core.vp_tracker import VictoryPointTracker
from assault_model.state.turn import TurnState
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import hex_range, safe_hex_distance, _as_qr, CoordLike

# --- COMBAT IMPORTS ---
from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.close_combat_context import CombatResolutionContext
from assault_model.map.combat_geometry import determine_attack_sector
from assault_model.map.hex_edge_feature import HexEdgeFeature

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
        # Turn order resolution
        # -----------------------------
        self.turn_order = self._build_turn_order(units)

        # -----------------------------
        # Side to ownership mapping
        # -----------------------------
        self.side_to_ownership = self._build_side_ownership()
        self.ownership_to_side = {own: side for side, own in self.side_to_ownership.items()}

        # -----------------------------
        # MAP STATE (Copy-on-Write layered dict, Roadmap 6.2)
        # -----------------------------
        self.hex_states: CoWHexStateMap = CoWHexStateMap({
            (h.q, h.r): HexState(h) for h in game_map.hexes
        })

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
        self.outcome: Optional["ScenarioOutcomeResult"] = None
        self._dirty_control_hexes: Set[Tuple[int, int]] = set()
        self._units_by_hex: Dict[Tuple[int, int], Set[str]] = {}
        self._unit_sides: Dict[str, str] = {}
        self._unit_last_known_state: Dict[str, Tuple[Optional[Tuple[int, int]], bool, bool]] = {}
        self._previously_occupied_hexes: Set[Tuple[int, int]] = set()

        # init
        self._apply_initial_vp_control_on_start()
        self.recalculate_hex_control(force_full=True)

    # =================================================
    # TURN ORDER
    # =================================================
    def _build_turn_order(self, units: List[UnitInstance]) -> List[str]:
        return sorted({u.side for u in units if u.alive})

    # =================================================
    # SIDE → OWNERSHIP
    # =================================================
    def _build_side_ownership(self) -> Dict[str, HexOwnership]:
        # IMPORTANT: NONE is a neutral/uncontrolled sentinel and must never be
        # assigned to a real side. Only controlled ownership values are valid.
        ownership_values = [o for o in HexOwnership if o.is_controlled()]

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
    # HEX CONTROL (Incremental O(k * R^2) update)
    # =================================================
    def record_dirty_control_hex(self, coords: CoordLike) -> None:
        """
        Record a single hex coordinate that suffered tactical changes
        (movement, casualties, suppression, morale retreat).
        """
        try:
            q, r = _as_qr(coords)
            if not hasattr(self, "_dirty_control_hexes"):
                self._dirty_control_hexes = set()
            self._dirty_control_hexes.add((q, r))
        except Exception:
            pass

    def record_unit_event(
        self,
        unit: UnitInstance,
        prev_coords: Optional[CoordLike] = None,
    ) -> None:
        """
        Record affected origin coordinates for a unit action/event.
        """
        if prev_coords is not None:
            self.record_dirty_control_hex(prev_coords)
        if unit is not None and getattr(unit, "position", None) is not None:
            self.record_dirty_control_hex(unit.position)

    def _rebuild_unit_spatial_index(self) -> None:
        """Full rebuild of unit spatial index and state snapshot."""
        self._units_by_hex = {}
        self._unit_sides = {}
        self._unit_last_known_state = {}

        for unit in self.units:
            self._unit_sides[unit.unit_id] = unit.side
            pos = (unit.position.q, unit.position.r) if (unit.alive and unit.position) else None
            self._unit_last_known_state[unit.unit_id] = (pos, unit.alive, unit.suppressed)
            if pos is not None:
                self._units_by_hex.setdefault(pos, set()).add(unit.unit_id)

    def add_unit(self, unit: UnitInstance) -> None:
        """
        Dynamically register a reinforcement unit into the game state.
        Maintains side mappings, spatial unit lookups, turn orders and territorial control.
        """
        self.units.append(unit)
        self._unit_sides[unit.unit_id] = unit.side
        pos = (unit.position.q, unit.position.r) if (unit.alive and unit.position) else None
        self._unit_last_known_state[unit.unit_id] = (pos, unit.alive, unit.suppressed)
        if pos is not None:
            self._units_by_hex.setdefault(pos, set()).add(unit.unit_id)
            self._dirty_control_hexes.add(pos)
        if unit.side not in self.turn_order:
            self.turn_order.append(unit.side)
        self._cache_version = int(getattr(self, "_cache_version", 0)) + 1
        self.recalculate_hex_control(affected_positions=[pos] if pos is not None else None)

    def recalculate_hex_control(
        self,
        affected_positions: Optional[Iterable[CoordLike]] = None,
        influence_radius: int = 3,
        force_full: bool = False,
    ) -> Set[Tuple[int, int]]:
        """
        Incremental territorial control recalculation in O(k * R^2) amortized.

        Brecha Resuelta (Roadmap 6.3):
        En lugar de iterar sobre toda la cuadrícula (W * H * N), solo se recalculan
        los hexágonos dentro del radio de influencia táctica (R <= 3) alrededor de
        las unidades que ejecutaron movimientos, sufrieron bajas o quedaron suprimidas.
        """
        vp_hexes = set()
        if self.victory:
            vp_hexes = {vp.hex_coords for vp in self.victory.points}

        if (
            force_full
            or not hasattr(self, "_units_by_hex")
            or not hasattr(self, "_unit_last_known_state")
            or not hasattr(self, "_dirty_control_hexes")
        ):
            self._rebuild_unit_spatial_index()
            self._dirty_control_hexes = set()
            active_coords = set(self.hex_states.keys())
        else:
            dirty_origins: Set[Tuple[int, int]] = set(self._dirty_control_hexes)
            if affected_positions:
                for p in affected_positions:
                    try:
                        dirty_origins.add(_as_qr(p))
                    except Exception:
                        pass

            # Detect automatic delta in unit positions, casualties, suppression, or desynced hex ownership
            for unit in self.units:
                self._unit_sides[unit.unit_id] = unit.side
                pos = (unit.position.q, unit.position.r) if (unit.alive and unit.position) else None
                last_pos, last_alive, last_suppressed = self._unit_last_known_state.get(
                    unit.unit_id, (None, False, False)
                )

                expected_owner = self.side_to_ownership.get(unit.side, HexOwnership.NONE) if unit.alive else None
                ro_hs = (
                    self.hex_states.get_readonly(pos)
                    if isinstance(self.hex_states, CoWHexStateMap) and pos is not None
                    else (self.hex_states.get(pos) if pos is not None else None)
                )
                ownership_desynced = (
                    ro_hs is not None
                    and ro_hs.ownership != expected_owner
                )

                if pos != last_pos or unit.alive != last_alive or unit.suppressed != last_suppressed or ownership_desynced:
                    if last_pos is not None:
                        dirty_origins.add(last_pos)
                        if last_pos in self._units_by_hex:
                            self._units_by_hex[last_pos].discard(unit.unit_id)
                            if not self._units_by_hex[last_pos]:
                                del self._units_by_hex[last_pos]
                    if pos is not None:
                        dirty_origins.add(pos)
                        self._units_by_hex.setdefault(pos, set()).add(unit.unit_id)

                    self._unit_last_known_state[unit.unit_id] = (pos, unit.alive, unit.suppressed)

            self._dirty_control_hexes.clear()

            if not dirty_origins:
                return set()

            # Expand dirty centers by tactical influence radius R <= 3 (O(k * R^2))
            active_coords = set()
            for origin in dirty_origins:
                for h in hex_range(origin, radius=influence_radius):
                    if h in self.hex_states:
                        active_coords.add(h)

        is_cow = isinstance(self.hex_states, CoWHexStateMap)
        # Update active hexes in O(k * R^2), mutating CoW deltas only when ownership/contested changes
        for coords in active_coords:
            ro_state = self.hex_states.get_readonly(coords) if is_cow else self.hex_states.get(coords)
            if ro_state is None:
                continue

            unit_ids = self._units_by_hex.get(coords, set())
            present_sides = {self._unit_sides[uid] for uid in unit_ids if uid in self._unit_sides}

            if len(present_sides) == 1:
                side = next(iter(present_sides))
                new_ownership = self.side_to_ownership.get(
                    side,
                    HexOwnership.NONE,
                )
                new_contested = False

            elif len(present_sides) > 1:
                new_ownership = HexOwnership.NONE
                new_contested = True

            else:
                # VP control persists until another side occupies the hex.
                if coords not in vp_hexes:
                    new_ownership = HexOwnership.NONE
                else:
                    new_ownership = ro_state.ownership
                new_contested = False

            if ro_state.ownership != new_ownership or ro_state.contested != new_contested:
                hex_state = self.hex_states.get(coords)
                if hex_state is not None:
                    hex_state.ownership = new_ownership
                    hex_state.contested = new_contested

        self._previously_occupied_hexes = set(self._units_by_hex.keys())
        return active_coords

    def _apply_initial_vp_control_on_start(self) -> None:
        """
        VP hexes start neutral by default, unless the scenario
        explicitly sets an initial owner for a given VP.
        """
        if self.turn != 1 or not self.victory:
            return

        for vp in self.victory.points:
            hex_state = self.hex_states.get(vp.hex_coords)
            if hex_state is None:
                continue
            if vp.initial_owner:
                hex_state.ownership = self.side_to_ownership.get(
                    vp.initial_owner,
                    HexOwnership.NONE,
                )
            else:
                hex_state.ownership = HexOwnership.NONE
            hex_state.contested = False

    # =================================================
    # TURN END
    # =================================================
    def end_turn(self) -> None:

        self.recalculate_hex_control()

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

        ctx = CombatResolutionContext(
            attacker=attacker,
            defender=defender,
            combat_mode=getattr(action, "combat_mode", CombatMode.ASSAULT),
            attack_sector=attack_sector,
        )
        # CC-001 obstacle crossing hook:
        # if attacker->defender edge has an obstacle feature, mark context.
        if attacker.position is not None and defender.position is not None:
            edge_feature = self.game_map.get_hex_edge_feature(
                (attacker.position.q, attacker.position.r),
                (defender.position.q, defender.position.r),
            )
            ctx.crossed_obstacle = edge_feature in {HexEdgeFeature.WALL}

            # Palma et al. 2025 / Task 2.4: Multi-unit combined assault support detection
            supporting_attackers = []
            for u in self.units:
                if (
                    u.unit_id != attacker.unit_id
                    and u.side == attacker.side
                    and bool(getattr(u, "alive", True))
                    and not bool(getattr(u, "suppressed", False))
                ):
                    if u.position is not None and safe_hex_distance(u.position, defender.position) == 1:
                        supporting_attackers.append(u)
            ctx.supporting_attackers = supporting_attackers
            ctx.unsuppressed_solo_frontal_penalty_enabled = True
        return ctx

    # =================================================
    # REACTION STATE
    # =================================================
    def enter_reaction(self, context: "ReactionContext") -> None:
        self.reaction_context = context

    def clear_reaction(self) -> None:
        self.reaction_context = None

    # =================================================
    # COPY-ON-WRITE (CoW) & TRANSACTIONAL DELTAS (Roadmap 6.2)
    # =================================================
    def clone_cow(self) -> "GameState":
        """
        Create an isolated Copy-on-Write (CoW) transactional clone of GameState.

        - Shares immutable singletons: `game_map`, `victory`, `turn_order`,
          `side_to_ownership`, and unit static `UnitType` templates.
        - Branches `hex_states` via `CoWHexStateMap.branch()` in O(1) without
          duplicating untouched `HexState` objects.
        - Clones dynamic unit deltas via `UnitInstance.clone_cow()`.
        """
        cloned = object.__new__(GameState)
        cloned.game_map = self.game_map
        cloned.units = [u.clone_cow() for u in self.units]
        cloned.turn = self.turn
        cloned.turn_state = TurnState(turn_number=self.turn)
        cloned.turn_order = self.turn_order
        cloned.side_to_ownership = self.side_to_ownership
        cloned.ownership_to_side = getattr(self, "ownership_to_side", None)

        if isinstance(self.hex_states, CoWHexStateMap):
            cloned.hex_states = self.hex_states.branch()
        else:
            cloned.hex_states = CoWHexStateMap(self.hex_states).branch()

        cloned.victory = self.victory
        cloned.vp_tracker = self.vp_tracker.clone_cow() if self.vp_tracker is not None else None
        cloned.reaction_context = self.reaction_context
        cloned.done = self.done
        cloned.winner = self.winner
        cloned.end_reason = self.end_reason
        cloned.outcome = self.outcome
        cloned._cache_version = int(getattr(self, "_cache_version", 0))

        cloned._dirty_control_hexes = set(getattr(self, "_dirty_control_hexes", ()))
        cloned._units_by_hex = {
            k: set(v) for k, v in getattr(self, "_units_by_hex", {}).items()
        }
        cloned._unit_sides = dict(getattr(self, "_unit_sides", {}))
        cloned._unit_last_known_state = dict(getattr(self, "_unit_last_known_state", {}))
        cloned._previously_occupied_hexes = set(getattr(self, "_previously_occupied_hexes", ()))
        return cloned

    def __deepcopy__(self, memo) -> "GameState":
        return self.clone_cow()

    def compute_delta(self, other: "GameState") -> GameStateDelta:
        """Compute minimal transactional delta from `self` to `other`."""
        return compute_state_delta(self, other)

    def create_checkpoint(
        self,
        activated_units: Optional[set] = None,
        active_side: Optional[str] = None,
    ) -> GameStateDelta:
        """Capture a lightweight transactional checkpoint for O(Delta) rollback."""
        return capture_full_checkpoint(self, activated_units=activated_units, active_side=active_side)

    def restore_checkpoint(self, delta: GameStateDelta) -> None:
        """Restore `self` in-place from a previously captured GameStateDelta."""
        apply_state_delta(self, delta)