import json
from pathlib import Path

from assault_sim.sim_env import SimEnv
from assault_sim.action_catalog import ActionCatalog
from assault_sim.rewards.vp_difference import VPDifferenceReward
from assault_sim.heuristics import get_heuristic_policy


class TrainingEnv:
    def __init__(self, sim_config, env_config_path: Path):
        with open(env_config_path) as f:
            self.env_cfg = json.load(f)

        self.sim = SimEnv(sim_config, debug_config=sim_config.debug)

        self.max_steps = self.env_cfg["environment"]["max_steps"]
        self.step_count = 0

        # reward function
        self.reward_fn = VPDifferenceReward(
            normalize=self.env_cfg["rewards"]["default"].get("normalize", False)
        )

        # policies per side
        self.policies = {}
        for side, cfg in self.env_cfg["sides"].items():
            if cfg["role"] == "heuristic":
                self.policies[side] = get_heuristic_policy(cfg["policy"])
            else:
                self.policies[side] = None  # learning agent placeholder

        self.prev_vp = None

    def reset(self):
        obs = self.sim.reset()
        self.step_count = 0
        self.prev_vp = obs.vp_tracker.total_points
        return obs

    def step(self):
        state = self.sim.game_state

        # 🔹 elegir acción (fase 1: una acción global)
        action = ActionCatalog(state).actions()[0]

        obs, _, sim_done, info = self.sim.step(action)

        # reward desacoplado
        reward = self.reward_fn(self.prev_vp, obs.vp_tracker.total_points)
        self.prev_vp = obs.vp_tracker.total_points

        self.step_count += 1
        done = sim_done or self.step_count >= self.max_steps

        return obs, reward, done, info