import random
from pathlib import Path

import numpy as np
import torch
import torch.optim as optim

from assault_sim.config.ppo_config import PPOConfig
from assault_sim.engine.env_factory import make_env
from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.train.ppo_schedule import ppo_schedule
from assault_sim.train.ppo_trainer import ppo_update
from assault_sim.rewards.shaped_reward import ShapedReward
from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.decision.decision_engine_controller import DecisionEngineController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.evaluation.evaluator import Evaluator


REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "sim_config.yaml"
ENV_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "env_config.json"


def main():
    seed = PPOConfig.SEED
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    env = make_env(
        config_path=SIM_CONFIG_PATH,
        env_config_path=ENV_CONFIG_PATH,
        rl_side=PPOConfig.RL_SIDE,
        scenario=PPOConfig.SCENARIO,
        reward_fn=ShapedReward(rl_side=PPOConfig.RL_SIDE),
        seed=seed,
    )

    obs = env.reset()
    next_obs, reward, done, info = env.step(None)
    assert len(obs.shape) == 1
    assert len(next_obs.shape) == 1
    assert isinstance(reward, float)
    assert isinstance(done, bool)
    assert isinstance(info, dict)

    input_dim = obs.shape[0]
    device = torch.device("cpu")
    policy = PolicyNet(input_dim=input_dim, num_options=len(TacticalOption)).to(device)
    optimizer = optim.Adam(policy.parameters(), lr=PPOConfig.LR)

    n = PPOConfig.SEQ_LEN * 2
    batch = {
        "obs": torch.randn(n, input_dim, dtype=torch.float32, device=device),
        "actions": torch.randint(0, len(TacticalOption), (n,), dtype=torch.long, device=device),
        "attack_modes": torch.randint(0, 2, (n,), dtype=torch.long, device=device),
        "old_logp": torch.randn(n, dtype=torch.float32, device=device),
        "returns": torch.randn(n, dtype=torch.float32, device=device),
        "advantages": torch.randn(n, dtype=torch.float32, device=device),
        "teacher": torch.randint(0, len(TacticalOption), (n,), dtype=torch.long, device=device),
        "dones": torch.zeros(n, dtype=torch.float32, device=device),
    }
    stats = ppo_update(policy, optimizer, batch, ppo_schedule(0), device, PPOConfig.ENTROPY_COEF)
    assert isinstance(stats, dict) and "loss" in stats

    eval_env = make_env(
        config_path=SIM_CONFIG_PATH,
        env_config_path=ENV_CONFIG_PATH,
        rl_side=PPOConfig.RL_SIDE,
        scenario=PPOConfig.SCENARIO,
        reward_fn=ShapedReward(rl_side=PPOConfig.RL_SIDE),
        seed=seed,
    )
    controller = DecisionEngineController(
        rl_side=PPOConfig.RL_SIDE,
        decision_engine=DecisionEngine(),
        option_policy=OptionPolicy(policy),
        heuristic=TacticalPathHeuristic(),
        sim_env=eval_env.sim,
    )
    controller.training_mode = False
    evaluator = Evaluator(eval_env, controller, None, PPOConfig.RL_SIDE, max_steps=5)
    out = evaluator.evaluate(1)
    assert isinstance(out, list)

    print("SMOKE_CHECK_OK")


if __name__ == "__main__":
    main()

