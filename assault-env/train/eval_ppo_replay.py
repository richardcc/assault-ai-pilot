from stable_baselines3 import PPO

from assault_env.env import AssaultEnv
from assault.replay.snapshot import snapshot
from assault.replay.replay import Replay
from assault.replay.serialization import save_replay_to_json


MODEL_PATH = "models/ppo_level7_current"
REPLAY_PATH = "replays/ppo_eval_run_001.json"

# ------------------------------------------------------------
# Create environment in EVALUATION mode (no exploration)
# ------------------------------------------------------------
env = AssaultEnv(training=False)

# ------------------------------------------------------------
# Load trained PPO model
# ------------------------------------------------------------
model = PPO.load(MODEL_PATH)

# ------------------------------------------------------------
# Run ONE evaluation episode and record replay
# ------------------------------------------------------------
obs, _ = env.reset()
done = False
replay_states = []

while not done:
    # ✅ PPO decides action (deterministic)
    action, _ = model.predict(obs, deterministic=True)

    obs, reward, terminated, truncated, info = env.step(int(action))

    # ✅ Snapshot engine state (same as run_episode.py)
    replay_states.append(snapshot(env.state))

    done = terminated or truncated

# ------------------------------------------------------------
# Save replay to JSON
# ------------------------------------------------------------
replay = Replay(states=replay_states)
save_replay_to_json(replay, REPLAY_PATH)

print("✅ PPO evaluation finished")
print("Replay saved to:", REPLAY_PATH)
if "metrics" in info:
    print("Episode metrics:", info["metrics"])