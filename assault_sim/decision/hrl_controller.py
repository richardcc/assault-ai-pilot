from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.state_encoder import explainable_context

from assault_sim.strategy.formation_strategy import (
    FormationStrategy,
    FormationStrategyEngine,
)

import random


class HRLController:

    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 6,
        TacticalOption.FLANK: 5,
        TacticalOption.ATTACK: 10,
        TacticalOption.HOLD: 1,
        TacticalOption.RETREAT: 2,
    }

    def __init__(self, option_policy, option_executor, rl_side, event_bus=None):
        self.policy = option_policy
        self.executor = option_executor
        self.rl_side = rl_side
        self.event_bus = event_bus

        self.current_option = None
        self.current_attack_mode = None
        self.steps_remaining = -1

        self.formation_engine = FormationStrategyEngine()

    # -------------------------------------------------
    def choose_action(self, state, obs):

        active = state.active_unit

        if active is None or active.side != self.rl_side:
            return None

        # -------------------------------------------------
        # ✅ Detect close combat
        # -------------------------------------------------
        in_close_combat = False
        for u in state.units:
            if u.side != active.side and u.alive:
                dx = abs(active.position.q - u.position.q)
                dy = abs(active.position.r - u.position.r)
                if dx <= 1 and dy <= 1:
                    in_close_combat = True
                    break

        # -------------------------------------------------
        # ✅ ¿toca nueva decisión?
        # -------------------------------------------------
        is_new_selection = (
            self.current_option is None or self.steps_remaining <= 0
        )

        # -------------------------------------------------
        # ✅ mantener opción actual (sin overrides destructivos)
        # -------------------------------------------------
        if not is_new_selection:

            self.steps_remaining -= 1

            return self.executor.execute(
                state,
                self.current_option,
                self.current_attack_mode
            )

        # -------------------------------------------------
        # ✅ NUEVA DECISIÓN
        # -------------------------------------------------

        strategy = self.formation_engine.update(state, self.rl_side)

        # ✅ PPO decide base
        ppo_option, attack_mode = self.policy.choose_option(obs)

        # -------------------------------------------------
        # ✅ EXPLORACIÓN
        # -------------------------------------------------
        if random.random() < 0.1:
            ppo_option = random.choice(list(TacticalOption))

        # -------------------------------------------------
        # ✅ SOFT BIAS (NO overrides)
        # -------------------------------------------------

        # 🔥 combate cercano → favorecer ATTACK
        if in_close_combat and ppo_option != TacticalOption.ATTACK:
            if random.random() < 0.6:
                ppo_option = TacticalOption.ATTACK

        # 🔥 estrategia ATTACK → empujar (no forzar)
        if strategy == FormationStrategy.ATTACK:
            if ppo_option != TacticalOption.ATTACK:
                if random.random() < 0.6:
                    ppo_option = TacticalOption.ATTACK

        # 🔥 PUSH_VP → favorecer movimiento
        elif strategy == FormationStrategy.PUSH_VP:
            if ppo_option not in [TacticalOption.ADVANCE, TacticalOption.FLANK]:
                if random.random() < 0.7:
                    ppo_option = TacticalOption.ADVANCE

        # 🔥 HOLD_VP → evitar HOLD inútil
        elif strategy == FormationStrategy.HOLD_VP:
            if ppo_option == TacticalOption.HOLD:
                if random.random() < 0.9:
                    ppo_option = TacticalOption.ADVANCE

        # 🔥 CLEANUP → favorecer eliminar enemigos
        elif strategy == FormationStrategy.CLEANUP:
            if ppo_option != TacticalOption.ATTACK:
                if random.random() < 0.7:
                    ppo_option = TacticalOption.ATTACK

        # -------------------------------------------------
        # ✅ evitar acciones inútiles (SOFT)
        # -------------------------------------------------

        if ppo_option in [TacticalOption.HOLD, TacticalOption.RETREAT]:
            if random.random() < 0.6:
                ppo_option = TacticalOption.ADVANCE

        # -------------------------------------------------
        # ✅ evitar attack desde lejos (SOFT)
        # -------------------------------------------------
        if ppo_option == TacticalOption.ATTACK and not in_close_combat:

            close_enemy = False

            for u in state.units:
                if u.side != active.side and u.alive:
                    dx = abs(active.position.q - u.position.q)
                    dy = abs(active.position.r - u.position.r)

                    if dx <= 3 and dy <= 3:
                        close_enemy = True
                        break

            if not close_enemy:
                if random.random() < 0.5:
                    ppo_option = TacticalOption.ADVANCE

        # -------------------------------------------------
        # ✅ asignar decisión final
        # -------------------------------------------------
        self.current_option = ppo_option

        if self.current_option == TacticalOption.ATTACK:
            self.current_attack_mode = 0 if attack_mode is None else attack_mode
        else:
            self.current_attack_mode = None

        self.steps_remaining = self.OPTION_HORIZON[self.current_option]

        # -------------------------------------------------
        # ✅ LOGGING
        # -------------------------------------------------
        if self.event_bus:
            context = explainable_context(
                state,
                rl_side=self.rl_side,
                max_turns=getattr(state, "max_turns", None),
            )

            self.event_bus.emit({
                "type": "HRL_DECISION",
                "payload": {
                    "side": self.rl_side,
                    "option": self.current_option.name,
                    "attack_mode": (
                        "INDIRECT" if self.current_attack_mode == 1 else "DIRECT"
                        if self.current_attack_mode is not None else None
                    ),
                    "description": self.current_option.description(),
                    "category": self.current_option.category(),
                    "turn": state.turn,
                    "context": context,
                    "formation": strategy.name,
                    "policy_info": getattr(self.policy, "last_decision_info", {}),
                }
            })

        # -------------------------------------------------
        self.steps_remaining -= 1

        return self.executor.execute(
            state,
            self.current_option,
            self.current_attack_mode
        )