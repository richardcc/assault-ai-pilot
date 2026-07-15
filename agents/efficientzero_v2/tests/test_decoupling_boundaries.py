from __future__ import annotations

from pathlib import Path

from agents.efficientzero_v2.core.interop import load_efficientzero_config
from agents.efficientzero_v2.core import selfplay as selfplay_module


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_core_network_module_no_direct_muzero_import() -> None:
    text = (_repo_root() / "agents" / "efficientzero_v2" / "core" / "network.py").read_text(
        encoding="utf-8"
    )
    assert "agents.muzero" not in text


def test_trainer_module_no_direct_muzero_import() -> None:
    text = (_repo_root() / "agents" / "efficientzero_v2" / "train" / "trainer.py").read_text(
        encoding="utf-8"
    )
    assert "agents.muzero" not in text


def test_train_engine_module_no_direct_muzero_import() -> None:
    text = (_repo_root() / "agents" / "efficientzero_v2" / "train" / "train_engine.py").read_text(
        encoding="utf-8"
    )
    assert "agents.muzero" not in text


def test_load_efficientzero_config_returns_local_contract() -> None:
    cfg = load_efficientzero_config(
        _repo_root() / "agents" / "efficientzero_v2" / "configs" / "efficientzero_v2_config.min_valid.yaml"
    )
    assert isinstance(cfg.paths, dict)
    assert isinstance(cfg.model, dict)
    assert isinstance(cfg.selfplay, dict)
    assert isinstance(cfg.train, dict)


def test_selfplay_backend_can_be_swapped_for_regression_boundary() -> None:
    class _DummyBackend:
        def play_episode(self, **kwargs):
            return [{"backend": "dummy", "kwargs_keys": sorted(kwargs.keys())}]

    original_backend = selfplay_module._BACKEND
    try:
        selfplay_module.set_selfplay_backend(_DummyBackend())
        out = selfplay_module.play_episode(seed=1, scenario_id="s1")
        assert out and out[0]["backend"] == "dummy"
    finally:
        selfplay_module.set_selfplay_backend(original_backend)


def test_selfplay_backend_defaults_to_native_ezv2() -> None:
    assert selfplay_module.current_backend_name() == "_NativeEZV2SelfplayBackend"
