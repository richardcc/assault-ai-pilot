from agents.muzero.train.train_muzero import _resolve_device


def test_resolve_device_cpu():
    assert _resolve_device("cpu") == "cpu"


def test_resolve_device_auto_returns_valid():
    assert _resolve_device("auto") in {"cpu", "cuda"}
