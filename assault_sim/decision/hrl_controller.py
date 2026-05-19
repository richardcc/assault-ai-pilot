from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.state_encoder import explainable_context

from assault_sim.strategy.formation_strategy import (
    FormationStrategy,
    FormationStrategyEngine,
)

from assault_model.actions.status import WaitAction

import random


class HRLController:

    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 3,
        TacticalOption.FLANK: 2,
        TacticalOption.ATTACK: 4,   # 🔧 reducido (antes 10)
        TacticalOption.HOLD: 1,
        TacticalOption.RETREAT: 1,
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
        self.last_payload = None

    # -------------------------------------------------
    def choose_action(self, state, unit, obs):

        active = unit

        if active is None:
            return WaitAction("SYSTEM")

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
        # ✅ REUSE OPTION
        # -------------------------------------------------
        is_new_selection = (
            self.current_option is None or self.steps_remaining <= 0
        )

        if not is_new_selection:
            self.steps_remaining -= 1

            action = self.executor.execute(
                state,
                active,
                self.current_option,
                self.current_attack_mode
            )

            if action is None:
                action = WaitAction(active.unit_id)

            if self.last_payload:
                action.hrl_payload = self.last_payload

            return action

        # -------------------------------------------------
        # ✅ NEW DECISION
        # -------------------------------------------------
        strategy = self.formation_engine.update(state, self.rl_side)
        if strategy is None:
            strategy = FormationStrategy.ATTACK

        # ✅ decisión PPO REAL
        ppo_option, attack_mode = self.policy.choose_option(obs)

        # -------------------------------------------------
        # ✅ EXPLORATION (OK)
        # -------------------------------------------------
        if random.random() < 0.1:
            ppo_option = random.choice(list(TacticalOption))

        # -------------------------------------------------
        # ✅ SOFT BIAS (NO destructivo)
        # -------------------------------------------------

        # 🔧 mantener ATTACK si ya fue elegido
        if ppo_option != TacticalOption.ATTACK:

            if in_close_combat:
                if random.random() < 0.5:
                    ppo_option = TacticalOption.ATTACK

            if strategy == FormationStrategy.ATTACK:
                if random.random() < 0.4:
                    ppo_option = TacticalOption.ATTACK

            elif strategy == FormationStrategy.PUSH_VP:
                if random.random() < 0.4:
                    ppo_option = TacticalOption.ADVANCE

            elif strategy == FormationStrategy.CLEANUP:
                if random.random() < 0.5:
                    ppo_option = TacticalOption.ATTACK

        # -------------------------------------------------
        # ✅ IMPORTANTE: NO BLOQUEAR ATTACK
        # -------------------------------------------------
        # ❌ eliminado:
        # - bloqueo por distancia
        # - forzado a ADVANCE
        # - destrucción de decisiones PPO

        # -------------------------------------------------
        # ✅ ASSIGN FINAL DECISION
        # -------------------------------------------------
        self.current_option = ppo_option

        if self.current_option == TacticalOption.ATTACK:
            self.current_attack_mode = (
                0 if attack_mode is None else attack_mode
            )
        else:
            self.current_attack_mode = None

        self.steps_remaining = self.OPTION_HORIZON[self.current_option]

        # -------------------------------------------------
        # ✅ PAYLOAD
        # -------------------------------------------------
        payload = {
            "formation": strategy.name if strategy else None,
            "option": self.current_option.name,
            "attack_mode": (
                "INDIRECT" if self.current_attack_mode == 1 else
                "DIRECT" if self.current_attack_mode is not None else None
            ),
            "policy_info": getattr(self.policy, "last_decision_info", {})
        }

        self.last_payload = payload

        # -------------------------------------------------
        # ✅ EVENT BUS
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
                    "option": payload["option"],
                    "attack_mode": payload["attack_mode"],
                    "description": self.current_option.description(),
                    "category": self.current_option.category(),
                    "turn": state.turn,
                    "context": context,
                    "formation": payload["formation"],
                    "policy_info": payload["policy_info"],
                }
            })

        # -------------------------------------------------
        self.steps_remaining -= 1

        action = self.executor.execute(
            state,
            active,
            self.current_option,
            self.current_attack_mode
        )

        if action is None:
            action = WaitAction(active.unit_id)

        action.hrl_payload = payload

        return action