from pathlib import Path


def test_gate_script_exists() -> None:
    path = Path("scripts/gate_reporting_v2_go_nogo.ps1")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "GO: reporting v2 strict gate PASSED" in text
    assert "NO-GO: reporting v2 strict gate FAILED" in text
