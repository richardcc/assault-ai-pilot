from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.state_encoder import explainable_context


class HRLController:

    # -------------------------------------------------
    # ✅ HORIZON AJUSTADO
    # -------------------------------------------------
    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 6,
        TacticalOption.FLANK: 5,    # 🔥 antes 8 → reduce drift
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
        self.steps_remaining = -1

    # -------------------------------------------------
    # MAIN
    # -------------------------------------------------
    def choose_action(self, state, obs):

        active = state.active_unit

        # -------------------------------------------------
        # No control
        # -------------------------------------------------
        if active is None or active.side != self.rl_side:
            return None

        # -------------------------------------------------
        # 🔥 detectar combate cercano
        # -------------------------------------------------
        in_close_combat = False
        for u in state.units:
            if u.side != active.side and u.alive:
                if hasattr(active, "position") and hasattr(u, "position"):
                    dx = abs(active.position.q - u.position.q)
                    dy = abs(active.position.r - u.position.r)
                    if dx <= 1 and dy <= 1:
                        in_close_combat = True
                        break

        # -------------------------------------------------
        # ¿nueva opción?
        # -------------------------------------------------
        is_new_selection = (
            self.current_option is None or self.steps_remaining <= 0
        )

        # -------------------------------------------------
        # ✅ mantener ATTACK con continuidad
        # -------------------------------------------------
        if not is_new_selection:
            if self.current_option == TacticalOption.ATTACK:

                # 🔥 extender si sigue en combate
                if in_close_combat:
                    self.steps_remaining = max(self.steps_remaining, 3)

                self.steps_remaining -= 1
                return self.executor.execute(state, self.current_option)

        # -------------------------------------------------
        # ✅ forzar ATTACK si hay combate cercano
        # -------------------------------------------------
        if in_close_combat:
            self.current_option = TacticalOption.ATTACK
            self.steps_remaining = 5   # 🔥 antes 2

        # -------------------------------------------------
        # selección nueva
        # -------------------------------------------------
        elif is_new_selection:

            self.current_option = self.policy.choose_option(obs)
            self.steps_remaining = self.OPTION_HORIZON[self.current_option]

            # 🔥 bloquear FLANK en combate cercano
            if in_close_combat and self.current_option == TacticalOption.FLANK:
                self.current_option = TacticalOption.ATTACK

            # -------------------------------------------------
            # EVENT LOG
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
                        "description": self.current_option.description(),
                        "category": self.current_option.category(),
                        "turn": state.turn,
                        "context": context,
                        "policy_info": self.policy.last_decision_info,
                    }
                })

        # -------------------------------------------------
        # decremento estándar
        # -------------------------------------------------
        self.steps_remaining -= 1

        # -------------------------------------------------
        # ejecutar
        # -------------------------------------------------
        return self.executor.execute(
            state,
            self.current_option
        )
