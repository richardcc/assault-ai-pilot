# assault_sim/train/run_match_rl_vs_heuristic.py

import torch
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.controller import RLPolicyController
from assault_sim.rl.side_controller import SideAwareController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.state_encoder import encode_state

from assault_sim.debug.console_observer import ConsoleObserver


def main():
    # =================================================
    # ✅ DEFINE RL SIDE HERE (MUST MATCH TRAINING)
    # =================================================
    rl_side = "US"   # "GE" or "US"
    enemy_side = "GE" if rl_side == "US" else "US"

    print(f">>> Replaying: RL ({rl_side}) vs Heuristic ({enemy_side})")

    # -------------------------------------------------
    # Load trained PPO checkpoint
    # -------------------------------------------------
    checkpoint_path = (
        Path(__file__).resolve()
        .parent.parent
        / "checkpoints"
        / f"ppo_{rl_side}_phase01.pt"
    )

    checkpoint = torch.load(checkpoint_path, map_location="cpu")

    policy = PolicyNet(
        input_dim=checkpoint["input_dim"],     # ✅ must be 9
        max_actions=checkpoint["max_actions"],
    )
    policy.load_state_dict(checkpoint["model_state_dict"])
    policy.eval()

    print(">>> PPO model loaded")

    # -------------------------------------------------
    # Controllers
    # -------------------------------------------------
    max_turns = None  # will be known after reset

    rl_controller = RLPolicyController(
        policy_net=policy,
        rl_side=rl_side,
        max_turns=None,   # filled later
    )
    heuristic_controller = TacticalPathHeuristic()

    controller = SideAwareController(
        rl_controller=rl_controller,
        heuristic_controller=heuristic_controller,
        rl_side=rl_side,
    )

    # -------------------------------------------------
    # Environment
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"
    sim_config.seed = 42   # ✅ reproducible

    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=sim_config.debug,
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
    )

    # -------------------------------------------------
    # Observer (prints turns & actions)
    # -------------------------------------------------
    observer = ConsoleObserver()
    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)

    # -------------------------------------------------
    # Reset environment
    # -------------------------------------------------
    obs = env.reset()                      # ✅ RL observation vector (9)
    max_turns = sim_env.scenario.max_turns
    rl_controller.max_turns = max_turns   # ✅ update controller now

    done = False
    step = 0

    # -------------------------------------------------
    # Run one full match
    # -------------------------------------------------
    while not done:
        game_state = sim_env.game_state

        action = controller.choose_action(
            game_state,
            obs
        )

        obs, _, done, _ = env.step(action)
        step += 1

    # Final score from REAL game state
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