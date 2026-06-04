from assault_sim.strategy.formation_strategy import FormationStrategyEngine
from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption

# ✅ NUEVO
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.decision.action_bridge import ActionBridge
from assault_sim.rl.state_encoder import encode_state


class DecisionEngineController:

    def __init__(self, rl_side, decision_engine, option_policy, heuristic, sim_env):
        self.rl_side = rl_side
        self.decision_engine = decision_engine
        self.option_policy = option_policy
        self.heuristic = heuristic
        self.sim_env = sim_env

        # ✅ NUEVO: executor real (CRÍTICO)
        # Temporarily disable bad-trade filtering to recover baseline attack behavior.
        self.executor = OptionExecutor(self.heuristic, avoid_bad_trades=False, adv_threshold=-0.5)

        # PPO tracking
        self.current_option = None
        self.current_option_sampled = None
        self.current_option_resolved = None
        self.current_attack_mode = 0
        self.last_logp = None
        self.last_value = None
        self.last_decision_trace = None

        # ✅ Observación por-unidad realmente consumida por la política.
        # El rollout la guarda para mantener PPO consistente.
        self.last_obs = None

        # L3 strategy layer
        self.formation_engine = FormationStrategyEngine()
        self.current_strategy = None

        self.debug = False

        # Train vs evaluation mode
        self.training_mode = True
        self.strict_on_policy = True
        self.action_bridge = ActionBridge()

    # -------------------------------------------------
    def reset(self):
        """
        Reset per-episode state.
        Critical for LSTM + strategy consistency.
        """
        if hasattr(self.option_policy, "reset_hidden"):
            self.option_policy.reset_hidden()

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
            # L3: STRATEGY
            # -------------------------------------------------
            game_state = self.sim_env.game_state
            strategy = self.formation_engine.update(game_state, self.rl_side)
            self.current_strategy = strategy

            # -------------------------------------------------
            # ✅ OBSERVACIÓN POR-UNIDAD (CLAVE)
            # Re-codificamos el obs usando la unidad activa para que la
            # política perciba dirección/distancia al enemigo. Guardamos
            # el obs realmente consumido para que el rollout (PPO) sea
            # consistente con la entrada de la red.
            # -------------------------------------------------
            max_turns = getattr(
                getattr(self.sim_env, "scenario", None), "max_turns", None
            )

            obs = encode_state(
                game_state,
                unit=unit,
                rl_side=self.rl_side,
                max_turns=max_turns,
            )
            self.last_obs = obs

            # -------------------------------------------------
            # L2: POLICY (modelo RL)
            # -------------------------------------------------
            sampled_option, attack_mode, _logp, value = self.option_policy.choose_option(obs)
            strategy_name = getattr(strategy, "name", None) if strategy is not None else None
            resolved_option = self.action_bridge.resolve_option(
                sampled_option=sampled_option,
                strategy_name=strategy_name,
                training_mode=self.training_mode,
                strict_on_policy=self.strict_on_policy,
            )

            # -------------------------------------------------
            # STORE PPO OUTPUTS
            # -------------------------------------------------
            self.current_option_sampled = sampled_option
            self.current_option_resolved = resolved_option
            self.current_attack_mode = attack_mode if attack_mode is not None else 0
            self.last_value = value

            # -------------------------------------------------
            # DecisionEngine (solo en evaluación)
            # -------------------------------------------------
            intent = None
            if not self.training_mode:
                intent = self.decision_engine.compute_intent(self.sim_env)

            # -------------------------------------------------
            # INTENT EXECUTION (EVAL ONLY)
            # -------------------------------------------------
            if intent:
                chosen_unit, action = intent

                if chosen_unit and chosen_unit.unit_id == unit.unit_id:
                    action.unit_id = unit.unit_id
                    self.sim_env.runtime.activated_units.add(unit.unit_id)
                    return action

            # -------------------------------------------------
            # ✅ EJECUCIÓN REAL (CRÍTICO)
            # -------------------------------------------------
            action = self.executor.execute(
                state,
                unit,
                resolved_option,
                attack_mode=self.current_attack_mode
            )

            # fallback seguro
            if action is None:
                if self.debug:
                    print(f"[RL] {unit.unit_id} -> WAIT (fallback)")
                action = WaitAction(unit.unit_id)

            executed_option = self.action_bridge.infer_executed_option(
                action=action,
                fallback=resolved_option,
            )
            executed_attack_mode = self.current_attack_mode if executed_option == TacticalOption.ATTACK else 0
            self.current_attack_mode = executed_attack_mode
            self.current_option = executed_option
            self.last_logp = self.option_policy.log_prob_for(
                option=executed_option,
                attack_mode=executed_attack_mode,
            )
            self.last_decision_trace = self.action_bridge.build_trace(
                sampled_option=sampled_option,
                resolved_option=resolved_option,
                executed_option=executed_option,
                strategy_name=strategy_name,
            )

            action.unit_id = unit.unit_id
            self.sim_env.runtime.activated_units.add(unit.unit_id)

            if self.debug:
                print(f"[RL] {unit.unit_id} -> {executed_option.name}")

            return action

        # =================================================
        # ENEMY SIDE (heurística)
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