import os
import torch
import time

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.logger import configure

from assault_env.env import AssaultEnv


# -----------------------------
# Env factories
# -----------------------------
def make_env():
    return AssaultEnv()


if __name__ == "__main__":
    # -----------------------------
    # Clean, fixed run (no mixing)
    # -----------------------------
    RUN_ID = "current"
    LOG_DIR = f"logs/ppo_level3_penalty/{RUN_ID}"

    os.makedirs(LOG_DIR, exist_ok=True)

    print("=== PPO TRAIN LAUNCHER ===", flush=True)
