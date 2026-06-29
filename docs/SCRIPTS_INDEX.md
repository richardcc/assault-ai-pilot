# Scripts Index

Central catalog of repository scripts under `scripts/`.

## Experiments V2 (from scratch)

- Queue root: `experiments_v2/queue/*.yaml`
- Worker: `scripts/exp_v2_worker.py`
- Status: `scripts/exp_v2_status.py`
- Docs: `experiments_v2/README.md`

Quick start:

- Run once:
  - `python .\scripts\exp_v2_worker.py --once`
- Run service mode:
  - `python .\scripts\exp_v2_worker.py`
- Check status:
  - `python .\scripts\exp_v2_status.py`

## Most Used Commands

- Reaction Fire strict matrix gate:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_reaction_policy_matrix.ps1 -Episodes 50 -Seed 42 -EnforceGate`
- R2.a no-regression gate (with eval):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\gate_r2a_no_regression_vs_r21i.ps1 -RunEval`
- Single experiment from manifest:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_experiment_from_manifest.ps1 -ManifestPath .\scripts\experiment_manifest.template.json`
- Single experiment from manifest + apply manifest changes:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_experiment_from_manifest.ps1 -ManifestPath .\scripts\experiment_manifest.template.json -ApplyChanges`
- Single experiment forcing old-mismatch apply (advanced):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_experiment_from_manifest.ps1 -ManifestPath .\scripts\experiment_manifest.template.json -ApplyChanges -ForceOldMismatch`
- Batch experiments:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_experiment_batch.ps1 -ManifestsDir .\scripts\experiments -ContinueOnError`
- Batch experiments + apply manifest changes:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_experiment_batch.ps1 -ManifestsDir .\scripts\experiments -ApplyChanges -ContinueOnError`
- Batch experiments + apply manifest changes (force old mismatch):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_experiment_batch.ps1 -ManifestsDir .\scripts\experiments -ApplyChanges -ForceOldMismatch -ContinueOnError`
- Live experiment monitor:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\watch_experiments.ps1`
- Queue worker service (polls manifests and executes pending queue):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\experiment_queue_worker.ps1 -ManifestsDir .\scripts\experiments`
- Queue worker service + apply manifest changes:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\experiment_queue_worker.ps1 -ManifestsDir .\scripts\experiments -ApplyChanges`
- Queue worker service + apply + old mismatch + running guard:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\experiment_queue_worker.ps1 -ManifestsDir .\scripts\experiments -ApplyChanges -ForceOldMismatch`
- Reset manifest status in batch (example: `done_revert -> planned`):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\reset_experiment_status.ps1 -FromStatus done_revert -ToStatus planned`
- Promote passed experiment to archive (`done_keep`):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\promote_experiment.ps1 -ManifestPath .\scripts\experiments\<manifest>.json`

## Training / Eval Gates

- `scripts/gate_r2a_no_regression_vs_r21i.ps1` - No-regression gate vs frozen `R2.1-i` baseline.
- `scripts/gate_reaction_fire_technical.ps1` - Technical integration gate for Reaction Fire.
- `scripts/gate_reaction_fire_natural.ps1` - Natural-occurrence KPI gate for Reaction Fire.
- `scripts/run_reaction_policy_matrix.ps1` - Runs `always/balanced/never` reaction policies and compares outcomes (supports `-EnforceGate`).
- `scripts/run_gap_active_queue.ps1` - One-shot runner for active gate queue.
- `scripts/run_all_gates.ps1` - Aggregate gate runner.
- `scripts/gate_smoke_eval.ps1` - Smoke evaluation gate.
- `scripts/gate_fps_smoke.ps1` - FPS/perf smoke gate.
- `scripts/gate_tests.ps1` - Test-suite gate.
- `scripts/check_latest_eval_gates.ps1` - Quick check of latest eval gate results.
- `scripts/check_trainer_sweep_gate.ps1` - Validates trainer sweep outputs against gate criteria.

## Training / Eval Utilities

- `scripts/sb3_eval_viewer.py` - Viewer for SB3 evaluation reports.
- `scripts/run_eval_parallel_configs.ps1` - Runs eval across multiple config files in parallel.
- `scripts/run_trainer_sweep_it_battaglia.ps1` - Trainer sweep for IT battaglia scenario.
- `scripts/build_trainer_sweep_summary.ps1` - Builds summary artifacts for trainer sweeps.
- `scripts/analyze_us_vp_losses.py` - VP loss analysis helper for US-side runs.
- `scripts/debug_vp_owners_once.py` - One-shot debug script for VP ownership state.

## Reaction Fire / Tactical Debug

- `scripts/test_reaction_fire_e2e.ps1` - End-to-end Reaction Fire test harness.
- `scripts/force_reaction_fire_smoke.py` - Forced Reaction Fire smoke execution helper.

## Roadmap / Closeout Helpers

