import os
import time

import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.logger import configure
from stable_baselines3.common.callbacks import CallbackList, CheckpointCallback

from assault_env.env import AssaultEnv

# Policy y callback
from assault_runner.policies import ExplainableActorCriticPolicy
from assault_runner.rationale_callback import RationaleLossCallback

# ✅ ÚNICO REWARD
from assault_runner.rewards.reward_vp_control import RewardVPControl


# ------------------------------------------------------------
# PATHS
# ------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs", "ppo_mettete_i_piedi_terra")
MODEL_DIR = os.path.join(PROJECT_ROOT, "models")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)


# ------------------------------------------------------------
# REWARD WRAPPER
# ------------------------------------------------------------

class RewardWrapper(gym.Wrapper):
    def __init__(self, env, reward_fn):
        super().__init__(env)
        self.reward_fn = reward_fn

    def reset(self, **kwargs):
        self.reward_fn.reset()
        return self.env.reset(**kwargs)

    def step(self, action):
        obs, _, terminated, truncated, info = self.env.step(action)

        reward = self.reward_fn.compute(
            info=info,
            episode_outcome=info.get("episode_outcome"),
        )

        return obs, reward, terminated, truncated, info


# ------------------------------------------------------------
# ENV FACTORY (CANÓNICA)
# ------------------------------------------------------------

def make_env(seed=0):
    def _init():
        env = AssaultEnv(
            scenario_id="mettete_i_piedi_terra_1_min",
            seed=seed,
        )

        reward_fn = RewardVPControl()
        env = RewardWrapper(env, reward_fn)

        return env

    return _init


# ------------------------------------------------------------
# TRAINING
# ------------------------------------------------------------

if __name__ == "__main__":

    env = DummyVecEnv([make_env(seed=0)])

    logger = configure(LOG_DIR, ["stdout", "csv", "tensorboard"])

    model = PPO(
        policy=ExplainableActorCriticPolicy,
        env=env,
        verbose=1,
        tensorboard_log=LOG_DIR,
        device="auto",

        learning_rate=3e-4,
        n_steps=2048,
        batch_size=2048,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        vf_coef=0.5,
        max_grad_norm=0.5,
    )

    model.set_logger(logger)

    callbacks = CallbackList([
        RationaleLossCallback(verbose=1),
        CheckpointCallback(
            save_freq=100_000,
            save_path=MODEL_DIR,
            name_prefix="ppo_mettete_i_piedi_terra",
        ),
    ])

    print("▶ Starting PPO training")

    try:
        model.learn(
            total_timesteps=500_000,
            callback=callbacks,
            progress_bar=True,
        )
    except KeyboardInterrupt:
        print("⏹ Training interrupted by user")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    final_model_path = os.path.join(
        MODEL_DIR,
        f"ppo_mettete_i_piedi_terra_final_{timestamp}"
    )
    model.save(final_model_path)
    print(f"✅ Model saved to: {final_model_path}")