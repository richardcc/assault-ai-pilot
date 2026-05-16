from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.state_encoder import explainable_context

from assault_sim.strategy.formation_strategy import (
    FormationStrategy,
    FormationStrategyEngine,
)


class HRLController:

    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 6,
        TacticalOption.FLANK: 5,
        TacticalOption.ATTACK: 10,
        TacticalOption.HOLD: 1,
        TacticalOption.RETREAT: 2,
    }

    def __init__(self, option_policy, option_executor, rl_side, event_bus=None):
        # ✅ asegurarse de que es OptionPolicy
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

        # ✅ seguridad
        if active is None or active.side != self.rl_side:
            return None

        # -------------------------------------------------
        # Detect close combat
        # -------------------------------------------------
        in_close_combat = False
        for u in state.units:
            if u.side != active.side and u.alive:
                dx = abs(active.position.q - u.position.q)
                dy = abs(active.position.r - u.position.r)
                if dx <= 1 and dy <= 1:
                    in_close_combat = True
                    break

        is_new_selection = (
            self.current_option is None or self.steps_remaining <= 0
        )

        # -------------------------------------------------
        # MAINTAIN CURRENT OPTION
        # -------------------------------------------------
        if not is_new_selection:

            # ✅ mantener ATTACK coherente
            if self.current_option == TacticalOption.ATTACK:
                if in_close_combat:
                    self.steps_remaining = max(self.steps_remaining, 3)

            self.steps_remaining -= 1

            return self.executor.execute(
                state,
                self.current_option,
                self.current_attack_mode
            )

        # -------------------------------------------------
        # FORCE ATTACK EN COMBATE CERCANO
        # -------------------------------------------------
        if in_close_combat:
            self.current_option = TacticalOption.ATTACK
            self.current_attack_mode = 0  # direct
            self.steps_remaining = 5

        # -------------------------------------------------
        # NEW DECISION (RL + STRATEGY)
        # -------------------------------------------------
        else:

            strategy = self.formation_engine.update(state, self.rl_side)

            # ✅ CLAVE: esto requiere OptionPolicy
            ppo_option, attack_mode = self.policy.choose_option(obs)

            # -------------------------------------------------
            # Strategy fusion
            # -------------------------------------------------
            if strategy == FormationStrategy.ATTACK:
                if ppo_option in [TacticalOption.ATTACK, TacticalOption.ADVANCE]:
                    self.current_option = ppo_option
                else:
                    self.current_option = TacticalOption.ATTACK

            elif strategy == FormationStrategy.PUSH_VP:
                if ppo_option in [TacticalOption.ADVANCE, TacticalOption.FLANK]:
                    self.current_option = ppo_option
                else:
                    self.current_option = TacticalOption.ADVANCE

            elif strategy == FormationStrategy.HOLD_VP:
                if ppo_option in [TacticalOption.HOLD, TacticalOption.ATTACK]:
                    self.current_option = ppo_option
                else:
                    self.current_option = TacticalOption.HOLD

            elif strategy == FormationStrategy.CLEANUP:
                self.current_option = TacticalOption.ATTACK

            else:
                self.current_option = ppo_option

            # -------------------------------------------------
            # ✅ ATTACK MODE (robusto)
            # -------------------------------------------------
            if self.current_option == TacticalOption.ATTACK:
                self.current_attack_mode = 0 if attack_mode is None else attack_mode
            else:
                self.current_attack_mode = None

            self.steps_remaining = self.OPTION_HORIZON[self.current_option]

            # -------------------------------------------------
            # ✅ evitar flank en melee
            # -------------------------------------------------
            if in_close_combat and self.current_option == TacticalOption.FLANK:
                self.current_option = TacticalOption.ATTACK
                self.current_attack_mode = 0

            # -------------------------------------------------
            # LOGGING
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
