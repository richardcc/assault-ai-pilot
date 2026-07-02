# MuZero on VOEC - Architecture

Validation state: **Pending Validation**.

## Modules

- `adapter_voec.py`: boundary between MuZero and simulator.
- `core/network.py`: representation/dynamics/prediction heads.
- `core/mcts.py`: search contract (MVP stub now, PUCT next).
- `core/replay.py`: replay storage/sampling.
- `core/selfplay.py`: self-play episode generation.
- `train/trainer.py`: optimization step.
- `train/train_muzero.py`: run orchestration and artifacts.
- `obs/*`: events + JSONL + run manifest.
- `xai/*`: decision/search/episode reports.
