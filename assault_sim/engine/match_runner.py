from assault_model.actions.status import WaitAction
from assault_sim.engine.activation_manager import ActivationManager


class MatchRunner:

    def __init__(self, env, controller=None):
        self.env = env
        self.controller = controller

        unit_selector = (
            controller.select_best_unit
            if controller and hasattr(controller, "select_best_unit")
            else None
        )

        self.activation_manager = ActivationManager(
            env.sim.game_state,
            unit_selector=unit_selector
        )

    # -------------------------------------------------
    def reset(self):
        obs = self.env.reset()

        unit_selector = (
            self.controller.select_best_unit
            if self.controller and hasattr(self.controller, "select_best_unit")
            else None
        )

        self.activation_manager = ActivationManager(
            self.env.sim.game_state,
            unit_selector=unit_selector
        )

        return obs

    # -------------------------------------------------
    def step(self, controller, obs):

        state = self.env.sim.game_state

        # -----------------------------------------
        # NEXT ACTIVATION
        # -----------------------------------------
        side, unit = None, None

        for _ in range(len(self.activation_manager.sides) * 2):
            side, unit = self.activation_manager.next_activation()
            if unit is not None:
                break

        # -----------------------------------------
        # TURN END
        # -----------------------------------------
        if unit is None:

            next_obs, reward, done, info = self.env.step(
                WaitAction("SYSTEM")
            )

            self.activation_manager = ActivationManager(
                self.env.sim.game_state
            )

            return {
                "obs": next_obs,
                "reward": reward,
                "done": done,
                "info": info,
                "side": None,
                "unit": None,
                "is_turn_end": True,
                "is_rl_turn_end": False,
            }

        # -----------------------------------------
        # ✅ ACTION (NUEVO MODELO LIMPIO)
        # -----------------------------------------
        # 🔥 DELEGAR COMPLETAMENTE EN EL CONTROLLER
        action = controller.act(state, side, unit, obs)

        # fallback safety (muy importante)
        if action is None:
            print(f"[WARN] {side}:{unit.unit_id} returned None → WAIT")
            action = WaitAction(unit.unit_id)

        next_obs, reward, done, info = self.env.step(action)

        # -----------------------------------------
        # SYNC SCHEDULER
        # -----------------------------------------
        self.activation_manager.state = self.env.sim.game_state
        self.activation_manager.blocked_units = (
            self.env.sim.runtime.activated_units.copy()
        )

        # -----------------------------------------
        # DETECT NEXT SIDE
        # -----------------------------------------
        next_side = None

        unit_selector = (
            self.controller.select_best_unit
            if self.controller and hasattr(self.controller, "select_best_unit")
            else None
        )

        temp_am = ActivationManager(
            self.env.sim.game_state,
            unit_selector=unit_selector
        )

        temp_am.blocked_units = self.activation_manager.blocked_units.copy()

        for _ in range(len(temp_am.sides)):
            s, u = temp_am.next_activation()
            if u is not None:
                next_side = s
                break

        # -----------------------------------------
        # RL TURN END
        # -----------------------------------------
        is_rl_turn_end = (
            side == controller.rl_side and
            (next_side is None or next_side != controller.rl_side)
        )

        return {
            "obs": next_obs,
            "reward": reward,
            "done": done,
            "info": info,
            "side": side,
            "unit": unit,
            "action": action,
            "is_turn_end": False,
            "is_rl_turn_end": is_rl_turn_end,
        }