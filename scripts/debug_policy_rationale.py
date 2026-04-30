"""
DEBUG SCRIPT: Verify if PPO policy emits rationale logits.

This script answers ONE question:
Does policy.forward(obs) return (action_dist, rationale_logits)
or only action_dist?

It does NOT train, does NOT save replays.
"""

import torch
from stable_baselines3 import PPO

from assault_env.env import AssaultEnv
from assault_env.scenario_base import simple_duel_level7_P4_2v2_from_json


MODEL_PATH = "models/ppo_p4_2v2_explainable_final_20260425_131822.zip"


def main():
    print("🔎 Loading model...")
    model = PPO.load(MODEL_PATH)
    policy = model.policy

    print("\n📦 Policy class:")
    print(type(policy))
    print(policy)

    print("\n🎮 Creating environment...")
    env = AssaultEnv(
        scenario_builder=simple_duel_level7_P4_2v2_from_json,
        training=False,
        max_turns=200,
    )

    obs, _ = env.reset()

    print("\n🧪 Running policy.forward(obs)...")
    with torch.no_grad():
        obs_tensor, _ = policy.obs_to_tensor(obs)
        out = policy.forward(obs_tensor)

    print("\n✅ policy.forward() returned:")
    print("Type:", type(out))
    print("Value:", out)

    print("\n🧠 Interpretation:")
    if isinstance(out, tuple):
        print("✅ forward() returns a tuple")
        print("Tuple length:", len(out))
        if len(out) == 2:
            action_dist, rationale_logits = out
            print("✅ Second element (rationale logits):", rationale_logits)
            if rationale_logits is not None:
                print(
                    "✅ Argmax rationale:",
                    rationale_logits.argmax(dim=-1).item()
                )
            else:
                print("❌ rationale_logits is None")
        else:
            print("❌ Tuple does NOT have 2 elements")
    else:
        print("❌ forward() returns ONLY action distribution")
        print("❌ No rationale head active")


if __name__ == "__main__":
    main()