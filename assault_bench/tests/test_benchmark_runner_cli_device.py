from assault_bench.runner import _build_arg_parser, _resolve_bench_device_choice


def test_arg_parser_accepts_device_override():
    args = _build_arg_parser().parse_args(["--device", "cpu"])
    assert args.device == "cpu"


def test_arg_parser_device_default_uses_config():
    args = _build_arg_parser().parse_args([])
    assert args.device == ""


def test_device_override_takes_precedence(monkeypatch):
    calls = []

    def fake_resolve(raw):
        calls.append(str(raw))
        return str(raw)

    monkeypatch.setattr("assault_bench.runner._resolve_bench_device", fake_resolve)
    out = _resolve_bench_device_choice("cuda", "cpu")
    assert out == "cpu"
    assert calls == ["cpu"]


def test_device_override_falls_back_to_config(monkeypatch):
    calls = []

    def fake_resolve(raw):
        calls.append(str(raw))
        return str(raw)

    monkeypatch.setattr("assault_bench.runner._resolve_bench_device", fake_resolve)
    out = _resolve_bench_device_choice("cuda", "")
    assert out == "cuda"
    assert calls == ["cuda"]
