import random
from pathlib import Path
from statistics import mean, pstdev

import numpy as np
import torch

from assault_sim.config.ppo_config import PPOConfig
from assault_sim.engine.env_factory import make_env
from assault_sim.rewards.shaped_reward import ShapedReward
from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.decision.decision_engine_controller import DecisionEngineController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.evaluation.evaluator import Evaluator


REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "sim_config.yaml"
ENV_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "env_config.json"

# P0 thresholds (short-run tolerance)
MAX_STD_WIN_RATE = 0.10
MAX_STD_DAMAGE_RATIO = 0.15
MAX_STD_AVG_REWARD = 0.15


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def run_short_eval(run_seed: int) -> dict:
    set_seed(run_seed)
    env = make_env(
        config_path=SIM_CONFIG_PATH,
        env_config_path=ENV_CONFIG_PATH,
        rl_side=PPOConfig.RL_SIDE,
        scenario=PPOConfig.SCENARIO,
        reward_fn=ShapedReward(rl_side=PPOConfig.RL_SIDE),
        seed=run_seed,
    )
    obs = env.reset()

    policy = PolicyNet(
        input_dim=obs.shape[0],
        num_options=len(TacticalOption),
    )
    policy.eval()

    controller = DecisionEngineController(
        rl_side=PPOConfig.RL_SIDE,
        decision_engine=DecisionEngine(),
        option_policy=OptionPolicy(policy),
        heuristic=TacticalPathHeuristic(),
        sim_env=env.sim,
    )
    controller.training_mode = False

    evaluator = Evaluator(
        env=env,
        rl_controller=controller,
        enemy_controller=None,
        rl_side=PPOConfig.RL_SIDE,
        max_steps=40,
    )
    results = evaluator.evaluate(2)
    if not results:
        return {"win_rate": 0.0, "damage_ratio": 0.0, "avg_reward": 0.0}

    wins = 0.0
    rl_damage = 0.0
    enemy_damage = 0.0
    avg_rewards = []
    for r in results:
        winner = r.get("winner")
        if winner == PPOConfig.RL_SIDE:
            wins += 1.0
        elif winner is None:
            wins += 0.5
        rl_damage += r.get("side", {}).get("RL", {}).get("damage", 0)
        enemy_damage += r.get("side", {}).get("ENEMY", {}).get("damage", 0)
        avg_rewards.append(float(r.get("avg_reward", 0.0)))

    return {
        "win_rate": wins / len(results),
        "damage_ratio": rl_damage / max(1.0, enemy_damage),
        "avg_reward": mean(avg_rewards) if avg_rewards else 0.0,
    }


def main():
    seed = PPOConfig.SEED
    runs = [run_short_eval(seed) for _ in range(3)]
    wr = [r["win_rate"] for r in runs]
    dr = [r["damage_ratio"] for r in runs]
    ar = [r["avg_reward"] for r in runs]

    std_wr = pstdev(wr) if len(wr) > 1 else 0.0
    std_dr = pstdev(dr) if len(dr) > 1 else 0.0
    std_ar = pstdev(ar) if len(ar) > 1 else 0.0

    print("=== REPRO CHECK (P0) ===")
    print(f"seed={seed} runs={len(runs)}")
    print(f"win_rate runs={wr} std={std_wr:.4f}")
    print(f"damage_ratio runs={dr} std={std_dr:.4f}")
    print(f"avg_reward runs={ar} std={std_ar:.4f}")

    ok = (
        std_wr <= MAX_STD_WIN_RATE
        and std_dr <= MAX_STD_DAMAGE_RATIO
        and std_ar <= MAX_STD_AVG_REWARD
    )

    if ok:
        print("REPRO_CHECK_OK")
    else:
        raise SystemExit(
            "REPRO_CHECK_FAIL: std thresholds exceeded "
            f"(wr<={MAX_STD_WIN_RATE}, dr<={MAX_STD_DAMAGE_RATIO}, ar<={MAX_STD_AVG_REWARD})"
        )


if __name__ == "__main__":
    main()

