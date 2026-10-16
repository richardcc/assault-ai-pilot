from __future__ import annotations

import json
from pathlib import Path

from mlops.reporting.replay_v2 import read_ndjson_rows, eval_root_from_source


def test_v2_eval_root_from_source_resolves_latest_eval(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "muzero_demo"
    run_root.mkdir(parents=True, exist_ok=True)
    eval_src = run_root / "xai" / "bench_eval_1.json"
    eval_src.parent.mkdir(parents=True, exist_ok=True)
    eval_src.write_text("{}", encoding="utf-8")
    evals_root = tmp_path / "runs" / "evals"
    (evals_root / "muzero_demo__20260101_000001").mkdir(parents=True, exist_ok=True)
    (evals_root / "muzero_demo__20260102_000001").mkdir(parents=True, exist_ok=True)
    got = eval_root_from_source(str(eval_src))
    assert got is not None
    assert got.name.startswith("muzero_demo__")


def test_read_ndjson_rows_plain_text_fallback(tmp_path: Path) -> None:
    p = tmp_path / "episode_0.ndjson.zst"
    rows = [{"step": 0}, {"step": 1}, {"step": 2}]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = read_ndjson_rows(p, 1, 2)
    assert [r["step"] for r in out] == [1, 2]
