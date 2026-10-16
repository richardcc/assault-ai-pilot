from assault_bench.phase29_metrics import build_phase29_eval_kpis_from_seed_rows


def test_build_phase29_eval_kpis_includes_opportunity_conversion_fields() -> None:
    rows = [
        {
            "opportunity_conversion_early_opportunity_steps": 2,
            "opportunity_conversion_early_converted_steps": 1,
            "opportunity_conversion_mid_opportunity_steps": 3,
            "opportunity_conversion_mid_converted_steps": 2,
            "opportunity_conversion_late_opportunity_steps": 0,
            "opportunity_conversion_late_converted_steps": 0,
        },
        {
            "opportunity_conversion_early_opportunity_steps": 1,
            "opportunity_conversion_early_converted_steps": 1,
            "opportunity_conversion_mid_opportunity_steps": 1,
            "opportunity_conversion_mid_converted_steps": 0,
            "opportunity_conversion_late_opportunity_steps": 2,
            "opportunity_conversion_late_converted_steps": 1,
        },
    ]

    out = build_phase29_eval_kpis_from_seed_rows(rows)
    assert out["opportunity_conversion_early_opportunity_steps"] == 3
    assert out["opportunity_conversion_early_converted_steps"] == 2
    assert out["opportunity_conversion_early_rate"] == (2.0 / 3.0)

    assert out["opportunity_conversion_mid_opportunity_steps"] == 4
    assert out["opportunity_conversion_mid_converted_steps"] == 2
    assert out["opportunity_conversion_mid_rate"] == 0.5

    assert out["opportunity_conversion_late_opportunity_steps"] == 2
    assert out["opportunity_conversion_late_converted_steps"] == 1
    assert out["opportunity_conversion_late_rate"] == 0.5
