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
    assert res["scenario_id"] in ("mettete_i_piedi_terra_1", "mettete_i_piedi_terra_1_min")
    assert res["tracked_side"] == "US"
    assert res["opponent_side"] in ("IT", "GE")
    assert res["vp"]["total_objectives"] == 3
    assert len(res["victory_outcomes"]["table"]) == 4


def test_replay_steps_payload_scenario_overlay_detection():
    from mlops.reporting.replay_api import detect_scenario_id_from_transitions
    repo_root = Path(__file__).resolve().parents[2]

    # German units -> mettete_i_piedi_terra_1
    transitions_ge = [{"units": [{"unit_id": "GE_1"}, {"unit_id": "US_1"}], "vp_map": {"3,4": "GE"}}]
    sid_ge = detect_scenario_id_from_transitions(transitions_ge, repo_root)
    assert sid_ge == "mettete_i_piedi_terra_1"

    # Italian units -> battaglia_cittadina_2_1
    transitions_it = [{"units": [{"unit_id": "IT_1"}, {"unit_id": "US_1"}], "vp_map": {"16,1": "IT"}}]
    sid_it = detect_scenario_id_from_transitions(transitions_it, repo_root)
    assert sid_it == "battaglia_cittadina_2_1"


def test_enrich_episodes_meta_includes_controller_by_side(tmp_path):
    from mlops.reporting.replay_api import _enrich_episodes_meta
    dummy_replay_path = tmp_path / "bench_replay_index_test.json"
    dummy_replay_path.write_text("{}", encoding="utf-8")

    raw_meta = [
        {"episode_index": 0, "agent_name": "ezv2_vs_random_US", "scenario_id": "battaglia_cittadina_2_1"},
        {"episode_index": 1, "agent_name": "ezv2_vs_random_IT", "scenario_id": "battaglia_cittadina_2_1"},
        {"episode_index": 2, "agent_name": "ezv2_selfplay", "scenario_id": "battaglia_cittadina_2_1"},
    ]

    enriched = _enrich_episodes_meta(dummy_replay_path, raw_meta)
    assert len(enriched) == 3

    assert enriched[0]["matchup"] == "vs_random_atk"
    assert enriched[0]["controller_by_side"]["US"] == "EfficientZeroV2"
    assert enriched[0]["controller_by_side"]["IT"] == "Random"
    assert "GE" not in enriched[0]["controller_by_side"]
    assert enriched[0]["matchup_label"] == "EZv2 (US Atk) vs Rand (IT Def)"

    assert enriched[1]["matchup"] == "vs_random_def"
    assert enriched[1]["controller_by_side"]["IT"] == "EfficientZeroV2"
    assert enriched[1]["controller_by_side"]["US"] == "Random"
    assert "GE" not in enriched[1]["controller_by_side"]
    assert enriched[1]["matchup_label"] == "EZv2 (IT Def) vs Rand (US Atk)"

    assert enriched[2]["matchup"] == "selfplay"
    assert enriched[2]["controller_by_side"]["US"] == "EfficientZeroV2"
    assert enriched[2]["controller_by_side"]["IT"] == "EfficientZeroV2"
    assert "GE" not in enriched[2]["controller_by_side"]
    assert enriched[2]["matchup_label"] == "EZv2 Self-Play (IT Def vs US Atk)"


def test_load_scenario_overlay_reinforcements():
    from mlops.reporting.viewer_data_access import load_scenario_overlay
    repo_root = Path(__file__).resolve().parents[2]
    overlay = load_scenario_overlay(repo_root, "mettete_i_piedi_terra_1")
    assert "reinforcements" in overlay
    assert len(overlay["reinforcements"]) >= 1
    wave = overlay["reinforcements"][0]
    assert wave["turn"] == 2
    assert wave["side"] == "US"
    assert wave["units_count"] == 7
    assert len(wave["units"]) == 7


