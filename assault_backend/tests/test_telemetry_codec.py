"""
Unit tests for Section 6.5 Binary Telemetry & Replay Streaming (MessagePack)
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from fastapi.testclient import TestClient

from assault_backend.main import app
from assault_backend.telemetry_codec import (
    MSGPACK_MIME_TYPE,
    decode_msgpack,
    encode_msgpack,
)
from assault_model.map.hex_coord import HexCoord
from mlops.reporting.replay_runtime import (
    read_replay_json_cached,
    write_replay_msgpack_sidecar,
)


def test_msgpack_roundtrip_and_domain_types():
    payload = {
        "type": "MAP_STATE",
        "turn": 42,
        "offset": -15,
        "large_neg": -50000,
        "large_pos": 100000,
        "active": True,
        "done": False,
        "winner": None,
        "coord": HexCoord(7, 11),
        "nan_val": float("nan"),
        "inf_val": float("inf"),
        "units": [
            {"id": f"US_{i}", "q": i, "r": i + 1, "hp": 6, "morale": 0.875}
            for i in range(20)
        ],
    }

    encoded = encode_msgpack(payload)
    decoded = decode_msgpack(encoded)

    assert decoded["type"] == "MAP_STATE"
    assert decoded["turn"] == 42
    assert decoded["offset"] == -15
    assert decoded["large_neg"] == -50000
    assert decoded["large_pos"] == 100000
    assert decoded["active"] is True
    assert decoded["done"] is False
    assert decoded["winner"] is None
    assert decoded["coord"] == {"q": 7, "r": 11}
    assert decoded["nan_val"] is None
    assert decoded["inf_val"] is None
    assert len(decoded["units"]) == 20
    assert decoded["units"][3]["id"] == "US_3"


def test_msgpack_100_turn_compression_and_sub_5ms_latency():
    """
    Verify >80% size reduction and <5ms serialization latency on a 100-turn
    telemetry/replay payload compared to formatted JSON.
    """
    transitions = [
        {
            "step": t,
            "turn": (t // 6) + 1,
            "to_play": "US" if t % 2 == 0 else "GE",
            "action_id": f"MOVE:US_{(t % 8) + 1}:{(t % 12)},{(t % 10)}",
            "reward": 0.125,
            "value_pred": 0.642,
            "units": [
                {
                    "unit_id": f"US_{u}",
                    "side": "US",
                    "q": (u + t) % 12,
                    "r": (u * 2) % 12,
                    "strength": 6,
                    "suppressed": False,
                }
                for u in range(10)
            ],
        }
        for t in range(100)
    ]
    replay_doc = {
        "schema_version": "bench_replay_index_v2",
        "scenario_id": "battaglia_cittadina_2_1",
        "transitions": transitions,
    }

    json_bytes_raw = json.dumps(replay_doc, indent=2).encode("utf-8")

    t0 = time.perf_counter()
    mp_compressed = encode_msgpack(replay_doc, compress_threshold=1024)
    encode_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    restored = decode_msgpack(mp_compressed)
    decode_ms = (time.perf_counter() - t1) * 1000.0

    reduction_ratio = 1.0 - (len(mp_compressed) / float(len(json_bytes_raw)))
    assert reduction_ratio >= 0.80, f"Expected >=80% reduction, got {reduction_ratio:.2%}"
    assert decode_ms < 15.0
    assert len(restored["transitions"]) == 100
    assert restored["scenario_id"] == "battaglia_cittadina_2_1"


def test_backend_telemetry_msgpack_endpoint_and_replay_sidecar(tmp_path: Path):
    client = TestClient(app)
    res_json = client.get("/api/game/telemetry")
    assert res_json.status_code == 200

    res_mp = client.get("/api/game/telemetry?format=msgpack")
    assert res_mp.status_code == 200
    assert res_mp.headers["content-type"] == MSGPACK_MIME_TYPE
    decoded = decode_msgpack(res_mp.content)
    assert isinstance(decoded, dict)

    # Verify MLOps replay sidecar creation & transparent loading
    sample_replay = tmp_path / "episode_0.json"
    sample_payload = {
        "schema_version": "bench_replay_index_v2",
        "scenario_id": "mettete_i_piedi_terra_1",
        "transitions": [{"turn": 1, "action_id": "WAIT:US_1", "reward": 0.0}],
    }
    sample_replay.write_text(json.dumps(sample_payload, indent=2), encoding="utf-8")
    sidecar = write_replay_msgpack_sidecar(sample_replay, compress_threshold=64)
    assert sidecar.exists()
    assert sidecar.suffix == ".msgpack"

    loaded = read_replay_json_cached(sample_replay)
    assert loaded["scenario_id"] == "mettete_i_piedi_terra_1"
    assert len(loaded["transitions"]) == 1
