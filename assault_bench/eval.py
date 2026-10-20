"""Evaluation Harness canónico para EfficientZero V2 en Assault (Fase 5).

Ejecuta evaluaciones cuantitativas de modelos contra baselines heurísticos
(Random / Rule-based) o en auto-juego (Self-Play), computando métricas de
rendimiento táctico y de perfilado doctrinal:
- recon_survival_rate
- fire_support_stationarity
- spearhead_vp_capture_rate
- doctrine_adherence_rate
- doctrine_mutation_rate
- Verificación de paridad doctrinal contra baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from assault_bench.benchmark_orchestrator import run_benchmark
from assault_bench.doctrine_metrics import (
    aggregate_doctrine_kpis,
    compute_doctrine_role_metrics,
    verify_doctrine_parity,
)


def extract_doctrine_kpis_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extrae y computa las métricas doctrinales agregadas desde el payload de benchmark."""
    # Si ya vienen precalculadas en el payload, retornarlas
    if "doctrine_eval_kpis" in payload and payload["doctrine_eval_kpis"]:
        return dict(payload["doctrine_eval_kpis"])

    # Si hay episodios de replay serializados en el payload
    replays = list(payload.get("bench_replay_episodes", []) or [])
    if replays:
        episode_doctrine_rows = []
        for rep in replays:
            transitions = list(rep.get("transitions", []) or [])
            if transitions:
                m = compute_doctrine_role_metrics(transitions)
                episode_doctrine_rows.append(m)
        if episode_doctrine_rows:
            return aggregate_doctrine_kpis(episode_doctrine_rows)

    # Fallback seguro con valores neutros tipados
    return aggregate_doctrine_kpis([])


def evaluate_checkpoint(
    checkpoint_path: str,
    config_path: str = "assault_bench/configs/benchmark_config.yaml",
    muzero_config_path: str = "",
    device: str = "cpu",
    scenario_id: Optional[str] = None,
    mlflow_experiment: str = "assault_bench_eval",
) -> Dict[str, Any]:
    """Evalúa un checkpoint de EfficientZero V2 y genera reporte integral con métricas doctrinales."""
    payload = run_benchmark(
        config_path=config_path,
        checkpoint_path=checkpoint_path,
        muzero_config_path=muzero_config_path,
        device=device,
        mlflow_experiment=mlflow_experiment,
    )

    # Computar KPIs doctrinales del modelo evaluado
    doctrine_kpis = extract_doctrine_kpis_from_payload(payload)
    payload["doctrine_eval_kpis"] = doctrine_kpis

    # Extraer fila de baseline para paridad (si existe)
    results = list(payload.get("results", []) or [])
    baseline_row = next(
        (r for r in results if str(r.get("agent_name", "")) == "baseline_random"),
        None,
    )
    baseline_doctrine = None
    if baseline_row and "doctrine_kpis" in baseline_row:
        baseline_doctrine = dict(baseline_row.get("doctrine_kpis", {}) or {})

    # Verificación de paridad doctrinal
    parity_report = verify_doctrine_parity(
        eval_doctrine=doctrine_kpis,
        baseline_doctrine=baseline_doctrine,
    )
    payload["doctrine_parity_report"] = parity_report

    return payload


