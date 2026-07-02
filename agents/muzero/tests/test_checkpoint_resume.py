import tempfile
from pathlib import Path

import pytest
import yaml

torch = pytest.importorskip("torch")

from agents.muzero.core.network import MuZeroNetwork
from agents.muzero.train.train_muzero import run_training


def _write_cfg(path: Path, cfg: dict) -> None:
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def test_train_resume_from_checkpoint_smoke():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ckpt = tmp / "resume.pt"
        run_root = tmp / "runs"

        model = MuZeroNetwork(observation_dim=4, hidden_dim=32, action_dim=32)
        torch.save(model.state_dict(), ckpt)

        cfg = {
            "paths": {
                "run_root": str(run_root),
                "voec_config": "voec_sim/configs/voec_config.yaml",
            },
            "scenario": {"id": "battaglia_cittadina_2_1", "seed": 11},
            "model": {
                "observation_dim": 4,
                "hidden_dim": 32,
                "action_dim": 32,
                "learning_rate": 0.001,
            },
            "selfplay": {"max_steps": 10, "mcts_simulations": 8, "mcts_c_puct": 1.5},
            "train": {
                "iterations": 1,
                "episodes_per_iter": 1,
                "batch_size": 2,
                "replay_capacity": 200,
                "resume_checkpoint": str(ckpt),
            },
        }
        cfg_path = tmp / "resume_cfg.yaml"
        _write_cfg(cfg_path, cfg)

        result = run_training(config_path=str(cfg_path))
        assert "run_id" in result
        assert (run_root / result["run_id"] / "run_manifest.json").exists()
