from __future__ import annotations

from pathlib import Path
from mlops.reporting.viewer_data_access import load_scenario_detail


def test_load_scenario_detail_battaglia_cittadina():
    repo_root = Path(__file__).resolve().parents[2]
    res = load_scenario_detail(repo_root, "battaglia_cittadina")
    assert res["ok"] is True
    assert res["scenario_id"] == "battaglia_cittadina"
    assert res["max_turns"] == 8
    assert res["tracked_side"] == "US"
    assert res["opponent_side"] in ("IT", "GE")
    assert res["vp"]["total_objectives"] == 5

    table = res["victory_outcomes"]["table"]
    assert len(table) == 5
    # Row 0: 5 objectives -> Vittoria Totale (+1) vs Sconfitta Totale (-1)
    assert table[0]["canonical_class"] == "total_victory"
    assert table[0]["canonical_score"] == 1
    assert table[0]["dual_class"] == "total_defeat"
    assert table[0]["dual_score"] == -1

    # Row 2: 3 objectives -> Pareggio (0) vs Pareggio (0)
    assert table[2]["canonical_class"] == "draw"
    assert table[2]["canonical_score"] == 0
    assert table[2]["dual_class"] == "draw"
    assert table[2]["dual_score"] == 0


def test_load_scenario_detail_mettete():
    repo_root = Path(__file__).resolve().parents[2]
    res = load_scenario_detail(repo_root, "mettete_i_piedi_terra_1")
    assert res["ok"] is True
    assert res["scenario_id"] == "mettete_i_piedi_terra_1_min"
    assert res["tracked_side"] == "US"
    assert res["opponent_side"] == "GE"
    assert res["vp"]["total_objectives"] == 3
    assert len(res["victory_outcomes"]["table"]) == 4
