from assault_sim.strategy.formation_strategy import FormationStrategyEngine
from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption


class DecisionEngineController:

    def __init__(self, rl_side, decision_engine, option_policy, heuristic, sim_env):
        self.rl_side = rl_side
        self.decision_engine = decision_engine
        self.option_policy = option_policy
        self.heuristic = heuristic
        self.sim_env = sim_env

        # PPO tracking
        self.current_option = None
        self.current_attack_mode = 0
        self.last_logp = None
        self.last_value = None

        # L3 strategy layer
        self.formation_engine = FormationStrategyEngine()
        self.current_strategy = None

        self.debug = False

        # Train vs evaluation mode
        self.training_mode = True

    # -------------------------------------------------
    def reset(self):
        """
        Reset per-episode state.
        This is critical for LSTM stability and strategy consistency.
        """
        if hasattr(self.option_policy, "reset_hidden"):
            self.option_policy.reset_hidden()

        # Reset strategy state
        self.formation_engine.current_strategy = None
        self.formation_engine.remaining_steps = 0
        self.current_strategy = None

    # -------------------------------------------------
    def act(self, state, side, unit, obs):

        # =================================================
        # RL SIDE
        # =================================================
        if side == self.rl_side:

            # -------------------------------------------------
            # L3: Update strategy every step
            # -------------------------------------------------
            game_state = self.sim_env.game_state
            strategy = self.formation_engine.update(game_state, self.rl_side)
            self.current_strategy = strategy

            # -------------------------------------------------
            # L2: Sample option from policy (single call)
            # -------------------------------------------------
            option, attack_mode, logp, value = self.option_policy.choose_option(obs)

            # -------------------------------------------------
            # 🔥 L3 → L2 bias (key fix)
            # -------------------------------------------------
            if strategy is not None:

                if strategy.name == "ATTACK":
                    if option == TacticalOption.ADVANCE:
                        option = TacticalOption.ATTACK

                elif strategy.name == "PUSH_VP":
                    if option == TacticalOption.HOLD:
                        option = TacticalOption.ADVANCE

                elif strategy.name == "HOLD_VP":
                    if option == TacticalOption.ADVANCE:
                        option = TacticalOption.HOLD

                elif strategy.name == "CLEANUP":
                    option = TacticalOption.ATTACK

            # Store PPO outputs
            self.current_option = option
            self.current_attack_mode = attack_mode if attack_mode is not None else 0
            self.last_logp = logp
            self.last_value = value

            # -------------------------------------------------
            # DecisionEngine only active during evaluation
            # -------------------------------------------------
            intent = None
            if not self.training_mode:
                intent = self.decision_engine.compute_intent(self.sim_env)

            # -------------------------------------------------
            # Intent-based execution (evaluation only)
            # -------------------------------------------------
            if intent:
                chosen_unit, action = intent

                if chosen_unit and chosen_unit.unit_id == unit.unit_id:
                    action.unit_id = unit.unit_id
                    self.sim_env.runtime.activated_units.add(unit.unit_id)
                    return action

            # -------------------------------------------------
            # PPO + heuristic execution (training path)
            # -------------------------------------------------
            action = self.heuristic.choose_action(state, unit, option)

            if action is None:
                if self.debug:
                    print(f"[RL] {unit.unit_id} -> WAIT (fallback)")
                action = WaitAction(unit.unit_id)

            action.unit_id = unit.unit_id
            self.sim_env.runtime.activated_units.add(unit.unit_id)

            return action

        # =================================================
        # ENEMY SIDE (heuristic only)
        # =================================================
        options_to_try = [
            TacticalOption.ATTACK,
            TacticalOption.FLANK,
            TacticalOption.ADVANCE,
            TacticalOption.RETREAT,
            TacticalOption.HOLD,
        ]

        action = None

        for opt in options_to_try:
            action = self.heuristic.choose_action(state, unit, opt)

            if action is not None:
                if self.debug:
                    print(f"[ENEMY] {unit.unit_id} -> {opt.name}")
                break

        if action is None:
            if self.debug:
                print(f"[ENEMY] {unit.unit_id} -> WAIT (fallback)")
            action = WaitAction(unit.unit_id)

        action.unit_id = unit.unit_id
        self.sim_env.runtime.activated_units.add(unit.unit_id)

        return action
