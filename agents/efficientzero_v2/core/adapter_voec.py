from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from voec_sim.core.simulator import VOECSimulator


@dataclass
class EZV2Observation:
    turn: int = 1
    to_play: str | None = None
    done: bool = False
    units: List[Dict] = field(default_factory=list)
    playable_hexes: List[Dict] = field(default_factory=list)
    vp_hexes: List[Dict] = field(default_factory=list)
    vp_owner_by_hex: Dict[str, str] = field(default_factory=dict)
    terrain_move_cost_by_hex: Dict[str, float] = field(default_factory=dict)
    terrain_cover_by_hex: Dict[str, float] = field(default_factory=dict)
    terrain_los_block_by_hex: Dict[str, int] = field(default_factory=dict)
    terrain_type_by_hex: Dict[str, str] = field(default_factory=dict)
    fortification_type_by_hex: Dict[str, str] = field(default_factory=dict)
    fortification_edge_by_hex: Dict[str, Dict[str, int]] = field(default_factory=dict)
    max_turns: int = 8
    _coord_bounds: tuple[int, int, int, int] | None = None


class EZV2VOECAdapter:
    """Thin EZv2 adapter exposing a stable selfplay surface."""

    def __init__(self, simulator: VOECSimulator):
        self.sim = simulator
        self._cached_bounds: Optional[tuple[int, int, int, int]] = None

    def initial_state(
        self,
        scenario_id: str,
        seed: int = 0,
        terrain_mutation_prob: float = 0.0,
        unit_jitter_prob: float = 0.0,
        asymmetric_strength_jitter: float = 0.0,
    ) -> EZV2Observation:
        self._cached_bounds = None
        self.sim.new_episode(
            scenario_id=scenario_id,
            seed=seed,
            terrain_mutation_prob=terrain_mutation_prob,
            unit_jitter_prob=unit_jitter_prob,
            asymmetric_strength_jitter=asymmetric_strength_jitter,
        )
        return self.observation()

    def legal_actions(self) -> List[str]:
        return self.sim.legal_actions()

    def apply(self, action_id: str):
        return self.sim.step(action_id)

    def terminal(self) -> bool:
        return self.sim.is_terminal()

    def scenario_max_turns(self) -> int:
        return int(self.sim.scenario_max_turns() or 8)

    def scenario_total_units(self) -> int:
        if hasattr(self.sim, "scenario_total_units"):
            return int(self.sim.scenario_total_units() or 0)
        return len(getattr(getattr(self.sim, "_state", None), "units", []) or [])

    def observation(self) -> EZV2Observation:
        snapshot = self.sim.snapshot()
        spatial = self.sim.spatial_features()
        playable = list(spatial.get("playable_hexes", []))
        if self._cached_bounds is None and playable:
            qs = [int(h["q"]) for h in playable if "q" in h]
            rs = [int(h["r"]) for h in playable if "r" in h]
            if qs and rs:
                self._cached_bounds = (min(qs), max(qs), min(rs), max(rs))
        return EZV2Observation(
            turn=snapshot.turn,
            to_play=snapshot.to_play,
            done=snapshot.done,
            units=[
                {
                    "unit_id": u.unit_id,
                    "unit_key": u.unit_key,
                    "unit_label": u.unit_label,
                    "art_ref": u.art_ref,
                    "side": u.side,
                    "q": u.q,
                    "r": u.r,
                    "hp": u.hp,
                    "alive": u.alive,
                    "doctrine_role": getattr(u, "doctrine_role", None),
                    "doctrine_profile": getattr(u, "doctrine_profile", None),
                }
                for u in snapshot.units
            ],
            playable_hexes=playable,
            vp_hexes=list(spatial.get("vp_hexes", [])),
            vp_owner_by_hex=dict(spatial.get("vp_owner_by_hex", {})),
            terrain_move_cost_by_hex=dict(spatial.get("terrain_move_cost_by_hex", {})),
            terrain_cover_by_hex=dict(spatial.get("terrain_cover_by_hex", {})),
            terrain_los_block_by_hex=dict(spatial.get("terrain_los_block_by_hex", {})),
            terrain_type_by_hex=dict(spatial.get("terrain_type_by_hex", {})),
            fortification_type_by_hex=dict(spatial.get("fortification_type_by_hex", {})),
            fortification_edge_by_hex=dict(spatial.get("fortification_edge_by_hex", {})),
            max_turns=int(self.sim.scenario_max_turns() or 8),
            _coord_bounds=self._cached_bounds,
        )

