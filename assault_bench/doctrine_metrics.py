"""Métricas doctrinales y evaluación de comportamiento por rol para EfficientZero V2.

Calcula indicadores de alineación doctrinal a partir de las filas de traza
(trace_rows) de benchmark y auto-juego:
- recon_survival_rate: Tasa de supervivencia de unidades de exploración/reconocimiento.
- fire_support_stationarity: Proporción de turnos en que unidades de apoyo por fuego
  mantienen su posición (disparando, vigilando o sosteniendo en vez de avanzar a ciegas).
- spearhead_vp_capture_rate: Porcentaje de capturas de VPs ejecutadas por unidades de asalto.
- doctrine_adherence_rate: Proporción de decisiones con modulación prior afín al rol activo.
- doctrine_mutation_rate: Frecuencia de mutación contextual respecto al perfil base.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from assault_bench.transform_ops import to_dict_rows


def compute_doctrine_role_metrics(
    trace_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calcula las métricas doctrinales para un episodio dado su historial de trazas."""
    rows = to_dict_rows(trace_rows)
    if not rows:
        return {
            "recon_survival_rate": 1.0,
            "fire_support_stationarity": 1.0,
            "spearhead_vp_capture_rate": 0.0,
            "doctrine_adherence_rate": 0.0,
            "doctrine_mutation_rate": 0.0,
            "recon_initial_count": 0,
            "recon_final_alive": 0,
            "fire_support_total_actions": 0,
            "fire_support_stationary_actions": 0,
            "vp_captures_total": 0,
            "spearhead_vp_captures": 0,
            "total_decisions": 0,
            "boosted_decisions": 0,
            "total_unit_steps": 0,
            "mutated_unit_steps": 0,
            "mutation_counts_by_reason": {},
            "role_step_distribution": {},
        }

    # 1. Recon Survival Rate
    # Extraer unidades del primer snapshot para contar recon iniciales
    first_row_units = list(rows[0].get("units", []) or [])
    last_row_units = list(rows[-1].get("units", []) or [])

    recon_initial_ids: set[str] = set()
    for u in first_row_units:
        uid = str(u.get("unit_id", "") or "")
        doc_role = str(u.get("doctrine_role", "") or "")
        active_role = str(u.get("active_role", "") or "")
        if "RECON" in doc_role.upper() or "RECON" in active_role.upper():
            if uid:
                recon_initial_ids.add(uid)

    recon_alive_final = 0
    if recon_initial_ids:
        for u in last_row_units:
            uid = str(u.get("unit_id", "") or "")
            if uid in recon_initial_ids:
                is_alive = bool(u.get("alive", False))
                hp = float(u.get("hp", 0.0) or 0.0)
                if is_alive and hp > 0:
                    recon_alive_final += 1
        recon_survival_rate = float(recon_alive_final) / float(len(recon_initial_ids))
    else:
        recon_survival_rate = 1.0

    # 2. Fire Support Stationarity & 3. Spearhead VP Capture & 4. Adherence & 5. Mutations
    fs_total = 0
    fs_stationary = 0
    vp_captures_total = 0
    spearhead_vp_captures = 0
    total_decisions = 0
    boosted_decisions = 0
    total_unit_steps = 0
    mutated_unit_steps = 0
    mutation_reasons: Dict[str, int] = {}
    role_distribution: Dict[str, int] = {}

    for row in rows:
        acting_uid = str(row.get("acting_unit_id", row.get("unit_id", "")) or "")
        action_kind = str(row.get("action_kind", "") or "").strip().upper()
        role_assigned = str(
            row.get("role_assigned", row.get("unit_macro_role", "")) or ""
        ).upper()
        role_is_mutated = bool(row.get("role_is_mutated", False))
        mutation_reason = str(row.get("role_mutation_reason", "") or "")
        prior_boost = float(row.get("prior_boost_applied", 0.0) or 0.0)

        # Registro de decisiones
        if action_kind and action_kind not in {"TIMEOUT"}:
            total_decisions += 1
            if prior_boost > 1e-4:
                boosted_decisions += 1

        # Trazabilidad de roles
        if role_assigned:
            role_distribution[role_assigned] = role_distribution.get(role_assigned, 0) + 1
            total_unit_steps += 1
            if role_is_mutated:
                mutated_unit_steps += 1
                reason_key = mutation_reason or "UNKNOWN_MUTATION"
                mutation_reasons[reason_key] = mutation_reasons.get(reason_key, 0) + 1

        # Fire support stationarity: acciones no-MOVE por unidades de apoyo de fuego
        if "FIRE_SUPPORT" in role_assigned:
            fs_total += 1
            if action_kind not in {"MOVE", "ADVANCE", "CHARGE"}:
                fs_stationary += 1

        # Spearhead VP capture rate
        why_vp = dict(row.get("why_action_vs_vp", {}) or {})
        is_capture = bool(
            why_vp.get("is_vp_capture_taken", False)
            or row.get("is_vp_capture_taken", False)
        )
        if is_capture:
            vp_captures_total += 1
            if "SPEARHEAD" in role_assigned:
                spearhead_vp_captures += 1

    fs_stationarity_rate = (
        float(fs_stationary) / float(fs_total) if fs_total > 0 else 1.0
    )
    spearhead_capture_rate = (
        float(spearhead_vp_captures) / float(vp_captures_total)
        if vp_captures_total > 0
        else 0.0
    )
    adherence_rate = (
        float(boosted_decisions) / float(total_decisions)
        if total_decisions > 0
        else 0.0
    )
    mutation_rate = (
        float(mutated_unit_steps) / float(total_unit_steps)
        if total_unit_steps > 0
        else 0.0
    )

    return {
        "recon_survival_rate": recon_survival_rate,
        "fire_support_stationarity": fs_stationarity_rate,
        "spearhead_vp_capture_rate": spearhead_capture_rate,
        "doctrine_adherence_rate": adherence_rate,
        "doctrine_mutation_rate": mutation_rate,
        "recon_initial_count": int(len(recon_initial_ids)),
        "recon_final_alive": int(recon_alive_final),
        "fire_support_total_actions": int(fs_total),
        "fire_support_stationary_actions": int(fs_stationary),
        "vp_captures_total": int(vp_captures_total),
        "spearhead_vp_captures": int(spearhead_vp_captures),
        "total_decisions": int(total_decisions),
        "boosted_decisions": int(boosted_decisions),
        "total_unit_steps": int(total_unit_steps),
        "mutated_unit_steps": int(mutated_unit_steps),
        "mutation_counts_by_reason": mutation_reasons,
        "role_step_distribution": role_distribution,
    }


