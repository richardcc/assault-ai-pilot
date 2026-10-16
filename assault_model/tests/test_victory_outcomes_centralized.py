from __future__ import annotations

import pytest
from types import SimpleNamespace

from assault_model.core.victory_outcomes import (
    OutcomeClass,
    ScenarioOutcomeResult,
    evaluate_scenario_outcome,
)


def test_outcome_class_parsing_and_properties():
    # Canonical parsing from Italian scenario strings
    assert OutcomeClass.from_str("Vittoria Totale") == OutcomeClass.TOTAL_VICTORY
    assert OutcomeClass.from_str("Vittoria") == OutcomeClass.VICTORY
    assert OutcomeClass.from_str("Pareggio") == OutcomeClass.DRAW
    assert OutcomeClass.from_str("Sconfitta") == OutcomeClass.DEFEAT
    assert OutcomeClass.from_str("Sconfitta totale") == OutcomeClass.TOTAL_DEFEAT

    # Parsing from English / identifier strings
    assert OutcomeClass.from_str("total_victory") == OutcomeClass.TOTAL_VICTORY
    assert OutcomeClass.from_str("win") == OutcomeClass.VICTORY
    assert OutcomeClass.from_str("draw") == OutcomeClass.DRAW
    assert OutcomeClass.from_str("defeat") == OutcomeClass.DEFEAT
    assert OutcomeClass.from_str("total_defeat") == OutcomeClass.TOTAL_DEFEAT
    assert OutcomeClass.from_str("unknown_label") == OutcomeClass.UNKNOWN

    # Score properties
    assert OutcomeClass.TOTAL_VICTORY.score == 1
    assert OutcomeClass.VICTORY.score == 1
    assert OutcomeClass.DRAW.score == 0
    assert OutcomeClass.DEFEAT.score == -1
    assert OutcomeClass.TOTAL_DEFEAT.score == -1

    # Win / loss / draw flags
    assert OutcomeClass.TOTAL_VICTORY.is_win is True
    assert OutcomeClass.VICTORY.is_win is True
    assert OutcomeClass.DRAW.is_win is False
    assert OutcomeClass.DRAW.is_draw is True
    assert OutcomeClass.DEFEAT.is_loss is True
    assert OutcomeClass.TOTAL_DEFEAT.is_loss is True


def test_outcome_class_dual_symmetry():
    # Opponent duality in 2-player matches
    assert OutcomeClass.TOTAL_VICTORY.dual == OutcomeClass.TOTAL_DEFEAT
    assert OutcomeClass.VICTORY.dual == OutcomeClass.DEFEAT
    assert OutcomeClass.DRAW.dual == OutcomeClass.DRAW
    assert OutcomeClass.DEFEAT.dual == OutcomeClass.VICTORY
    assert OutcomeClass.TOTAL_DEFEAT.dual == OutcomeClass.TOTAL_VICTORY
    assert OutcomeClass.UNKNOWN.dual == OutcomeClass.UNKNOWN


