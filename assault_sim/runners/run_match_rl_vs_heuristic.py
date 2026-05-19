# C:\repos\python\assault\assault_sim\runners\run_match_rl_vs_heuristic.py

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

from assault_sim.engine.match_runner import MatchRunner
from assault_sim.decision.controller_adapter import RLvsHeuristicController

from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.debug.debug_config import DebugConfig

from assault_sim.debug.replay_observer import ReplayObserver
from assault_sim.debug.replay_writer import ReplayWriter
from assault_sim.debug.replay_utils import extract_initial_state


RL_SIDE = "US"
CHECKPOINT = Path("models/latest.pt")


def main():

    rl_side = RL_SIDE
    enemy_side = "GE" if rl_side == "US" else "US"

    print(f">>> Replaying HRL: RL ({rl_side}) vs Heuristic ({enemy_side})")

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("C:/repos/python/assault/assault_sim/config/sim_config.yaml")
    )

    sim_config.scenario_name = "phase01_seq001_initial_contact"
    sim_config.seed = 42

    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=True),
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("C:/repos/python/assault/assault_sim/config/env_config.json"),
        rl_side=rl_side,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    # -------------------------------------------------
    # MODEL
    # -------------------------------------------------
    print(f">>> Loading checkpoint: {CHECKPOINT}")

    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption),
    )

    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    policy.load_state_dict(checkpoint)
    policy.eval()

    print(">>> PPO model loaded ✅")

    # -------------------------------------------------
    # HRL COMPONENTS
    # -------------------------------------------------
    option_policy = OptionPolicy(policy)

    heuristic = TacticalPathHeuristic()
    executor = OptionExecutor(heuristic)

    hrl_controller = HRLController(
        option_policy=option_policy,
        option_executor=executor,
        rl_side=rl_side,
        event_bus=sim_env.event_bus,
    )

    controller = RLvsHeuristicController(
        rl_side=rl_side,
        hrl_controller=hrl_controller,
        heuristic=heuristic,
        executor=executor,
    )

    # -------------------------------------------------
    # OBSERVERS
    # -------------------------------------------------
    observer = ConsoleObserver(rl_side=rl_side)
    replay_observer = ReplayObserver()

    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)
        sim_env.event_bus.subscribe(replay_observer)

    # -------------------------------------------------
    # INIT REPLAY
    # -------------------------------------------------
    replay_observer.replay.initial_state = extract_initial_state(
        sim_env.game_state
    )

    replay_observer.replay.meta = {
        "scenario_id": sim_config.scenario_name,
        "sides": {
            rl_side: "RL",
            enemy_side: "HEURISTIC",
        },
    }

    # -------------------------------------------------
    # MATCH RUNNER
    # -------------------------------------------------
    runner = MatchRunner(env)

    done = False
    step = 0

    # -------------------------------------------------
    # LOOP (UNIFICADO)
    # -------------------------------------------------
    while not done:

        result = runner.step(controller, obs)

        obs = result["obs"]
        done = result["done"]

        step += 1

    # -------------------------------------------------
    # FINAL RESULT
    # -------------------------------------------------
    final_state = sim_env.game_state

    vp = (
        final_state.vp_tracker.total_points
        if final_state.vp_tracker else 0
    )

    print("\n=== MATCH FINISHED ===")
    print(f"Total steps: {step}")
    print(f"Winner:      {final_state.winner}")
    print(f"Reason:      {final_state.end_reason}")
    print(f"Final VP:    {vp}")

    replay_observer.replay.meta["result"] = {
        "winner": final_state.winner,
        "reason": final_state.end_reason,
        "vp": vp,
        "steps": step,
    }

    # -------------------------------------------------
    # SAVE REPLAY
    # -------------------------------------------------
    replay_dir = Path("C:/repos/python/assault/assault_sim/session/replays")
    replay_dir.mkdir(parents=True, exist_ok=True)

    replay_path = replay_dir / (
        f"{sim_config.scenario_name}__"
        f"{rl_side}_RL_vs_{enemy_side}_HEURISTIC.json"
    )

    ReplayWriter.write(replay_observer.replay, replay_path)

    print(f"✅ Replay saved to: {replay_path}")


if __name__ == "__main__":
    main()
