from enum import Enum
from typing import Optional
import random

from assault_model.map.hex_utils import safe_hex_distance
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

        if not own_units or not enemy_units:
            return FormationStrategy.PUSH_VP

        # -------------------------------------------------
        # ✅ DISTANCIA ENEMIGO (mínima)
        # -------------------------------------------------
        enemy_dist = min(
            safe_hex_distance(u.position, e.position)
            for u in own_units
            for e in enemy_units
        )

        # -------------------------------------------------
        # ✅ VENTAJA LOCAL (🔥 CLAVE NUEVO)
        # -------------------------------------------------
        friendly_hp = sum(getattr(u, "hp", 0) for u in own_units)
        enemy_hp = sum(getattr(e, "hp", 0) for e in enemy_units)

        hp_advantage = friendly_hp - enemy_hp
        unit_advantage = len(own_units) - len(enemy_units)

        # -------------------------------------------------
        # ✅ ENEMIGOS DÉBILES
        # -------------------------------------------------
        low_hp_enemies = [
            e for e in enemy_units
            if getattr(e, "hp", 0) <= 1
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

            return min(
                safe_hex_distance(u.position, HexCoord(vp[0], vp[1]))
                for u in own_units
                for vp in vp_positions
            )

        vp_dist = distance_to_vp()

        roll = random.random()

        # -------------------------------------------------
        # ✅ CLEANUP (solo si conviene)
        # -------------------------------------------------
        if len(low_hp_enemies) >= 2:
            if hp_advantage >= 0 or roll < 0.6:
                return FormationStrategy.CLEANUP

        # -------------------------------------------------
        # ✅ COMBATE CERCANO (🔥 MÁS INTELIGENTE)
        # -------------------------------------------------
        if enemy_dist <= 3:

            # ✅ si vamos ganando → agresivo
            if hp_advantage > 0 or unit_advantage > 0:
                if roll < 0.6:
                    return FormationStrategy.ATTACK
                elif roll < 0.85:
                    return FormationStrategy.CLEANUP
                else:
                    return FormationStrategy.HOLD_VP

            # ❌ si vamos perdiendo → defensivo
            else:
                if roll < 0.5:
                    return FormationStrategy.HOLD_VP
                elif roll < 0.8:
                    return FormationStrategy.PUSH_VP
                else:
                    return FormationStrategy.ATTACK  # gamble controlado

        # -------------------------------------------------
        # ✅ CERCA DEL VP
        # -------------------------------------------------
        if vp_dist <= 2:

            if hp_advantage >= 0:
                if roll < 0.6:
                    return FormationStrategy.HOLD_VP
                elif roll < 0.85:
                    return FormationStrategy.ATTACK
                else:
                    return FormationStrategy.CLEANUP
            else:
                return FormationStrategy.HOLD_VP

        # -------------------------------------------------
        # ✅ LEJOS DEL VP
        # -------------------------------------------------
        if vp_dist > 2:

            if hp_advantage > 2:
                if roll < 0.5:
                    return FormationStrategy.ATTACK
                else:
                    return FormationStrategy.PUSH_VP

            elif hp_advantage < -2:
                if roll < 0.6:
                    return FormationStrategy.HOLD_VP
                else:
                    return FormationStrategy.PUSH_VP

            else:
                if roll < 0.4:
                    return FormationStrategy.PUSH_VP
                elif roll < 0.7:
                    return FormationStrategy.ATTACK
                else:
                    return FormationStrategy.HOLD_VP

        return FormationStrategy.HOLD_VP