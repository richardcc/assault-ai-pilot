from assault_sim.config import ppo_config
from assault_sim.train import train_ppo

# Small, fast config overrides for a quick test run
ppo_config.PPOConfig.TOTAL_UPDATES = 40
ppo_config.PPOConfig.NUM_ENVS = 2
ppo_config.PPOConfig.ROLLOUT_STEPS = 16
ppo_config.PPOConfig.BATCH_ROLLOUTS = 2
ppo_config.PPOConfig.ENTROPY_COEF = 0.05

if __name__ == '__main__':
    train_ppo.main()
