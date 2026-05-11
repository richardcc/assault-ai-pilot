from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.state_encoder import explainable_context


class HRLController:
    """
    Hierarchical RL controller.

    Decides WHEN to select a new tactical option and
    delegates execution to heuristics.
    """

    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 5,
        TacticalOption.FLANK: 6,
        TacticalOption.ATTACK: 2,
        TacticalOption.HOLD: 1,
        TacticalOption.RETREAT: 3,
    }

    def __init__(self, option_policy, option_executor, rl_side, event_bus=None):
        self.policy = option_policy
        self.executor = option_executor
        self.rl_side = rl_side
        self.event_bus = event_bus

        self.current_option = None
        self.steps_remaining = -1  # force first decision

    def choose_action(self, state, obs):
        active = state.active_unit
        if active is None or active.side != self.rl_side:
            return None

        is_new_selection = (
            self.current_option is None or self.steps_remaining <= 0
        )

        if is_new_selection:
            self.current_option = self.policy.choose_option(obs)
            self.steps_remaining = self.OPTION_HORIZON[self.current_option]

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

        self.steps_remaining -= 1

        return self.executor.execute(
            self.current_option,
            state,
            active
        )