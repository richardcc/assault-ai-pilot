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
    env_config_path: Path | None = None,
    controller=None,
    reward_fn=None,
    seed: int | None = None,
    train_lean: bool = False,
) -> TrainingEnv:

    # ✅ cargar config
    config = load_sim_config(config_path)
    if scenario:
        config.scenario_name = scenario

    # ✅ crear SimEnv
    sim_env = SimEnv(
        config=config,
        controller=controller
    )

    # ✅ crear reward (CLAVE) si no se proporciona uno
    if reward_fn is None:
        reward_fn = ProgressiveReward(rl_side=rl_side)

    # ✅ TrainingEnv con reward explícito
    env = TrainingEnv(
        sim_env,
        env_config_path or config_path,
        rl_side,
        scenario_override=scenario,
        reward_fn=reward_fn,
        seed=seed,
        train_lean=train_lean,
    )

    return env


# -------------------------------------------------
# ✅ MULTI ENV
# -------------------------------------------------
def make_envs(
    config_path: Path,
    rl_side: str,
    scenario: str,
    env_config_path: Path | None = None,
    n_envs: int = 4,
):
    return [
        make_env(
            config_path=config_path,
            rl_side=rl_side,
            scenario=scenario,
            env_config_path=env_config_path,
        )
        for _ in range(n_envs)
    ]


# -------------------------------------------------
# ✅ ALIASES
# -------------------------------------------------
create_env = make_env
create_envs = make_envs