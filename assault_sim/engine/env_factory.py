from pathlib import Path

from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.config.config_loader import load_sim_config
from assault_sim.rewards.progressive_reward import ProgressiveReward  # ✅ IMPORT CLAVE


# -------------------------------------------------
# ✅ SINGLE ENV
# -------------------------------------------------
def make_env(
    config_path: Path,
    rl_side: str,
    scenario: str,
    controller=None,
) -> TrainingEnv:

    # ✅ cargar config
    config = load_sim_config(config_path)

    # ✅ crear SimEnv
    sim_env = SimEnv(
        config=config,
        controller=controller
    )

    # ✅ crear reward (CLAVE)
    reward_fn = ProgressiveReward(rl_side=rl_side)

    # ✅ TrainingEnv con reward explícito
    env = TrainingEnv(
        sim_env,
        config_path,
        rl_side,
        reward_fn=reward_fn   # 💥 ESTO ARREGLA TODO
    )

    return env


# -------------------------------------------------
# ✅ MULTI ENV
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