def verify_curriculum_phase_doctrine(
    curriculum_path: str,
    phase_name: str,
    checkpoint_path: str,
    device: str = "cpu",
) -> Dict[str, Any]:
    """Verifica los criterios de gate y doctrina para una fase específica de un currículum."""
    curr_p = Path(curriculum_path).resolve()
    if not curr_p.exists():
        raise FileNotFoundError(f"Curriculum config no encontrado: {curr_p}")

    with curr_p.open("r", encoding="utf-8") as f:
        curr_cfg = yaml.safe_load(f)

    phases = list(curr_cfg.get("phases", []) or [])
    phase_def = next(
        (p for p in phases if str(p.get("name", "")).strip().lower() == phase_name.strip().lower()),
        None,
    )
    if not phase_def:
        raise ValueError(f"Fase '{phase_name}' no encontrada en currículum {curriculum_path}")

    eval_config = str(phase_def.get("eval_config", "assault_bench/configs/benchmark_config.yaml"))
    gate_reqs = dict(phase_def.get("gate", {}) or {})

    payload = evaluate_checkpoint(
        checkpoint_path=checkpoint_path,
        config_path=eval_config,
        device=device,
    )

    doctrine_kpis = payload.get("doctrine_eval_kpis", {})
    gate_status = dict(payload.get("phase_2_9_promotion_gate", {}) or {}).get("status", "FAIL")

    # Extraer umbrales doctrinales del currículum si existen
    min_recon = float(gate_reqs.get("min_recon_survival_rate", 0.40))
    min_fs = float(gate_reqs.get("min_fire_support_stationarity", 0.45))
    min_adh = float(gate_reqs.get("min_doctrine_adherence_rate", 0.35))

    parity = verify_doctrine_parity(
        eval_doctrine=doctrine_kpis,
        min_thresholds={
            "min_recon_survival_rate": min_recon,
            "min_fire_support_stationarity": min_fs,
            "min_doctrine_adherence_rate": min_adh,
        },
    )

    curriculum_verdict = (gate_status == "PASS") and (parity.get("status") == "PASS")

    return {
        "curriculum_name": str(curr_cfg.get("name", "")),
        "phase_name": phase_name,
        "checkpoint_path": checkpoint_path,
        "promotion_gate_status": gate_status,
        "doctrine_parity_status": parity.get("status"),
        "overall_curriculum_pass": curriculum_verdict,
        "doctrine_kpis": doctrine_kpis,
        "parity_details": parity,
        "benchmark_payload": payload,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assault Evaluation Harness: Evaluación de EfficientZero V2 y Perfilado Doctrinal."
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="Path al checkpoint .pt del modelo o 'latest'/'auto'.",
    )
    parser.add_argument(
        "--config",
        default="assault_bench/configs/benchmark_config.yaml",
        help="Path a la configuración YAML de benchmark.",
    )
    parser.add_argument(
        "--curriculum",
        default="",
        help="Opcional: Path al archivo curriculum.yaml.",
    )
    parser.add_argument(
        "--phase",
        default="phase1_bootstrap",
        help="Nombre de la fase del currículum a evaluar.",
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda", "auto"),
        default="cpu",
        help="Dispositivo de inferencia para MCTS y red neuronal.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Imprime el payload JSON completo a stdout.",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    if args.curriculum:
        report = verify_curriculum_phase_doctrine(
            curriculum_path=args.curriculum,
            phase_name=args.phase,
            checkpoint_path=args.checkpoint,
            device=args.device,
        )
        if args.print_json:
            print(json.dumps(report, indent=2))
        else:
            print("=" * 70)
            print(f"ASSAULT CURRICULUM EVALUATION: {report['curriculum_name']} / {report['phase_name']}")
            print("=" * 70)
            print(f"Checkpoint:             {report['checkpoint_path'] or 'baseline/stub'}")
            print(f"Promotion Gate Status:  {report['promotion_gate_status']}")
            print(f"Doctrine Parity Status: {report['doctrine_parity_status']}")
            print(f"Overall Verdict:        {'🟢 PASS' if report['overall_curriculum_pass'] else '🔴 FAIL'}")
            print("-" * 70)
            kpis = report["doctrine_kpis"]
            print(f"Recon Survival Rate:         {kpis.get('recon_survival_rate', 0.0) * 100:.1f}%")
            print(f"Fire Support Stationarity:   {kpis.get('fire_support_stationarity', 0.0) * 100:.1f}%")
            print(f"Spearhead VP Capture Rate:   {kpis.get('spearhead_vp_capture_rate', 0.0) * 100:.1f}%")
            print(f"Doctrine Adherence Rate:     {kpis.get('doctrine_adherence_rate', 0.0) * 100:.1f}%")
            print(f"Doctrine Mutation Rate:      {kpis.get('doctrine_mutation_rate', 0.0) * 100:.1f}%")
            print("=" * 70)
    else:
        payload = evaluate_checkpoint(
            checkpoint_path=args.checkpoint,
            config_path=args.config,
            device=args.device,
        )
        if args.print_json:
            print(json.dumps(payload, indent=2))
        else:
            gate = dict(payload.get("phase_2_9_promotion_gate", {}) or {}).get("status", "N/A")
            parity = dict(payload.get("doctrine_parity_report", {}) or {}).get("status", "N/A")
            kpis = dict(payload.get("doctrine_eval_kpis", {}) or {})
            print("=" * 70)
            print("ASSAULT BENCHMARK & DOCTRINE EVALUATION REPORT")
            print("=" * 70)
            print(f"Scenario:                    {payload.get('scenario_id', 'unknown')}")
            print(f"Run ID:                      {payload.get('run_id', 'n/a')}")
            print(f"Phase 2.9 Promotion Gate:    {gate}")
            print(f"Doctrine Parity:             {parity}")
            print("-" * 70)
            print(f"Recon Survival Rate:         {kpis.get('recon_survival_rate', 0.0) * 100:.1f}%")
            print(f"Fire Support Stationarity:   {kpis.get('fire_support_stationarity', 0.0) * 100:.1f}%")
            print(f"Spearhead VP Capture Rate:   {kpis.get('spearhead_vp_capture_rate', 0.0) * 100:.1f}%")
            print(f"Doctrine Adherence Rate:     {kpis.get('doctrine_adherence_rate', 0.0) * 100:.1f}%")
            print(f"Doctrine Mutation Rate:      {kpis.get('doctrine_mutation_rate', 0.0) * 100:.1f}%")
            print("=" * 70)


if __name__ == "__main__":
    main()
