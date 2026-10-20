"""Tests para la evaluación y verificación en currículum (Fase 5 - Perfilado Doctrinal)."""

from __future__ import annotations

import pytest

from assault_bench.doctrine_metrics import (
    aggregate_doctrine_kpis,
    compute_doctrine_role_metrics,
    verify_doctrine_parity,
)
from assault_bench.eval import extract_doctrine_kpis_from_payload


def test_compute_doctrine_role_metrics_empty():
    res = compute_doctrine_role_metrics([])
    assert res["recon_survival_rate"] == 1.0
    assert res["fire_support_stationarity"] == 1.0
    assert res["spearhead_vp_capture_rate"] == 0.0
    assert res["doctrine_adherence_rate"] == 0.0
    assert res["doctrine_mutation_rate"] == 0.0
    assert res["total_decisions"] == 0


def test_compute_doctrine_role_metrics_functional():
    # Escenario simulado:
    # 2 unidades recon iniciales (us_recon_jeep_1, us_recon_jeep_2).
    # 1 unidad de apoyo fuego (us_hmg_m2hb_1).
    # 1 unidad punta de lanza (us_rifle_squad_1).
    first_row_units = [
        {"unit_id": "us_recon_jeep_1", "doctrine_role": "ROLE_RECON", "alive": True, "hp": 3.0},
        {"unit_id": "us_recon_jeep_2", "doctrine_role": "ROLE_RECON", "alive": True, "hp": 3.0},
        {"unit_id": "us_hmg_m2hb_1", "doctrine_role": "ROLE_FIRE_SUPPORT", "alive": True, "hp": 4.0},
        {"unit_id": "us_rifle_squad_1", "doctrine_role": "ROLE_SPEARHEAD", "alive": True, "hp": 6.0},
    ]

    last_row_units = [
        {"unit_id": "us_recon_jeep_1", "doctrine_role": "ROLE_RECON", "alive": True, "hp": 2.0},
        {"unit_id": "us_recon_jeep_2", "doctrine_role": "ROLE_RECON", "alive": False, "hp": 0.0},
        {"unit_id": "us_hmg_m2hb_1", "doctrine_role": "ROLE_FIRE_SUPPORT", "alive": True, "hp": 4.0},
        {"unit_id": "us_rifle_squad_1", "doctrine_role": "ROLE_SPEARHEAD", "alive": True, "hp": 4.0},
    ]

    trace_rows = [
        # Paso 0: Recon Jeep se mueve con boost de reconocimiento
        {
            "step": 0,
            "unit_id": "us_recon_jeep_1",
            "acting_unit_id": "us_recon_jeep_1",
            "action_kind": "MOVE",
            "role_assigned": "ROLE_RECON",
            "role_is_mutated": False,
            "role_mutation_reason": "DEFAULT_PROFILE",
            "prior_boost_applied": 0.35,
            "units": first_row_units,
        },
        # Paso 1: HMG dispara estacionariamente (ATTACK)
        {
            "step": 1,
            "unit_id": "us_hmg_m2hb_1",
            "acting_unit_id": "us_hmg_m2hb_1",
            "action_kind": "ATTACK",
            "role_assigned": "ROLE_FIRE_SUPPORT",
            "role_is_mutated": False,
            "role_mutation_reason": "DEFAULT_PROFILE",
            "prior_boost_applied": 0.35,
            "units": first_row_units,
        },
        # Paso 2: HMG se reposiciona (MOVE)
        {
            "step": 2,
            "unit_id": "us_hmg_m2hb_1",
            "acting_unit_id": "us_hmg_m2hb_1",
            "action_kind": "MOVE",
            "role_assigned": "ROLE_FIRE_SUPPORT",
            "role_is_mutated": False,
            "role_mutation_reason": "DEFAULT_PROFILE",
            "prior_boost_applied": 0.0,
            "units": first_row_units,
        },
        # Paso 3: Rifle squad muta a SPEARHEAD por déficit y captura VP
        {
            "step": 3,
            "unit_id": "us_rifle_squad_1",
            "acting_unit_id": "us_rifle_squad_1",
            "action_kind": "MOVE",
            "role_assigned": "ROLE_SPEARHEAD",
            "role_is_mutated": True,
            "role_mutation_reason": "VP_DEFICIT_PRESSURE",
            "prior_boost_applied": 0.35,
            "is_vp_capture_taken": True,
            "units": last_row_units,
        },
    ]

    metrics = compute_doctrine_role_metrics(trace_rows)

    # 1 de 2 recon sobrevivió -> 50%
    assert metrics["recon_initial_count"] == 2
    assert metrics["recon_final_alive"] == 1
    assert metrics["recon_survival_rate"] == 0.50

    # HMG: 1 ATTACK (estacionario), 1 MOVE -> 1/2 = 50%
    assert metrics["fire_support_total_actions"] == 2
    assert metrics["fire_support_stationary_actions"] == 1
    assert metrics["fire_support_stationarity"] == 0.50

    # Capturas de VP: 1 total, realizada por SPEARHEAD -> 100%
    assert metrics["vp_captures_total"] == 1
    assert metrics["spearhead_vp_captures"] == 1
    assert metrics["spearhead_vp_capture_rate"] == 1.0

    # Adherencia: 3 de 4 pasos tuvieron prior_boost_applied > 0 -> 75%
    assert metrics["total_decisions"] == 4
    assert metrics["boosted_decisions"] == 3
    assert metrics["doctrine_adherence_rate"] == 0.75

    # Mutación: 1 de 4 pasos mutó de rol -> 25%
    assert metrics["mutated_unit_steps"] == 1
    assert metrics["doctrine_mutation_rate"] == 0.25
    assert metrics["mutation_counts_by_reason"] == {"VP_DEFICIT_PRESSURE": 1}


