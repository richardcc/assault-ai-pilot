from pathlib import Path

from mlops.reporting.viewer import _load_catalog_payload


def test_load_catalog_payload_reports_missing_catalog_in_strict_mode(tmp_path: Path) -> None:
    payload = _load_catalog_payload(tmp_path, "runs_curriculum/experiments/reporting/model_catalog_latest.json")
    assert payload.get("schema_version") == "reporting_v2_strict"
    assert list(payload.get("engines", []) or []) == []
    assert "catalog not found" in str(payload.get("error", "") or "")


def test_load_catalog_payload_reports_invalid_json_in_strict_mode(tmp_path: Path) -> None:
    bad_catalog = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "model_catalog_latest.json"
    bad_catalog.parent.mkdir(parents=True, exist_ok=True)
    bad_catalog.write_text("{invalid", encoding="utf-8")

    payload = _load_catalog_payload(tmp_path, "runs_curriculum/experiments/reporting/model_catalog_latest.json")
    assert payload.get("schema_version") == "reporting_v2_strict"
    assert "failed to parse catalog" in str(payload.get("error", "") or "")
