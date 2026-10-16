import json

from assault_bench.runner import _json_dumps


class _FakeHexCoord:
    def __init__(self, q: int, r: int) -> None:
        self.q = q
        self.r = r


def test_json_dumps_handles_hexcoord_like_objects_in_replay_payload():
    payload = {
        "schema_version": "bench_replay_episode_v2",
        "episode_index": 0,
        "seed": 7,
        "transitions": [
            {
                "target_qr": _FakeHexCoord(3, -2),
                "meta": {"raw": _FakeHexCoord(1, 0)},
            }
        ],
    }

    dumped = _json_dumps(payload, indent=2)
    parsed = json.loads(dumped)
    target = parsed["transitions"][0]["target_qr"]
    nested = parsed["transitions"][0]["meta"]["raw"]
    assert target == {"q": 3, "r": -2}
    assert nested == {"q": 1, "r": 0}
