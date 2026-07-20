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


def test_interop_module_no_legacy_alias_export() -> None:
    text = (_repo_root() / "agents" / "efficientzero_v2" / "core" / "interop.py").read_text(
        encoding="utf-8"
    )
    assert "MuZeroVOECAdapter" not in text


def test_core_interop_symbol_table_has_no_legacy_alias() -> None:
    from agents.efficientzero_v2.core import interop as interop_module

    assert not hasattr(interop_module, "MuZeroVOECAdapter")
    assert "MuZeroVOECAdapter" not in getattr(interop_module, "__all__", [])


def test_package_root_has_no_legacy_alias() -> None:
    import agents.efficientzero_v2 as package_root

    assert not hasattr(package_root, "MuZeroVOECAdapter")


def test_legacy_compat_module_removed() -> None:
    import importlib

    try:
        importlib.import_module("agents.efficientzero_v2.legacy_compat")
    except ModuleNotFoundError:
        return
    assert False, "legacy_compat module should not exist"


def test_selfplay_module_no_legacy_backend_toggle() -> None:
    text = (_repo_root() / "agents" / "efficientzero_v2" / "core" / "selfplay.py").read_text(
        encoding="utf-8"
    )
    assert "ASSAULT_EZV2_SELFPLAY_BACKEND" not in text
    assert "legacy_muzero" not in text
    assert "agents.muzero" not in text


def test_load_efficientzero_config_returns_local_contract() -> None:
    cfg = load_efficientzero_config(
        _repo_root() / "agents" / "efficientzero_v2" / "configs" / "efficientzero_v2_config.min_valid.yaml"
    )
    assert isinstance(cfg.paths, dict)
    assert isinstance(cfg.model, dict)
    assert isinstance(cfg.selfplay, dict)
    assert isinstance(cfg.train, dict)


def test_load_efficientzero_vp_strict_config_returns_local_contract() -> None:
    cfg = load_efficientzero_config(
        _repo_root() / "agents" / "efficientzero_v2" / "configs" / "efficientzero_v2_config.vp_strict.yaml"
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
