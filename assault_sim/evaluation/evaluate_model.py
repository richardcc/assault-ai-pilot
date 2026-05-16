# assault_sim/evaluation/evaluate_model.py

import torch
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.evaluation.evaluator import Evaluator
from assault_sim.evaluation.results import ResultsAnalyzer
from assault_sim.evaluation.eval_dashboard import EvalDashboard


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
RL_SIDE = "US"
EPISODES = 500
MAX_STEPS = 200

CONFIG_PATH = Path("assault_sim/config/sim_config.yaml")
ENV_CONFIG = Path("assault_sim/config/env_config.json")
CHECKPOINT = Path("assault_sim/checkpoints/ppo_US.pt")


# -------------------------------------------------
# BUILD MODEL
# -------------------------------------------------
def load_model():

    checkpoint = torch.load(CHECKPOINT)

    policy = PolicyNet(
        input_dim=checkpoint["input_dim"],
        max_actions=checkpoint["max_actions"],
    )

    policy.load_state_dict(checkpoint["model_state_dict"])
    policy.eval()

    return policy


# -------------------------------------------------
# BUILD CONTROLLERS
# -------------------------------------------------
def build_controllers(policy):

    heuristic = TacticalPathHeuristic()

    # RL
    option_policy = OptionPolicy(policy)
    executor_rl = OptionExecutor(heuristic)

    rl_controller = HRLController(
        option_policy=option_policy,
        option_executor=executor_rl,
        rl_side=RL_SIDE,
    )

    # ENEMY (baseline simple)
    executor_enemy = OptionExecutor(heuristic)

    class EnemyController:
        def choose_action(self, state, obs):
            return executor_enemy.execute(
                state,
                TacticalOption.ATTACK
            )

    enemy_controller = EnemyController()

    return rl_controller, enemy_controller


# -------------------------------------------------
# BUILD ENV
# -------------------------------------------------
def build_env():

    sim_config = load_sim_config(CONFIG_PATH)
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    sim_env = SimEnv(sim_config)

    env = TrainingEnv(
        sim_env,
        env_config_path=ENV_CONFIG,
        rl_side=RL_SIDE,
    )

    return env


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():

    print(">>> EVALUATION PIPELINE START")

    # model
    policy = load_model()
    print("✅ Model loaded")

    # controllers
    rl_controller, enemy_controller = build_controllers(policy)

    # env
    env = build_env()

    # evaluator
    evaluator = Evaluator(
        env,
        rl_controller,
        enemy_controller,
        RL_SIDE,
        max_steps=MAX_STEPS
    )

    # dashboard
    dashboard = EvalDashboard()

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    results = evaluator.evaluate(EPISODES)

    for r in results:
        dashboard.add_episode(r)

    # -------------------------------------------------
    # ANALYSIS
    # -------------------------------------------------
    analyzer = ResultsAnalyzer(results, RL_SIDE)

    analyzer.print_report()

    # -------------------------------------------------
    # DASHBOARD
    # -------------------------------------------------
    dashboard.save_csv("metrics.csv")
    dashboard.plot_all()

    print("\n>>> EVALUATION FINISHED")


# -------------------------------------------------
# ENTRY POINT
# -------------------------------------------------
if __name__ == "__main__":
    main()