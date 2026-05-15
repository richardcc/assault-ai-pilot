from pathlib import Path

from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.config.config_loader import load_sim_config


def make_env(
    config_path: Path,
    rl_side: str,
    scenario: str,
    controller=None,
) -> TrainingEnv:

    config = load_sim_config(config_path)
    config.scenario_name = scenario

    sim = SimEnv(config, controller=controller)

    env = TrainingEnv(
        sim,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=rl_side,
    )

    return env


# ✅ ALIAS PROFESIONAL
create_env = make_env
