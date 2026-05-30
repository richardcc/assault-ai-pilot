from assault_model.state.game_state import GameState
from assault_model.actions.status import WaitAction


class DecisionEngineController:
    def __init__(self, env, decision_engine=None, heuristic_controller=None):
        """
        Simulation controller for DecisionEngine-based execution.

        :param env: SimEnv instance
        :param decision_engine: planner (independent, no RL)
        :param heuristic_controller: optional fallback
        """
        self.env = env
        self.decision_engine = decision_engine
        self.heuristic_controller = heuristic_controller

    # --------------------------------------------------
    # ✅ MAIN DECISION ROUTING
    # --------------------------------------------------
    def _select_action(self, state, active_side, available_units):
        """
        Decision priority:
        1. DecisionEngine (planner)
        2. Heuristic fallback
        3. Safe fallback (wait)
        """

        # ✅ 1. DecisionEngine (PRIMARY)
        if self.decision_engine:
            intent = self.decision_engine.compute_intent(self.env)

            if intent and isinstance(intent, tuple) and len(intent) == 2:
                unit, action = intent
                return unit, action

        # ✅ 2. Heuristic fallback
        if self.heuristic_controller:
            from assault_sim.rl.tactical_options import TacticalOption

            unit = available_units[0]

            action = self.heuristic_controller.choose_action(
                state,
                unit,
                TacticalOption.ATTACK
            )

            if action:
                return unit, action

        # ✅ 3. Safe fallback
        unit = available_units[0]
        return unit, WaitAction(unit.unit_id)

    # --------------------------------------------------
    # ✅ MAIN LOOP
    # --------------------------------------------------
    def run_simulation(self):
        state = self.env.reset()
        steps = 0

        print("[SIM START] DecisionEngine simulation started.")

        while not self.env.game_state.done:
            runtime = self.env.runtime
            active_side = getattr(runtime, "active_side", None)

            # --------------------------------------------------
            # ✅ FAILSAFE
            # --------------------------------------------------
            if not active_side:
                state, _, done, _ = self.env.step(WaitAction("SYSTEM"))
                if done:
                    break
                continue

            # --------------------------------------------------
            # ✅ AVAILABLE UNITS
            # --------------------------------------------------
            available_units = [
                u for u in self.env.game_state.units
                if u.side == active_side
                and getattr(u, "alive", True)
                and u.unit_id not in runtime.activated_units
            ]

            # --------------------------------------------------
            # ✅ TURN HANDLING
            # --------------------------------------------------
            if not available_units:
                state, _, done, _ = self.env.step(WaitAction("SYSTEM"))
                if done:
                    break
                continue

            # --------------------------------------------------
            # ✅ DECISION
            # --------------------------------------------------
            current_unit, action_to_execute = self._select_action(
                state,
                active_side,
                available_units
            )

            # --------------------------------------------------
            # ✅ SAFETY
            # --------------------------------------------------
            if action_to_execute and current_unit:
                action_to_execute.unit_id = current_unit.unit_id

            # --------------------------------------------------
            # ✅ MARK ACTIVATED
            # --------------------------------------------------
            runtime.activated_units.add(current_unit.unit_id)

            # --------------------------------------------------
            # ✅ EXECUTE
            # --------------------------------------------------
            state, _, done, _ = self.env.step(action_to_execute)
            steps += 1

            # --------------------------------------------------
            # ✅ CLEAR DECISION ENGINE CACHE
            # --------------------------------------------------
            if self.decision_engine and hasattr(self.decision_engine, "clear_cache"):
                self.decision_engine.clear_cache()

            # --------------------------------------------------
            # ✅ DEBUG OUTPUT
            # --------------------------------------------------
            action_name = getattr(
                action_to_execute,
                "action_id",
                action_to_execute.__class__.__name__
            )

            print(
                f"[STEP {steps:03d}] "
                f"Side: {active_side} | "
                f"Unit: {current_unit.unit_id} | "
                f"Action: {action_name}"
            )

        # --------------------------------------------------
        # ✅ END
        # --------------------------------------------------
        print(
            f"[SIM DONE] Winner: {self.env.game_state.winner} | "
            f"Reason: {getattr(self.env.game_state, 'end_reason', 'N/A')} | "
            f"Steps: {steps}"
        )

        return self.env.game_state
