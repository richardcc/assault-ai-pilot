from pathlib import Path

from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.config.config_loader import load_sim_config


# -------------------------------------------------
# ✅ SINGLE ENV
# -------------------------------------------------
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


# -------------------------------------------------
# ✅ MULTI ENV (lista de envs)
# -------------------------------------------------
def make_envs(
    config_path: Path,
    rl_side: str,
    scenario: str,
    n_envs: int = 4,
):
    return [
        make_env(config_path, rl_side, scenario)
        for _ in range(n_envs)
    ]


# -------------------------------------------------
# ✅ ALIASES
# -------------------------------------------------
create_env = make_env
create_envs = make_envs