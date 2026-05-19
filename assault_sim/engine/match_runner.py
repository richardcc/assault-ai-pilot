from assault_model.actions.status import WaitAction
from assault_sim.engine.activation_manager import ActivationManager


class MatchRunner:

    def __init__(self, env):
        self.env = env
        self.activation_manager = ActivationManager(env.sim.game_state)

    def reset(self):
        obs = self.env.reset()
        self.activation_manager = ActivationManager(self.env.sim.game_state)
        return obs

    def step(self, controller, obs):

        state = self.env.sim.game_state

        # -----------------------------------------
        # Next activation
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
        # ACTION
        # -----------------------------------------
        action = controller.act(state, side, unit, obs)

        if action is None:
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
        # ✅ SAFE NEXT SIDE DETECTION (SIN ROMPER ESTADO)
        # -----------------------------------------
        next_side = None

        # ✅ Creamos copia temporal del scheduler
        temp_am = ActivationManager(self.env.sim.game_state)
        temp_am.blocked_units = self.activation_manager.blocked_units.copy()

        for _ in range(len(temp_am.sides)):
            s, u = temp_am.next_activation()
            if u is not None:
                next_side = s
                break

        # -----------------------------------------
        # ✅ DETECT FIN TURNO RL
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
