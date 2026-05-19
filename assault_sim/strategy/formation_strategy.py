from enum import Enum
from typing import Optional
import random


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

        own_units = [u for u in state.units if u.side == rl_side and u.alive]
        enemy_units = [u for u in state.units if u.side != rl_side and u.alive]

        # -------------------------------------------------
        # ✅ fallback seguro
        # -------------------------------------------------
        if not own_units or not enemy_units:
            return FormationStrategy.PUSH_VP

        # -------------------------------------------------
        # DISTANCIA A ENEMIGOS
        # -------------------------------------------------
        def min_enemy_distance():
            best = 999
            for u in own_units:
                for e in enemy_units:
                    dx = abs(u.position.q - e.position.q)
                    dy = abs(u.position.r - e.position.r)
                    best = min(best, dx + dy)
            return best

        enemy_dist = min_enemy_distance()

        # -------------------------------------------------
        # CLEANUP (enemigos débiles)
        # -------------------------------------------------
        low_hp_enemies = [
            e for e in enemy_units
            if hasattr(e, "hp") and e.hp <= 1
        ]

        # -------------------------------------------------
        # VP
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
                    dx = abs(u.position.q - vp[0])
                    dy = abs(u.position.r - vp[1])
                    best = min(best, dx + dy)
            return best

        vp_dist = distance_to_vp()

        # -------------------------------------------------
        # ✅ DECISIONES
        # -------------------------------------------------

        # 🔥 1. CLEANUP agresivo si enemigos débiles
        if len(low_hp_enemies) >= 2:
            return FormationStrategy.CLEANUP

        # 🔥 2. COMBATE cercano → SIEMPRE atacar
        if enemy_dist <= 3:
            return FormationStrategy.ATTACK

        # 🔥 3. cerca de VP → mantener presión
        if vp_dist <= 2:
            return FormationStrategy.HOLD_VP

        # 🔥 4. lejos → push controlado PERO con tendencia a atacar
        if vp_dist > 2:

            roll = random.random()

            if roll < 0.4:
                return FormationStrategy.PUSH_VP
            elif roll < 0.7:
                return FormationStrategy.ATTACK   # 🔥 más agresivo
            else:
                return FormationStrategy.HOLD_VP

        # -------------------------------------------------
        # ✅ FALLBACK GLOBAL
        # -------------------------------------------------
        return FormationStrategy.ATTACK