from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from voec_sim.core.simulator import VOECSimulator


@dataclass
class MuZeroObservation:
    turn: int
    to_play: str | None
    done: bool
    units: List[Dict]
    playable_hexes: List[Dict]
    vp_hexes: List[Dict]
    vp_owner_by_hex: Dict[str, str]
    terrain_move_cost_by_hex: Dict[str, float]
    terrain_cover_by_hex: Dict[str, float]
    terrain_los_block_by_hex: Dict[str, int]


class MuZeroVOECAdapter:
    """
    Thin adapter exposing MuZero-friendly API on top of VOEC.
    """

    def __init__(self, simulator: VOECSimulator):
        self.sim = simulator

    def initial_state(self, scenario_id: str, seed: int = 0) -> MuZeroObservation:
        self.sim.new_episode(scenario_id=scenario_id, seed=seed)
        return self.observation()

    def legal_actions(self) -> List[str]:
        return self.sim.legal_actions()

    def apply(self, action_id: str):
        return self.sim.step(action_id)

    def terminal(self) -> bool:
        return self.sim.is_terminal()

    def observation(self) -> MuZeroObservation:
        snapshot = self.sim.snapshot()
        spatial = self.sim.spatial_features()
        return MuZeroObservation(
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
                }
                for u in snapshot.units
            ],
            playable_hexes=list(spatial.get("playable_hexes", [])),
            vp_hexes=list(spatial.get("vp_hexes", [])),
            vp_owner_by_hex=dict(spatial.get("vp_owner_by_hex", {})),
            terrain_move_cost_by_hex=dict(spatial.get("terrain_move_cost_by_hex", {})),
            terrain_cover_by_hex=dict(spatial.get("terrain_cover_by_hex", {})),
            terrain_los_block_by_hex=dict(spatial.get("terrain_los_block_by_hex", {})),
        )
