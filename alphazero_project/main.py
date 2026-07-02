from pathlib import Path
import yaml

from alphazero_project.integration.assault_model_adapter import AssaultModelAdapter
from alphazero_project.integration.assault_simulation import AssaultSimulation
from alphazero_project.core.selfplay.self_play import SelfPlay
from alphazero_project.core.model.model import get_model
from alphazero_project.core.training.trainer import Trainer


# -----------------------------
# CONFIG
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "alphazero_config.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


# -----------------------------
# INIT
# -----------------------------
sim = AssaultSimulation(config)
game = AssaultModelAdapter(sim)

sp = SelfPlay(game, config)

model = get_model()
trainer = Trainer(model)


# -----------------------------
# LOOP
# -----------------------------
dataset = []

NUM_ITERATIONS = 10
EPISODES_PER_ITER = 2

for iteration in range(NUM_ITERATIONS):
    print(f"\n======== ITER {iteration} ========")

    # -------------------------
    # SELF-PLAY
    # -------------------------
    for ep in range(EPISODES_PER_ITER):
        print(f"[SELF-PLAY] episode {ep}")

        episode = sp.play_episode()

        print(f"steps: {len(episode)}")

        dataset.extend(episode)

    print(f"dataset size: {len(dataset)}")

    # -------------------------
    # TRAIN
    # -------------------------
    print("[TRAINING]")

    metrics = trainer.train_batch(dataset)

    print(metrics)

    # -------------------------
    # RESET DATASET (opcional)
    # -------------------------
    dataset = []