import json
from pathlib import Path


class TrainingEnv:
    """
    Wrapper NO intrusivo sobre SimEnv.

    - No modifica SimEnv
    - No toca debug ni observers
    - No decide acciones
    - Solo coordina ejecución y reward
    """

    def __init__(self, sim_env, env_config_path: Path):
        self.sim = sim_env  # SimEnv REAL (con debug ya activo)

        with open(env_config_path, "r", encoding="utf-8") as f:
            self.env_config = json.load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", None)

        self.current_step = 0
        self.prev_vp = None

    def reset(self):
        """
        Delegación pura a SimEnv.
        """
        obs = self.sim.reset()

        self.current_step = 0

        # Estado para reward diferencial
        if obs.vp_tracker:
            self.prev_vp = obs.vp_tracker.total_points
        else:
            self.prev_vp = 0

        return obs

    def step(self, action):
        """
        Delegación pura a SimEnv.step()

        action: Action del modelo (ya creada fuera)
        """
        obs, _, sim_done, info = self.sim.step(action)

        # Reward EXTERNO (no toca SimEnv)
        if obs.vp_tracker:
            current_vp = obs.vp_tracker.total_points
        else:
            current_vp = 0

        reward = current_vp - self.prev_vp
        self.prev_vp = current_vp

        self.current_step += 1

        done = sim_done
        if self.max_steps is not None and self.current_step >= self.max_steps:
            done = True

        return obs, reward, done, info