- `scripts/cerrar_r21i.ps1` - Closeout workflow for `R2.1-i`.
- `scripts/preparar_r21j_si_falla.ps1` - Prepare `R2.1-j` branch workflow if gate fails.
- `scripts/run_r21e_us_gate.ps1` - Gate runner for `R2.1-e` (US-side).
- `scripts/run_r4_policy_redesign_gate.ps1` - Gate workflow for R4 redesign line.
- `scripts/run_r4_1_stepin_head_gate.ps1` - Gate workflow for R4.1 step-in head line.

## Rules / Docs / Parity Validation

- `scripts/ptest_quick.ps1` - Quick parity/doc test subset.
- `scripts/ptest_full.ps1` - Full parity/doc test suite.
- `scripts/ptest_pdf_trace_strict.ps1` - Strict PDF traceability checks.
- `scripts/ptest_rag_copilot.ps1` - RAG copilot validation checks.
- `scripts/ptest_combat_tables.ps1` - Combat tables parity checks.
- `scripts/ptest_rules_tables.ps1` - Rules tables parity checks.
- `scripts/ptest_modifier_parity.ps1` - Modifier parity validation.
- `scripts/archive_cleanup_batch1.ps1` - Cleanup helper for archived run batches.

## Experiment Orchestration

Core scripts:

- `scripts/experiment_manifest.template.json` - Base template for reproducible experiment manifests.
- `scripts/validate_experiment_manifest.py` - Validates manifest schema and single-lever policy constraints.
- `scripts/apply_experiment_changes.py` - Safely applies allowed JSON config changes declared in a manifest.
- `scripts/apply_experiment_changes.py` - Safely applies allowed JSON config changes declared in a manifest (supports `--force-old-mismatch`).
- `scripts/run_experiment_from_manifest.ps1` - Executes one manifest (`validate -> train -> gate`) with per-run logs/artifacts.
- `scripts/run_experiment_from_manifest.ps1` - Executes one manifest (`validate -> [apply] -> train -> gate`) and auto-restores applied files on failure when `-ApplyChanges` is used.
- `scripts/run_experiment_batch.ps1` - Runs multiple manifests in sequence and writes batch summaries.
- `scripts/watch_experiments.ps1` - Live monitor for experiment/batch status from generated artifacts.
- `scripts/experiment_queue_worker.ps1` - Long-running queue worker that polls manifests and auto-runs pending experiments.
- `scripts/reset_experiment_status.ps1` - Bulk status reset helper for experiment manifests (supports dry-run).
- `scripts/promote_experiment.ps1` - Promotes PASS experiments to `experiments_archive/passed` with `done_keep` and promotion log.

### Experiment Definitions (all manifests)

Location: `scripts/experiments/`

- `scripts/experiments/reward_single_lever_vp_stepin_bonus.json` - Aumenta incentivo a elegir step-in legal para recuperar conversion VP.
- `scripts/experiments/reward_single_lever_vp_stepin_missed_penalty_v1.json` - Penaliza mas perder step-in cerca de VP para reducir conversion collapse.
- `scripts/experiments/reward_single_lever_capture_post_contact_bonus_v1.json` - Refuerza progreso CAPTURE tras contacto para acelerar entrada/utilizacion de VP.
- `scripts/experiments/reward_single_lever_non_capture_near_vp_penalty_v1.json` - Desincentiva intents no-CAPTURE cerca de VP cuando hay presion de objetivo.
- `scripts/experiments/heuristic_single_lever_capture_priority.json` - Prioriza step-in legal sobre ataques no relevantes a VP.
- `scripts/experiments/heuristic_single_lever_vp_ally_congestion_penalty_v1.json` - Reduce sobrecarga de aliados en un mismo VP (mejor reparto de lanes).
- `scripts/experiments/architecture_telemetry_policy_vs_finalizer_v1.json` - Separa trazas propuesta-vs-ejecucion para detectar drift policy/finalizer.
- `scripts/experiments/architecture_single_lever_mission_critic_telemetry_v1.json` - Añade telemetria de mission-critic para diagnosticar fallos de conversion.
- `scripts/experiments/planner_single_lever_temporal_objective_windows_v1.json` - Activa ventanas temporales del planner (contacto -> entrada -> hold).
- `scripts/experiments/planner_single_lever_intent_budget_caps_v1.json` - Limita deriva ATTRIT y fuerza ventanas CAPTURE cerca de VP.
- `scripts/experiments/rag_single_lever_failure_pattern_detector_v1.json` - Detector RAG de patrones de fallo de mision en eval/trazas.
- `scripts/experiments/automation_single_lever_postmortem_generator_v1.json` - Genera postmortem automatico por run (causas + siguiente accion).

Archive locations:

- Failed/completed experiments: `scripts/experiments_archive/failed/`
- Passed/promoted experiments: `scripts/experiments_archive/passed/`

## External / Other

- `docs/pdfs/scripts/process_pdfs.py` - PDF processing utility used by docs pipeline.

