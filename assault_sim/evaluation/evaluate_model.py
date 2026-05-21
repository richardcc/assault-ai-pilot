import torch
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.decision.controller_adapter import RLvsHeuristicController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.evaluation.results import ResultsAnalyzer
from assault_sim.evaluation.eval_dashboard import EvalDashboard
from assault_sim.evaluation.evaluator import Evaluator  # ✅ CLAVE
from assault_sim.debug.debug_config import DebugConfig

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
RL_SIDE = "US"
EPISODES = 500

CONFIG_PATH = Path("C:/repos/python/assault/assault_sim/config/sim_config.yaml")
ENV_CONFIG = Path("C:/repos/python/assault/assault_sim/config/env_config.json")
CHECKPOINT = Path("models/latest.pt")


# -------------------------------------------------
# BUILD MODEL
# -------------------------------------------------
def load_model():

    print(">>> Loading model")

    sim_config = load_sim_config(CONFIG_PATH)
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    
    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=True)  # 🔥 ESTA ES LA CLAVE
    )


    env = TrainingEnv(
        sim_env,
        env_config_path=ENV_CONFIG,
        rl_side=RL_SIDE,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    policy_net = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    )

    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    policy_net.load_state_dict(checkpoint)
    policy_net.eval()

    return policy_net


# -------------------------------------------------
# BUILD CONTROLLER
# -------------------------------------------------
def build_controller(policy_net, sim_env):

    option_policy = OptionPolicy(policy_net)
    heuristic = TacticalPathHeuristic()
    executor = OptionExecutor(heuristic)

    hrl_controller = HRLController(
        option_policy=option_policy,
        option_executor=executor,
        rl_side=RL_SIDE,
        event_bus=sim_env.event_bus,
    )

    controller = RLvsHeuristicController(
        rl_side=RL_SIDE,
        hrl_controller=hrl_controller,
        heuristic=heuristic,
        executor=executor,
    )

    return controller


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

    return env, sim_env


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():

    print(">>> EVALUATION PIPELINE START")

    policy_net = load_model()
    print("✅ Model loaded")

    env, sim_env = build_env()
    controller = build_controller(policy_net, sim_env)

    print(f">>> RL SIDE: {RL_SIDE}")

    dashboard = EvalDashboard()

    # ✅ USAR EVALUATOR (CLAVE)
    evaluator = Evaluator(
        env=env,
        rl_controller=controller,
        enemy_controller=controller.heuristic,
        rl_side=RL_SIDE,
    )

    # ✅ ejecutar episodios
    results = evaluator.evaluate(EPISODES)

    # ✅ dashboard
    for r in results:
        dashboard.add_episode(r)

    # ✅ análisis
    analyzer = ResultsAnalyzer(results, RL_SIDE)
    analyzer.print_report()

    dashboard.save_csv("metrics.csv")
    dashboard.plot_all()

    print("\n>>> EVALUATION FINISHED")


if __name__ == "__main__":
    main()