@pytest.fixture
def battaglia_cittadina_scenario():
    return {
        "id": "battaglia_cittadina",
        "max_turns": 8,
        "vp": {
            "value_per_hex": 2,
            "hexes": [
                {"q": 16, "r": 1, "initial_owner": "IT"},
                {"q": 9, "r": 1, "initial_owner": "IT", "value": 3},
                {"q": 2, "r": 6, "initial_owner": "IT"},
                {"q": 8, "r": 9, "initial_owner": "US"},
                {"q": 16, "r": 8, "initial_owner": "US", "value": 3},
            ],
        },
        "victory_outcomes": {
            "tracked_side": "US",
            "metric": "objectives_captured",
            "timing": "end_of_last_turn",
            "table": [
                {
                    "captured": {"min": 5, "max": 5},
                    "result": "Vittoria Totale",
                    "outcome_class": "total_victory",
                    "next_scenario": "3.1",
                    "next_page": 26,
                    "outcome_score": 1,
                },
                {
                    "captured": {"min": 4, "max": 4},
                    "result": "Vittoria",
                    "outcome_class": "victory",
                    "next_scenario": "3.2",
                    "next_page": 28,
                    "outcome_score": 1,
                },
                {
                    "captured": {"min": 3, "max": 3},
                    "result": "Pareggio",
                    "outcome_class": "draw",
                    "next_scenario": "3.3",
                    "next_page": 30,
                    "outcome_score": 0,
                },
                {
                    "captured": {"min": 2, "max": 2},
                    "result": "Sconfitta",
                    "outcome_class": "defeat",
                    "next_scenario": "3.4",
                    "next_page": 32,
                    "outcome_score": -1,
                },
                {
                    "captured": {"min": 0, "max": 1},
                    "result": "Sconfitta totale",
                    "outcome_class": "total_defeat",
                    "next_scenario": "3.5",
                    "next_page": 34,
                    "outcome_score": -1,
                },
            ],
        },
    }


def test_battaglia_cittadina_all_tiers_and_bilateral_coherence(battaglia_cittadina_scenario):
    # Case 1: 5 captured by US -> Total Victory for US, Total Defeat for IT
    res5 = evaluate_scenario_outcome(
        scenario=battaglia_cittadina_scenario,
        final_vp_by_side={"US": 5, "IT": 0},
    )
    assert res5.winner == "US"
    assert res5.outcome_class == OutcomeClass.TOTAL_VICTORY
    assert res5.outcome_class_by_side == {"US": "total_victory", "IT": "total_defeat"}
    assert res5.outcome_score_by_side == {"US": 1, "IT": -1}
    assert res5.result_text_by_side["US"] == "Vittoria Totale"
    assert res5.result_text_by_side["IT"] == "Sconfitta totale"
    assert res5.next_scenario == "3.1"
    assert res5.next_page == 26

    # Case 2: 4 captured by US -> Victory for US, Defeat for IT
    res4 = evaluate_scenario_outcome(
        scenario=battaglia_cittadina_scenario,
        final_vp_by_side={"US": 4, "IT": 1},
    )
    assert res4.winner == "US"
    assert res4.outcome_class == OutcomeClass.VICTORY
    assert res4.outcome_class_by_side == {"US": "victory", "IT": "defeat"}
    assert res4.outcome_score_by_side == {"US": 1, "IT": -1}
    assert res4.next_scenario == "3.2"
    assert res4.next_page == 28

    # Case 3: 3 captured by US -> Draw for US, Draw for IT
    res3 = evaluate_scenario_outcome(
        scenario=battaglia_cittadina_scenario,
        final_vp_by_side={"US": 3, "IT": 2},
    )
    assert res3.winner is None
    assert res3.outcome_class == OutcomeClass.DRAW
    assert res3.outcome_class_by_side == {"US": "draw", "IT": "draw"}
    assert res3.outcome_score_by_side == {"US": 0, "IT": 0}
    assert res3.next_scenario == "3.3"
    assert res3.next_page == 30

    # Case 4: 2 captured by US, 3 by IT (Initial State, no VPs changed hands!)
    # US got Defeat. CRITICAL: IT must get VICTORY (NOT Draw)!
    res2 = evaluate_scenario_outcome(
        scenario=battaglia_cittadina_scenario,
        final_vp_by_side={"US": 2, "IT": 3},
    )
    assert res2.winner == "IT"
    assert res2.outcome_class == OutcomeClass.DEFEAT
    assert res2.outcome_class_by_side == {"US": "defeat", "IT": "victory"}
    assert res2.outcome_score_by_side == {"US": -1, "IT": 1}
    assert res2.result_text_by_side["IT"] == "Vittoria"
    assert res2.next_scenario == "3.4"
    assert res2.next_page == 32

    # Case 5: 1 captured by US -> Total Defeat for US, Total Victory for IT
    res1 = evaluate_scenario_outcome(
        scenario=battaglia_cittadina_scenario,
        final_vp_by_side={"US": 1, "IT": 4},
    )
    assert res1.winner == "IT"
    assert res1.outcome_class == OutcomeClass.TOTAL_DEFEAT
    assert res1.outcome_class_by_side == {"US": "total_defeat", "IT": "total_victory"}
    assert res1.outcome_score_by_side == {"US": -1, "IT": 1}
    assert res1.next_scenario == "3.5"
    assert res1.next_page == 34


