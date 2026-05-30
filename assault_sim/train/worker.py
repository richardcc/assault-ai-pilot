import torch

from assault_sim.engine.env_factory import make_env
from assault_sim.engine.rollout import collect_rollout

from assault_sim.config.ppo_config import PPOConfig

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.option_policy import OptionPolicy

from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

# ✅ IMPORT CORRECTO
from assault_sim.decision.decision_engine_controller import DecisionEngineController


def worker_loop(
    rollout_queue,
    config_path,
    scenario,
    weights_queue,
    progress_queue,
):

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    env = make_env(config_path, PPOConfig.RL_SIDE, scenario)

    obs = env.reset()
    input_dim = obs.shape[0]

    # -------------------------------------------------
    # MODEL
    # -------------------------------------------------
    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    ).to(device)

    # -------------------------------------------------
    # ✅ CONTROLLER (CORRECTO)
    # -------------------------------------------------
    decision_engine = DecisionEngine()
    option_policy = OptionPolicy(policy)
    heuristic = TacticalPathHeuristic()

    controller = DecisionEngineController(
        rl_side=PPOConfig.RL_SIDE,
        decision_engine=decision_engine,
        option_policy=option_policy,
        heuristic=heuristic,
        sim_env=env.sim,
    )

    # 🔥 CLAVE: activar modo training
    controller.training_mode = True

    # -------------------------------------------------
    # LOOP
    # -------------------------------------------------
    while True:

        # ✅ Sync weights
        if not weights_queue.empty():
            state_dict = weights_queue.get()
            policy.load_state_dict(state_dict)

        # ✅ Rollout
        rollout = collect_rollout(
            env,
            controller,
            max_steps=PPOConfig.ROLLOUT_STEPS
        )

        rollout_queue.put(rollout)