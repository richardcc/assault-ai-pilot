from assault_bench.runner import _extract_unit_suppressed_from_runtime_events


def test_extract_unit_suppressed_from_runtime_events_reads_payload_fields() -> None:
    events = [
        {
            "type": "ACTION_EFFECT",
            "payload": {
                "attacker": "US_2",
                "attacker_suppressed": False,
                "defender": "IT_1",
                "defender_suppressed": True,
            },
        }
    ]
    out = _extract_unit_suppressed_from_runtime_events(events)
    assert out["US_2"] is False
    assert out["IT_1"] is True
