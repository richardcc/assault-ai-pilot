from enum import Enum
from typing import Optional
import random

from assault_model.map.hex_utils import hex_distance
from assault_model.map.hex_coord import HexCoord


class FormationStrategy(Enum):
    ATTACK = 0
    PUSH_VP = 1
    HOLD_VP = 2
    CLEANUP = 3


class FormationStrategyEngine:

    def __init__(self, horizon: int = 6):
        self.current_strategy: Optional[FormationStrategy] = None
        self.remaining_steps: int = 0
        self.horizon = horizon

    # -------------------------------------------------
    def update(self, state, rl_side):

        if self.current_strategy is None or self.remaining_steps <= 0:
            self.current_strategy = self._select_strategy(state, rl_side)
            self.remaining_steps = self.horizon

        self.remaining_steps -= 1
        return self.current_strategy

    # -------------------------------------------------
    def _select_strategy(self, state, rl_side):

        own_units = [
            u for u in state.units
            if u.side == rl_side and u.alive and u.position is not None
        ]

        enemy_units = [
            u for u in state.units
            if u.side != rl_side and u.alive and u.position is not None
        ]

        # -------------------------------------------------
        # ✅ fallback seguro
        # -------------------------------------------------
        if not own_units or not enemy_units:
            return FormationStrategy.PUSH_VP

        # -------------------------------------------------
        # ✅ DISTANCIA A ENEMIGOS
        # -------------------------------------------------
        def min_enemy_distance():
            best = 999
            for u in own_units:
                for e in enemy_units:
                    d = hex_distance(u.position, e.position)
                    if d < best:
                        best = d
            return best

        enemy_dist = min_enemy_distance()

        # -------------------------------------------------
        # ✅ CLEANUP (enemigos débiles)
        # -------------------------------------------------
        low_hp_enemies = [
            e for e in enemy_units
            if hasattr(e, "hp") and e.hp <= 1
        ]

        # -------------------------------------------------
        # ✅ VP DISTANCE
        # -------------------------------------------------
        vp_positions = []

        if hasattr(state, "vp_tracker") and state.vp_tracker:
            try:
                vp_positions = [
                    vp.hex_coords for vp in state.vp_tracker.conditions.points
                ]
            except Exception:
                vp_positions = []

        def distance_to_vp():
            if not vp_positions:
                return 999

            best = 999
            for u in own_units:
                for vp in vp_positions:
                    vp_pos = HexCoord(vp[0], vp[1])
                    d = hex_distance(u.position, vp_pos)
                    if d < best:
                        best = d
            return best

        vp_dist = distance_to_vp()

        # -------------------------------------------------
        # ✅ DECISIONES SUAVES (CLAVE)
        # -------------------------------------------------

        roll = random.random()

        # CLEANUP
        if len(low_hp_enemies) >= 2:
            return FormationStrategy.CLEANUP

        # 🔥 COMBATE CERCANO (NO FORZAR ATTACK)
        if enemy_dist <= 3:

            if roll < 0.4:
                return FormationStrategy.ATTACK
            elif roll < 0.7:
                return FormationStrategy.HOLD_VP
            else:
                return FormationStrategy.CLEANUP

        # 🔥 CERCA DE VP
        if vp_dist <= 2:

            if roll < 0.5:
                return FormationStrategy.HOLD_VP
            elif roll < 0.75:
                return FormationStrategy.ATTACK
            else:
                return FormationStrategy.PUSH_VP

        # 🔥 LEJOS → MÁS MEZCLA REAL
        if vp_dist > 2:

            if roll < 0.4:
                return FormationStrategy.PUSH_VP
            elif roll < 0.65:
                return FormationStrategy.HOLD_VP
            elif roll < 0.85:
                return FormationStrategy.ATTACK
            else:
                return FormationStrategy.CLEANUP

        # fallback real
        return FormationStrategy.HOLD_VP