def test_aggregate_doctrine_kpis():
    ep1 = {
        "recon_initial_count": 2,
        "recon_final_alive": 2,
        "fire_support_total_actions": 4,
        "fire_support_stationary_actions": 3,
        "vp_captures_total": 2,
        "spearhead_vp_captures": 2,
        "total_decisions": 10,
        "boosted_decisions": 8,
        "total_unit_steps": 10,
        "mutated_unit_steps": 2,
        "mutation_counts_by_reason": {"VP_DEFICIT_PRESSURE": 2},
    }
    ep2 = {
        "recon_initial_count": 2,
        "recon_final_alive": 1,
        "fire_support_total_actions": 6,
        "fire_support_stationary_actions": 3,
        "vp_captures_total": 2,
        "spearhead_vp_captures": 1,
        "total_decisions": 10,
        "boosted_decisions": 6,
        "total_unit_steps": 10,
        "mutated_unit_steps": 1,
        "mutation_counts_by_reason": {"MORALE_OR_HEALTH_DEGRADATION": 1},
    }

    agg = aggregate_doctrine_kpis([ep1, ep2])

    # Recon: (2+1) / (2+2) = 3/4 = 0.75
    assert agg["recon_survival_rate"] == 0.75
    # FS: (3+3) / (4+6) = 6/10 = 0.60
    assert agg["fire_support_stationarity"] == 0.60
    # Spearhead capture: (2+1) / (2+2) = 3/4 = 0.75
    assert agg["spearhead_vp_capture_rate"] == 0.75
    # Adherence: (8+6) / 20 = 14/20 = 0.70
    assert agg["doctrine_adherence_rate"] == 0.70
    # Mutation rate: (2+1) / 20 = 3/20 = 0.15
    assert agg["doctrine_mutation_rate"] == 0.15
    assert agg["mutation_counts_by_reason"] == {
        "VP_DEFICIT_PRESSURE": 2,
        "MORALE_OR_HEALTH_DEGRADATION": 1,
    }


def test_verify_doctrine_parity_pass():
    eval_doc = {
        "recon_survival_rate": 0.75,
        "fire_support_stationarity": 0.60,
        "doctrine_adherence_rate": 0.70,
        "spearhead_vp_capture_rate": 0.80,
        "doctrine_mutation_rate": 0.15,
    }
    baseline_doc = {
        "recon_survival_rate": 0.50,
        "fire_support_stationarity": 0.30,
        "doctrine_adherence_rate": 0.20,
    }
    report = verify_doctrine_parity(eval_doctrine=eval_doc, baseline_doctrine=baseline_doc)
    assert report["status"] == "PASS"
    assert report["checks"]["recon_survival_pass"] is True
    assert report["checks"]["fire_support_stationarity_pass"] is True
    assert report["checks"]["doctrine_adherence_pass"] is True


def test_verify_doctrine_parity_fail():
    eval_doc = {
        "recon_survival_rate": 0.20,  # Bajo umbral mínimo de 0.40
        "fire_support_stationarity": 0.25,  # Bajo umbral de 0.45
        "doctrine_adherence_rate": 0.10,  # Bajo umbral de 0.35
    }
    report = verify_doctrine_parity(eval_doctrine=eval_doc)
    assert report["status"] == "FAIL"
    assert report["checks"]["recon_survival_pass"] is False
    assert report["checks"]["fire_support_stationarity_pass"] is False
    assert report["checks"]["doctrine_adherence_pass"] is False


def test_extract_doctrine_kpis_from_payload():
    # Caso 1: Payload con doctrine_eval_kpis explícito
    p1 = {"doctrine_eval_kpis": {"recon_survival_rate": 0.85}}
    kpis = extract_doctrine_kpis_from_payload(p1)
    assert kpis["recon_survival_rate"] == 0.85

    # Caso 2: Payload vacío fallback
    p2 = {}
    kpis2 = extract_doctrine_kpis_from_payload(p2)
    assert kpis2["recon_survival_rate"] == 1.0
