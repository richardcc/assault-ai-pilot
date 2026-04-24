import os
import time
import torch

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.logger import configure

from assault_env.env import AssaultEnv
from assault_env.scenario_base import simple_duel_level7_P4_2v2_from_json


# ------------------------------------------------------------
# Environment factory
# ------------------------------------------------------------

def make_env():
    """
    Factory function required by DummyVecEnv.
    P4: symmetric 2 vs 2
    """
    return AssaultEnv(
        scenario_builder=simple_duel_level7_P4_2v2_from_json,
        training=True,
        max_turns=200,
    )


# ------------------------------------------------------------
# Training launcher
# ------------------------------------------------------------

if __name__ == "__main__":

    RUN_ID = "p4_2v2_roles"
    LOG_DIR = f"logs/ppo_level7/{RUN_ID}"
    os.makedirs(LOG_DIR, exist_ok=True)

    print("=== PPO TRAIN LAUNCHER (P4 – 2 vs 2 SYMMETRIC) ===", flush=True)
    print("CUDA available:", torch.cuda.is_available(), flush=True)
    print("Log dir:", os.path.abspath(LOG_DIR), flush=True)
    print("==============================================", flush=True)

    # Vectorized environment (single env, SB3 requirement)
    env = DummyVecEnv([make_env])

    # Logger (stdout + tensorboard)
    logger = configure(LOG_DIR, ["stdout", "tensorboard"])

    # PPO configuration (UNCHANGED from P1–P3)
    model = PPO(
        policy="MultiInputPolicy",
        env=env,
        device="cuda" if torch.cuda.is_available() else "cpu",
        verbose=2,
        n_steps=256,
        batch_size=64,
        n_epochs=4,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
    )

    model.set_logger(logger)

    TOTAL_STEPS = 200_000

    start_time = time.time()
    try:
        model.learn(total_timesteps=TOTAL_STEPS)
    except KeyboardInterrupt:
        print("\nTraining interrupted by user (Ctrl+C)", flush=True)
    finally:
        elapsed = time.time() - start_time
        print(f"Training stopped after {elapsed:.1f}s", flush=True)

        os.makedirs("models", exist_ok=True)
        model_path = f"models/ppo_level7_{RUN_ID}"
        model.save(model_path)
        print("Model saved to:", model_path, flush=True)