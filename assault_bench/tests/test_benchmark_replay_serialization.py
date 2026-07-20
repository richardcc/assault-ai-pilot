import json

from assault_bench.runner import _json_dumps


class _FakeHexCoord:
    def __init__(self, q: int, r: int) -> None:
        self.q = q
        self.r = r


def test_json_dumps_handles_hexcoord_like_objects_in_replay_payload():
    payload = {
        "schema_version": "bench_replay_v1",
        "episodes": [
            {
                "seed": 7,
                "transitions": [
                    {
                        "target_qr": _FakeHexCoord(3, -2),
                        "meta": {"raw": _FakeHexCoord(1, 0)},
                    }
                ],
            }
        ],
    }

    dumped = _json_dumps(payload, indent=2)
    parsed = json.loads(dumped)
    target = (
        parsed["episodes"][0]["transitions"][0]["target_qr"]
    )
    nested = (
        parsed["episodes"][0]["transitions"][0]["meta"]["raw"]
    )
    assert target == {"q": 3, "r": -2}
    assert nested == {"q": 1, "r": 0}
