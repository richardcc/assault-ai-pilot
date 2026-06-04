import torch
import random
import numpy as np

from assault_sim.engine.env_factory import make_env
from assault_sim.engine.rollout import collect_rollout

from assault_sim.config.ppo_config import PPOConfig

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.option_policy import OptionPolicy

from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.decision.decision_engine_controller import DecisionEngineController


def worker_loop(
    rollout_queue,
    sim_config_path,
    env_config_path,
    scenario,
    weights_queue,
    progress_queue,
    reward_fn=None,
    base_seed: int = 42,
    worker_id: int = 0,
    rl_side: str | None = None,
    rollout_steps: int | None = None,
):
    effective_rl_side = rl_side or PPOConfig.RL_SIDE
    effective_rollout_steps = int(rollout_steps or PPOConfig.ROLLOUT_STEPS)


    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    worker_seed = int(base_seed) + int(worker_id)
    random.seed(worker_seed)
    np.random.seed(worker_seed)
    torch.manual_seed(worker_seed)

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    env = make_env(
        config_path=sim_config_path,
        env_config_path=env_config_path,
        rl_side=effective_rl_side,
        scenario=scenario,
        reward_fn=reward_fn,
        seed=worker_seed,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    # -------------------------------------------------
    # MODEL
    # -------------------------------------------------
    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    ).to(device)
    policy.eval()

    # -------------------------------------------------
    # CONTROLLER
    # -------------------------------------------------
    decision_engine = DecisionEngine()
    option_policy = OptionPolicy(policy)
    heuristic = TacticalPathHeuristic()

    controller = DecisionEngineController(
        rl_side=effective_rl_side,
        decision_engine=decision_engine,
        option_policy=option_policy,
        heuristic=heuristic,
        sim_env=env.sim,
    )

    controller.training_mode = True

    # -------------------------------------------------
    # LOOP
    # -------------------------------------------------
    while True:

        # ✅ Sync weights
        if not weights_queue.empty():
            state_dict = weights_queue.get()
            policy.load_state_dict(state_dict)

        # ✅ Rollout normal
        with torch.no_grad():
            rollout = collect_rollout(
                env,
                controller,
                max_steps=effective_rollout_steps
            )

        # =================================================
        # ✅ 🔥 NUEVO: REWARD POR ACCIÓN
        # =================================================
        reward_tracker = {}

        # 👇 asumimos que rollout trae "infos" y "rewards"
        for reward, l2 in zip(rollout["rewards"], rollout["l2"]):

            action_name = l2 if l2 is not None else "UNKNOWN"

            if action_name not in reward_tracker:
                reward_tracker[action_name] = {
                    "sum": 0.0,
                    "count": 0
                }

            reward_tracker[action_name]["sum"] += reward
            reward_tracker[action_name]["count"] += 1

        # ✅ añadir al rollout
        rollout["reward_by_action"] = reward_tracker

        rollout_queue.put(rollout)