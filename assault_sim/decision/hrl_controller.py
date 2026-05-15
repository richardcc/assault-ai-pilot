from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.state_encoder import explainable_context


class HRLController:

    # -------------------------------------------------
    # ✅ HORIZON AJUSTADO
    # -------------------------------------------------
    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 6,
        TacticalOption.FLANK: 8,
        TacticalOption.ATTACK: 10,
        TacticalOption.HOLD: 3,
        TacticalOption.RETREAT: 4,
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
        # No control → salir
        # -------------------------------------------------
        if active is None or active.side != self.rl_side:
            return None

        # -------------------------------------------------
        # 🔥 NUEVO: detectar combate cercano
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
        # ✅ FIX 1: mantener ATTACK
        # -------------------------------------------------
        if not is_new_selection:
            if self.current_option == TacticalOption.ATTACK:
                self.steps_remaining -= 1
                return self.executor.execute(state, self.current_option)

        # -------------------------------------------------
        # ✅ FIX 2: forzar ATTACK si hay combate cercano
        # -------------------------------------------------
        if in_close_combat:
            self.current_option = TacticalOption.ATTACK
            self.steps_remaining = 2  # corto pero decisivo

        # -------------------------------------------------
        # Selección nueva (normal)
        # -------------------------------------------------
        elif is_new_selection:

            self.current_option = self.policy.choose_option(obs)
            self.steps_remaining = self.OPTION_HORIZON[self.current_option]

            # -------------------------------------------------
            # EVENT LOG (opcional)
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
        # decrementar contador
        # -------------------------------------------------
        self.steps_remaining -= 1

        # -------------------------------------------------
        # ejecutar
        # -------------------------------------------------
        return self.executor.execute(
            state,
            self.current_option
        )