def test_schema_without_explicit_outcome_class_mettete_i_piedi():
    # Scenario JSON where outcome_class is omitted, having only Italian result
    scenario = {
        "id": "mettete_i_piedi_terra_1",
        "victory_outcomes": {
            "tracked_side": "US",
            "metric": "objectives_captured",
            "timing": "end_of_last_turn",
            "table": [
                {"captured": {"min": 3, "max": 3}, "result": "Vittoria totale", "next_scenario": "2.1", "next_page": 20},
                {"captured": {"min": 2, "max": 2}, "result": "Vittoria", "next_scenario": "2.2", "next_page": 22},
                {"captured": {"min": 1, "max": 1}, "result": "Pareggio", "next_scenario": "2.3", "next_page": 24},
                {"captured": {"min": 0, "max": 0}, "result": "Sconfitta totale", "next_scenario": None},
            ],
        },
    }

    # 3 captured -> US Vittoria totale
    res3 = evaluate_scenario_outcome(scenario=scenario, final_vp_by_side={"US": 3, "GE": 0})
    assert res3.outcome_class == OutcomeClass.TOTAL_VICTORY
    assert res3.winner == "US"
    assert res3.outcome_class_by_side == {"US": "total_victory", "GE": "total_defeat"}

    # 0 captured -> US Sconfitta totale -> GE Vittoria totale
    res0 = evaluate_scenario_outcome(scenario=scenario, final_vp_by_side={"US": 0, "GE": 3})
    assert res0.outcome_class == OutcomeClass.TOTAL_DEFEAT
    assert res0.winner == "GE"
    assert res0.outcome_class_by_side == {"US": "total_defeat", "GE": "total_victory"}
    assert res0.outcome_score_by_side == {"US": -1, "GE": 1}


def test_fallback_base_rules_without_objective_table():
    scenario = {"id": "legacy_skirmish", "victory_outcomes": None}

    # 1. Annihilation: only US alive
    res_annihil = evaluate_scenario_outcome(
        scenario=scenario,
        alive_sides=["US"],
        final_vp_by_side={"US": 1, "GE": 1},
    )
    assert res_annihil.winner == "US"
    assert res_annihil.end_reason == "last_side_standing"
    assert res_annihil.outcome_class_by_side == {"GE": "defeat", "US": "victory"}

    # 2. Max turns VP comparison
    res_vp = evaluate_scenario_outcome(
        scenario=scenario,
        alive_sides=["US", "GE"],
        final_vp_by_side={"US": 5, "GE": 2},
    )
    assert res_vp.winner == "US"
    assert res_vp.end_reason == "max_turns_vp"
    assert res_vp.outcome_class_by_side == {"GE": "defeat", "US": "victory"}


def test_scenario_outcome_to_dict_contract(battaglia_cittadina_scenario):
    res = evaluate_scenario_outcome(
        scenario=battaglia_cittadina_scenario,
        final_vp_by_side={"US": 4, "IT": 1},
    )
    d = res.to_dict()
    assert d["winner"] == "US"
    assert d["tracked_side"] == "US"
    assert d["captured"] == 4
    assert d["outcome_class"] == "victory"
    assert d["outcome_score"] == 1
    assert d["outcome_class_by_side"] == {"US": "victory", "IT": "defeat"}
    assert d["outcome_score_by_side"] == {"US": 1, "IT": -1}
    assert d["next_scenario"] == "3.2"
    assert d["next_page"] == 28
