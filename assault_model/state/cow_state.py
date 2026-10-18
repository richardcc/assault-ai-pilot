"""
Transactional Copy-on-Write (CoW) and Delta State Layer for GameState (Roadmap 6.2).

Reduces MCTS node expansion memory footprint and cloning latency by:
1. Keeping static battlefield geometry (Map), unit templates (UnitType), and
   victory definitions (VictoryConditions) as immutable shared singletons.
2. Managing hex control states via a layered Copy-on-Write dictionary (CoWHexStateMap)
   that only allocates HexState instances for coordinates touched or mutated in a branch.
3. Tracking explicit transactional deltas (delta_positions, delta_health,
   delta_morale, delta_activations, delta_hex_ownership) for fast inspection
   and O(Delta) state checkpoint/rollback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterator, Optional, Tuple, TYPE_CHECKING

from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_ownership import HexOwnership
from assault_model.map.hex_state import HexState

if TYPE_CHECKING:
    from assault_model.state.game_state import GameState


def _clone_hex_state(src: HexState) -> HexState:
    """Fast shallow clone of a single HexState sharing the immutable Hex tile."""
    dst = object.__new__(HexState)
    dst.hex = src.hex
    dst.ownership = src.ownership
    dst.contested = src.contested
    return dst


class CoWHexStateMap(dict):
    """
    Copy-on-Write layered dictionary mapping (q, r) -> HexState.

    Inherits from `dict` for 100% compatibility with existing code expecting a dict,
    while lazily materializing `HexState` clones into `_deltas` only when a specific
    coordinate is fetched for potential mutation or written to.
    Read-only iterations (`items()`, `values()`, `get_readonly()`) read directly
    from the shared `_base` layer overlaid with `_deltas` without allocating objects.
    """

    __slots__ = ("_base", "_deltas")

    def __init__(
        self,
        initial: Optional[Dict[Tuple[int, int], HexState]] = None,
        *,
        _base: Optional[Dict[Tuple[int, int], HexState]] = None,
    ) -> None:
        super().__init__()
        if _base is not None:
            self._base: Dict[Tuple[int, int], HexState] = _base
            self._deltas: Dict[Tuple[int, int], HexState] = {}
        else:
            self._base = dict(initial) if initial else {}
            self._deltas = {}

    def branch(self) -> "CoWHexStateMap":
        """
        Create a O(1) Copy-on-Write child view.
        If the current map already has deltas, we merge the pointers into a flat
        read-only reference dictionary (copying only the pointer table, NOT the
        HexState objects) so lookup depth remains strictly O(1) across deep MCTS trees.
        """
        if not self._deltas:
            shared_base = self._base
        else:
            shared_base = {**self._base, **self._deltas}
        return CoWHexStateMap(_base=shared_base)

    @property
    def delta_count(self) -> int:
        """Number of coordinates materialized/mutated in this branch."""
        return len(self._deltas)

    @property
    def base_count(self) -> int:
        """Total number of coordinates in the shared base layer."""
        return len(self._base)

    def get_readonly(self, key: Tuple[int, int], default: Optional[HexState] = None) -> Optional[HexState]:
        """Zero-copy read access to a HexState without materializing a delta clone."""
        hs = self._deltas.get(key)
        if hs is not None:
            return hs
        return self._base.get(key, default)

    def __getitem__(self, key: Tuple[int, int]) -> HexState:
        hs = self._deltas.get(key)
        if hs is not None:
            return hs
        base_hs = self._base.get(key)
        if base_hs is None:
            raise KeyError(key)
        cloned = _clone_hex_state(base_hs)
        self._deltas[key] = cloned
        return cloned

    def get(self, key: Tuple[int, int], default: Optional[HexState] = None) -> Optional[HexState]:
        hs = self._deltas.get(key)
        if hs is not None:
            return hs
        base_hs = self._base.get(key)
        if base_hs is None:
            return default
        cloned = _clone_hex_state(base_hs)
        self._deltas[key] = cloned
        return cloned

    def __setitem__(self, key: Tuple[int, int], value: HexState) -> None:
        self._deltas[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._base or key in self._deltas

    def __len__(self) -> int:
        if not self._deltas:
            return len(self._base)
        return len(self._base.keys() | self._deltas.keys())

    def __iter__(self) -> Iterator[Tuple[int, int]]:
        if not self._deltas:
            return iter(self._base)
        return iter({**self._base, **self._deltas})

    def keys(self):
        if not self._deltas:
            return self._base.keys()
        return {**self._base, **self._deltas}.keys()

    def values(self):
        if not self._deltas:
            return self._base.values()
        return [self._deltas.get(k, v) for k, v in self._base.items()] + [
            v for k, v in self._deltas.items() if k not in self._base
        ]

    def items(self):
        if not self._deltas:
            return self._base.items()
        merged = {**self._base, **self._deltas}
        return merged.items()

    def copy(self) -> "CoWHexStateMap":
        return self.branch()

    def __deepcopy__(self, memo) -> "CoWHexStateMap":
        return self.branch()


@dataclass(slots=True)
class GameStateDelta:
    """
    Compact transactional delta representing all dynamic state changes:
    - delta_positions: unit_id -> (q, r) or None
    - delta_health: unit_id -> (strength, alive)
    - delta_morale: unit_id -> (suppressed, fallback)
    - delta_transport: unit_id -> (embarked, carrier_id, tuple(passengers))
    - delta_activations: (turn, frozenset(activated_units), active_side)
    - delta_hex_ownership: (q, r) -> (ownership, contested)
    - terminal: (done, winner, end_reason)
    """

    delta_positions: Dict[str, Optional[Tuple[int, int]]] = field(default_factory=dict)
    delta_health: Dict[str, Tuple[int, bool]] = field(default_factory=dict)
    delta_morale: Dict[str, Tuple[bool, bool]] = field(default_factory=dict)
    delta_transport: Dict[str, Tuple[bool, Optional[str], Tuple[str, ...]]] = field(default_factory=dict)
    delta_activations: Tuple[int, FrozenSet[str], Optional[str]] = (1, frozenset(), None)
    delta_hex_ownership: Dict[Tuple[int, int], Tuple[HexOwnership, bool]] = field(default_factory=dict)
    terminal: Tuple[bool, Optional[str], Optional[str]] = (False, None, None)

    @property
    def is_empty(self) -> bool:
        return (
            not self.delta_positions
            and not self.delta_health
            and not self.delta_morale
            and not self.delta_transport
            and not self.delta_hex_ownership
        )


def capture_full_checkpoint(state: "GameState", activated_units: Optional[set] = None, active_side: Optional[str] = None) -> GameStateDelta:
    """
    Capture a lightweight value-tuple checkpoint of all dynamic state in `state`
    for fast O(Delta) rollback in MCTS / lookahead search.
    """
    positions: Dict[str, Optional[Tuple[int, int]]] = {}
    health: Dict[str, Tuple[int, bool]] = {}
    morale: Dict[str, Tuple[bool, bool]] = {}
    transport: Dict[str, Tuple[bool, Optional[str], Tuple[str, ...]]] = {}

    for u in state.units:
        uid = u.unit_id
        positions[uid] = (u.position.q, u.position.r) if u.position is not None else None
        health[uid] = (int(u.strength), bool(u.alive))
        morale[uid] = (bool(u.suppressed), bool(u.fallback))
        passengers = tuple(getattr(u, "passengers", ()) or ())
        transport[uid] = (bool(u.embarked), u.carrier_id, passengers)

    hex_own: Dict[Tuple[int, int], Tuple[HexOwnership, bool]] = {}
    if isinstance(state.hex_states, CoWHexStateMap):
        for k, hs in state.hex_states.items():
            if hs.ownership != HexOwnership.NONE or hs.contested:
                hex_own[k] = (hs.ownership, hs.contested)
    else:
        for k, hs in state.hex_states.items():
            if hs.ownership != HexOwnership.NONE or hs.contested:
                hex_own[k] = (hs.ownership, hs.contested)

    act_frozen = frozenset(activated_units) if activated_units else frozenset()
    return GameStateDelta(
        delta_positions=positions,
        delta_health=health,
        delta_morale=morale,
        delta_transport=transport,
        delta_activations=(int(state.turn), act_frozen, active_side),
        delta_hex_ownership=hex_own,
        terminal=(bool(state.done), state.winner, state.end_reason),
    )


def compute_state_delta(base_state: "GameState", current_state: "GameState") -> GameStateDelta:
    """
    Compute the minimal transactional delta (Delta positions, Delta health,
    Delta morale, Delta activations, Delta hex control) from `base_state` to `current_state`.
    """
    base_units = {u.unit_id: u for u in base_state.units}
    d_pos: Dict[str, Optional[Tuple[int, int]]] = {}
    d_hp: Dict[str, Tuple[int, bool]] = {}
    d_mor: Dict[str, Tuple[bool, bool]] = {}
    d_trans: Dict[str, Tuple[bool, Optional[str], Tuple[str, ...]]] = {}

    for u in current_state.units:
        uid = u.unit_id
        bu = base_units.get(uid)
        cur_pos = (u.position.q, u.position.r) if u.position is not None else None
        base_pos = (bu.position.q, bu.position.r) if (bu and bu.position is not None) else None
        if bu is None or cur_pos != base_pos:
            d_pos[uid] = cur_pos

        cur_hp = (int(u.strength), bool(u.alive))
        base_hp = (int(bu.strength), bool(bu.alive)) if bu is not None else None
        if cur_hp != base_hp:
            d_hp[uid] = cur_hp

        cur_mor = (bool(u.suppressed), bool(u.fallback))
        base_mor = (bool(bu.suppressed), bool(bu.fallback)) if bu is not None else None
        if cur_mor != base_mor:
            d_mor[uid] = cur_mor

        cur_pass = tuple(getattr(u, "passengers", ()) or ())
        base_pass = tuple(getattr(bu, "passengers", ()) or ()) if bu is not None else ()
        cur_tr = (bool(u.embarked), u.carrier_id, cur_pass)
        base_tr = (bool(bu.embarked), bu.carrier_id, base_pass) if bu is not None else None
        if cur_tr != base_tr:
            d_trans[uid] = cur_tr

    d_hex: Dict[Tuple[int, int], Tuple[HexOwnership, bool]] = {}
    if isinstance(current_state.hex_states, CoWHexStateMap) and isinstance(base_state.hex_states, CoWHexStateMap):
        # Fast path: only inspect coordinates materialized in current_state._deltas
        for k, hs in current_state.hex_states._deltas.items():
            b_hs = base_state.hex_states.get_readonly(k)
            if b_hs is None or b_hs.ownership != hs.ownership or b_hs.contested != hs.contested:
                d_hex[k] = (hs.ownership, hs.contested)
    else:
        for k, hs in current_state.hex_states.items():
            b_hs = base_state.hex_states.get(k)
            if b_hs is None or b_hs.ownership != hs.ownership or b_hs.contested != hs.contested:
                d_hex[k] = (hs.ownership, hs.contested)

    return GameStateDelta(
        delta_positions=d_pos,
        delta_health=d_hp,
        delta_morale=d_mor,
        delta_transport=d_trans,
        delta_activations=(int(current_state.turn), frozenset(), None),
        delta_hex_ownership=d_hex,
        terminal=(bool(current_state.done), current_state.winner, current_state.end_reason),
    )


def apply_state_delta(state: "GameState", delta: GameStateDelta) -> None:
    """
    Apply a GameStateDelta in-place to `state`.
    """
    units_by_id = {u.unit_id: u for u in state.units}

    for uid, pos in delta.delta_positions.items():
        u = units_by_id.get(uid)
        if u is not None:
            u.position = HexCoord(pos[0], pos[1]) if pos is not None else None

    for uid, (strength, alive) in delta.delta_health.items():
        u = units_by_id.get(uid)
        if u is not None:
            u.strength = strength
            u.alive = alive

    for uid, (suppressed, fallback) in delta.delta_morale.items():
        u = units_by_id.get(uid)
        if u is not None:
            u.suppressed = suppressed
            u.fallback = fallback

    for uid, (embarked, carrier_id, passengers) in delta.delta_transport.items():
        u = units_by_id.get(uid)
        if u is not None:
            u.embarked = embarked
            u.carrier_id = carrier_id
            if hasattr(u, "passengers"):
                u.passengers = list(passengers)

    # Reset any currently non-empty hexes that were neutral in the checkpoint
    for coords, hs in list(state.hex_states.items()):
        target_own, target_cont = delta.delta_hex_ownership.get(coords, (HexOwnership.NONE, False))
        if hs.ownership != target_own or hs.contested != target_cont:
            mut_hs = state.hex_states.get(coords)
            if mut_hs is not None:
                mut_hs.ownership = target_own
                mut_hs.contested = target_cont

    turn_num, _, _ = delta.delta_activations
    state.turn = turn_num
    state.turn_state.turn_number = turn_num
    state.done, state.winner, state.end_reason = delta.terminal
    state._dirty_control_hexes.clear()
    state._rebuild_unit_spatial_index()
