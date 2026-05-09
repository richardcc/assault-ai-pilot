# assault_sim/runners/run_match_rl_vs_heuristic.py
#
# HRL-enabled replay:
# - RL chooses tactical OPTIONS (not engine actions)
# - Heuristics execute those options
# - TrainingEnv remains untouched

import torch
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.debug.debug_config import DebugConfig


def main():
    # =================================================
    # DEFINE RL SIDE (MUST MATCH TRAINING)
    # =================================================
    rl_side = "US"        # "GE" or "US"
    enemy_side = "GE" if rl_side == "US" else "US"

    print(f">>> Replaying HRL: RL ({rl_side}) vs Heuristic ({enemy_side})")

    # -------------------------------------------------
    # Load trained PPO checkpoint
    # -------------------------------------------------
    checkpoint_path = (
        Path(__file__).resolve()
        .parent.parent
        / "checkpoints"
        / f"ppo_{rl_side}_phase01_HRL.pt"
    )

    checkpoint = torch.load(checkpoint_path, map_location="cpu")

    policy = PolicyNet(
        input_dim=checkpoint["input_dim"],
        max_actions=checkpoint["max_actions"],
    )
    policy.load_state_dict(checkpoint["model_state_dict"])
    policy.eval()

    print(">>> PPO model loaded (option-level policy)")

    # -------------------------------------------------
    # HRL Controllers
    # -------------------------------------------------
    option_policy = OptionPolicy(policy)

    heuristic_controller = TacticalPathHeuristic()
    option_executor = OptionExecutor(heuristic_controller)

    hrl_controller = HRLController(
        option_policy=option_policy,
        option_executor=option_executor,
        rl_side=rl_side,
    )

    # -------------------------------------------------
    # Environment
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"
    sim_config.seed = 42   # reproducible

    # ✅ IMPORTANT: enable event bus for replay & winner output
    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=True),
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=rl_side,
    )

    # -------------------------------------------------
    # Observer (pretty console output)
    # -------------------------------------------------
    # ✅ Pass rl_side so observer can say HRL vs Heuristic
    observer = ConsoleObserver(rl_side=rl_side)
    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)

    # -------------------------------------------------
    # Reset environment
    # -------------------------------------------------
    obs = env.reset()

    done = False
    step = 0

    # -------------------------------------------------
    # Run one full match (HRL loop)
    # -------------------------------------------------
    while not done:
        state = sim_env.game_state
        active = state.active_unit

        if active is not None and active.side == rl_side:
            action = hrl_controller.choose_action(state, obs)
        else:
            action = heuristic_controller.choose_action(state)

        obs, _, done, _ = env.step(action)
        step += 1

    # -------------------------------------------------
    # Final score (machine-level summary)
    # -------------------------------------------------
    final_state = sim_env.game_state
    vp = (
        final_state.vp_tracker.total_points
        if final_state.vp_tracker else 0
    )

    print("\n=== MATCH FINISHED ===")
    print(f"Total steps: {step}")
    print(f"Final VP:    {vp}")


if __name__ == "__main__":
    main()