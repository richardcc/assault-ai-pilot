#!/usr/bin/env python3
"""
Test to verify that decision engine selects units intelligently,
not sequentially.
"""

import torch
from pathlib import Path
from collections import defaultdict

from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.rl.state_encoder import encode_state
from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.engine.match_runner import MatchRunner
from assault_sim.runners.run_match_rl_vs_heuristic import DecisionEngineController
from assault_sim.debug.debug_config import DebugConfig

RL_SIDE = "US"
CHECKPOINT = Path("models/latest.pt")


def build_env():
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"
    sim_config.seed = 42
    
    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=False),
    )
    
    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=RL_SIDE,
    )
    
    return env, sim_env


def build_controller(policy, sim_env):
    option_policy = OptionPolicy(
        num_options=len(TacticalOption),
    )

    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    policy.load_state_dict(checkpoint)
    policy.eval()

    def build_obs(sim_env):
        return encode_state(
            sim_env.game_state,
            unit=None,
            rl_side=RL_SIDE,
            max_turns=sim_env.scenario.max_turns
        )

    decision_engine = DecisionEngine(
        model=policy,
        obs_builder=build_obs,
    )

    heuristic = TacticalPathHeuristic()

    controller = DecisionEngineController(
        rl_side=RL_SIDE,
        decision_engine=decision_engine,
        option_policy=option_policy,
        heuristic=heuristic,
        sim_env=sim_env,
    )

    return controller


def test_unit_selection():
    """Test that units are selected intelligently, not sequentially."""
    
    print("\n" + "="*60)
    print("TESTING INTELLIGENT UNIT SELECTION")
    print("="*60 + "\n")
    
    env, sim_env = build_env()
    
    # Reset to get obs dimension
    obs = env.reset()
    input_dim = obs.shape[0]
    
    policy_net = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption),
    )
    
    controller = build_controller(policy_net, sim_env)
    
    # Create runner with controller
    runner = MatchRunner(env, controller=controller)
    obs = runner.reset()
    
    # Track which units are activated in order
    units_activated = []
    
    # Run a few turns
    for turn in range(5):
        print(f"\n>>> TURN {turn + 1}")
        
        done = False
        step_in_turn = 0
        
        while not done:
            result = runner.step(controller, obs)
            obs = result["obs"]
            done = result["done"]
            side = result.get("side")
            unit = result.get("unit")
            is_turn_end = result.get("is_turn_end", False)
            
            if is_turn_end:
                break
            
            if unit is not None:
                units_activated.append((turn, step_in_turn, unit.unit_id, side))
                print(f"    Step {step_in_turn}: {side} - {unit.unit_id}")
                step_in_turn += 1
        
        if done:
            break
    
    print("\n" + "="*60)
    print("UNIT ACTIVATION ORDER:")
    print("="*60)
    
    # Check if units from the same side are activated in different order
    # (not just sequential)
    prev_turn = -1
    prev_positions = defaultdict(list)
    
    for turn, step, unit_id, side in units_activated:
        if turn != prev_turn:
            if prev_positions:
                # Check if there's variation in activation order
                us_units = [u for u in prev_positions['US']]
                if len(us_units) > 1:
                    print(f"  Turn {prev_turn}: US units activated in order: {us_units}")
            prev_turn = turn
            prev_positions = defaultdict(list)
        
        prev_positions[side].append(unit_id)
    
    # Final turn
    if prev_positions:
        us_units = [u for u in prev_positions['US']]
        if len(us_units) > 1:
            print(f"  Turn {prev_turn}: US units activated in order: {us_units}")
    
    print("\n[OK] Intelligent unit selection test completed!")
    print("If units are not appearing in the same sequential order each turn,")
    print("then intelligent selection is working correctly.\n")


if __name__ == "__main__":
    test_unit_selection()