def aggregate_doctrine_kpis(
    seed_doctrine_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Agrega las métricas doctrinales a través de múltiples episodios/semillas."""
    rows = to_dict_rows(seed_doctrine_rows)
    if not rows:
        return {
            "recon_survival_rate": 1.0,
            "fire_support_stationarity": 1.0,
            "spearhead_vp_capture_rate": 0.0,
            "doctrine_adherence_rate": 0.0,
            "doctrine_mutation_rate": 0.0,
            "recon_initial_total": 0,
            "recon_final_alive_total": 0,
            "fire_support_total_actions": 0,
            "fire_support_stationary_actions": 0,
            "vp_captures_total": 0,
            "spearhead_vp_captures": 0,
            "total_decisions": 0,
            "boosted_decisions": 0,
            "total_unit_steps": 0,
            "mutated_unit_steps": 0,
            "mutation_counts_by_reason": {},
            "role_step_distribution": {},
        }

    recon_init_sum = sum(int(r.get("recon_initial_count", 0) or 0) for r in rows)
    recon_alive_sum = sum(int(r.get("recon_final_alive", 0) or 0) for r in rows)
    fs_total_sum = sum(int(r.get("fire_support_total_actions", 0) or 0) for r in rows)
    fs_stat_sum = sum(int(r.get("fire_support_stationary_actions", 0) or 0) for r in rows)
    vp_cap_sum = sum(int(r.get("vp_captures_total", 0) or 0) for r in rows)
    sh_cap_sum = sum(int(r.get("spearhead_vp_captures", 0) or 0) for r in rows)
    decisions_sum = sum(int(r.get("total_decisions", 0) or 0) for r in rows)
    boosted_sum = sum(int(r.get("boosted_decisions", 0) or 0) for r in rows)
    unit_steps_sum = sum(int(r.get("total_unit_steps", 0) or 0) for r in rows)
    mutated_steps_sum = sum(int(r.get("mutated_unit_steps", 0) or 0) for r in rows)

    mutations_agg: Dict[str, int] = {}
    roles_agg: Dict[str, int] = {}
    for r in rows:
        for k, v in dict(r.get("mutation_counts_by_reason", {}) or {}).items():
            mutations_agg[str(k)] = mutations_agg.get(str(k), 0) + int(v or 0)
        for k, v in dict(r.get("role_step_distribution", {}) or {}).items():
            roles_agg[str(k)] = roles_agg.get(str(k), 0) + int(v or 0)

    recon_survival = (
        float(recon_alive_sum) / float(recon_init_sum) if recon_init_sum > 0 else 1.0
    )
    fs_stationarity = (
        float(fs_stat_sum) / float(fs_total_sum) if fs_total_sum > 0 else 1.0
    )
    spearhead_capture = (
        float(sh_cap_sum) / float(vp_cap_sum) if vp_cap_sum > 0 else 0.0
    )
    adherence = (
        float(boosted_sum) / float(decisions_sum) if decisions_sum > 0 else 0.0
    )
    mutation_rate = (
        float(mutated_steps_sum) / float(unit_steps_sum) if unit_steps_sum > 0 else 0.0
    )

    return {
        "recon_survival_rate": recon_survival,
        "fire_support_stationarity": fs_stationarity,
        "spearhead_vp_capture_rate": spearhead_capture,
        "doctrine_adherence_rate": adherence,
        "doctrine_mutation_rate": mutation_rate,
        "recon_initial_total": recon_init_sum,
        "recon_final_alive_total": recon_alive_sum,
        "fire_support_total_actions": fs_total_sum,
        "fire_support_stationary_actions": fs_stat_sum,
        "vp_captures_total": vp_cap_sum,
        "spearhead_vp_captures": sh_cap_sum,
        "total_decisions": decisions_sum,
        "boosted_decisions": boosted_sum,
        "total_unit_steps": unit_steps_sum,
        "mutated_unit_steps": mutated_steps_sum,
        "mutation_counts_by_reason": mutations_agg,
        "role_step_distribution": roles_agg,
    }


def verify_doctrine_parity(
    eval_doctrine: Dict[str, Any],
    baseline_doctrine: Optional[Dict[str, Any]] = None,
    min_thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Evalúa la conformidad doctrinal y paridad frente a baseline o umbrales mínimos."""
    thresholds = {
        "min_recon_survival_rate": 0.40,
        "min_fire_support_stationarity": 0.45,
        "min_doctrine_adherence_rate": 0.35,
    }
    if min_thresholds:
        thresholds.update(min_thresholds)

    eval_recon = float(eval_doctrine.get("recon_survival_rate", 1.0))
    eval_fs = float(eval_doctrine.get("fire_support_stationarity", 1.0))
    eval_adherence = float(eval_doctrine.get("doctrine_adherence_rate", 0.0))

    base_recon = (
        float(baseline_doctrine.get("recon_survival_rate", 0.0))
        if baseline_doctrine
        else 0.0
    )

    checks = {
        "recon_survival_pass": bool(eval_recon >= max(thresholds["min_recon_survival_rate"], base_recon - 0.05)),
        "fire_support_stationarity_pass": bool(eval_fs >= thresholds["min_fire_support_stationarity"]),
        "doctrine_adherence_pass": bool(eval_adherence >= thresholds["min_doctrine_adherence_rate"]),
    }

    all_pass = all(bool(v) for v in checks.values())
    return {
        "status": "PASS" if all_pass else "FAIL",
        "checks": checks,
        "eval_metrics": {
            "recon_survival_rate": eval_recon,
            "fire_support_stationarity": eval_fs,
            "doctrine_adherence_rate": eval_adherence,
            "spearhead_vp_capture_rate": float(eval_doctrine.get("spearhead_vp_capture_rate", 0.0)),
            "doctrine_mutation_rate": float(eval_doctrine.get("doctrine_mutation_rate", 0.0)),
        },
        "thresholds_applied": thresholds,
    }
