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

- VOEC/MuZero train runner (default config):
  - `python -m agents.muzero.train.train_muzero`
- VOEC/MuZero train runner (custom config):
  - `python -m agents.muzero.train.train_muzero --config agents/muzero/configs/muzero_config.test.yaml`
- VOEC/MuZero train runner (dev config):
  - `python -m agents.muzero.train.train_muzero --config agents/muzero/configs/muzero_config.dev.yaml`
- VOEC/MuZero train runner (dev-plus config):
  - `python -m agents.muzero.train.train_muzero --config agents/muzero/configs/muzero_config.dev_plus.yaml`
- VOEC/MuZero train runner (dev-plus 8 workers):
  - `python -m agents.muzero.train.train_muzero --config agents/muzero/configs/muzero_config.dev_plus_8w.yaml`
- VOEC/MuZero train runner (resume from checkpoint):
  - `python -m agents.muzero.train.train_muzero --config agents/muzero/configs/muzero_config.yaml` (set `train.resume_checkpoint` in YAML)
- VOEC benchmark runner (default config):
  - `python -m assault_bench.runner`
- VOEC benchmark runner (custom config):
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.test.yaml`
- VOEC benchmark runner (dev config):
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.dev.yaml`
- VOEC benchmark runner (dev-plus config):
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.dev_plus.yaml`
- VOEC benchmark with trained checkpoint:
  - `python -m assault_bench.runner --config assault_bench/configs/benchmark_config.dev_plus.yaml --checkpoint runs/<run_id>/checkpoints/iter_11.pt`
- VOEC UI timeline export (CLI):
  - `python -m voec_sim.ui_contract.export_timeline --voec-config voec_sim/configs/voec_config.yaml --scenario battaglia_cittadina_2_1 --seed 42 --policy first --max-steps 200 --out runs/ui_timeline_latest.json`

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

- `scripts/sb3_eval_viewer.py` - Viewer for SB3 reports + MuZero Ops tab (runs, integrity, benchmark latest).
- `docs/MUZERO_STRATEGY_TAXONOMY.md` - Canonical mapping from MuZero `action_kind` to strategy labels used by reports.
- `scripts/run_muzero_train_and_bench.ps1` - Runs MuZero train + benchmark in sequence, auto-picking latest `run_id` checkpoint.
- `scripts/run_muzero_train_and_bench.ps1 -Profile smoke` - Very short smoke profile for rapid channel/projection/reward sanity checks.
- `scripts/run_muzero_reaction_fire_ab.ps1` - MuZero-only A/B runner for Reaction Fire (`ASSAULT_ENABLE_REACTION_FIRE=1/0`) with comparative summary.
- `scripts/run_muzero_smoke_ab3.ps1` - Runs 3 smoke repetitions (seed sweep) and writes per-run + aggregate KPI summaries for quick low-noise comparisons.
- `scripts/run_muzero_objective_head_ab.ps1` - MuZero A/B runner for objective auxiliary head (`train.objective_loss_weight` OFF/ON), with objective funnel + benchmark comparative summary.
- `scripts/run_muzero_objective_head_ab3.ps1` - MuZero A/B x3 seeds for objective auxiliary head, with short-budget train overrides and explicit `on-off` delta summary.
- `scripts/run_muzero_objective_head_ab3_medium.ps1` - Medium-budget AB3 preset for objective head (`iterations=10`, `episodes_per_iter=8`) to reduce variance before deciding ON/OFF.
- `scripts/run_muzero_vp_progress_ab3.ps1` - MuZero AB3 runner for VP-progress tuning (`baseline` vs `progress`) with objective funnel/reason deltas and turn-limit finish impact.
- `scripts/run_muzero_vp_progress_ab3_long.ps1` - Long-budget AB3 preset for VP-progress tuning (`iterations=24`, `episodes_per_iter=16`).
- `scripts/run_muzero_timeline_export.ps1` - Exports a replay-ready timeline JSON from a MuZero run (`train_events`) for the viewer replay tab.
- `scripts/run_eval_parallel_configs.ps1` - Runs eval across multiple config files in parallel.
- `scripts/run_trainer_sweep_it_battaglia.ps1` - Trainer sweep for IT battaglia scenario.
- `scripts/build_trainer_sweep_summary.ps1` - Builds summary artifacts for trainer sweeps.
- `scripts/analyze_us_vp_losses.py` - VP loss analysis helper for US-side runs.
- `scripts/debug_vp_owners_once.py` - One-shot debug script for VP ownership state.

## VOEC / MuZero Runners

- `agents/muzero/train/train_muzero.py` - MuZero training runner with `--config` YAML support.
- `assault_bench/runner.py` - Benchmark runner with `--config` YAML support.
- `agents/muzero/configs/muzero_config.yaml` - Default MuZero config.
- `agents/muzero/configs/muzero_config.test.yaml` - Fast smoke config for CI/tests.
- `agents/muzero/configs/muzero_config.smoke.yaml` - Short local smoke config (slightly extended episodes) for fast-but-more-stable diagnostics.
- `agents/muzero/configs/muzero_config.dev.yaml` - Development training config (aligned to benchmark dev).
- `agents/muzero/configs/muzero_config.dev_plus.yaml` - Extended training config (higher budget for measurable separation).
- `agents/muzero/configs/muzero_config.dev_plus_8w.yaml` - Extended training config with `selfplay.num_workers=8`.
- `agents/muzero/configs/muzero_config.yaml::train.resume_checkpoint` - Optional checkpoint path for resume runs.
- `agents/muzero/configs/muzero_config.yaml::selfplay.mcts_unroll_steps` - Latent unroll depth for model-value planning.
- `agents/muzero/configs/muzero_config.yaml::selfplay.mcts_discount` - Discount used during latent multi-step value estimation.
- `agents/muzero/configs/muzero_config.yaml::model.device` - Device selector (`auto|cpu|cuda`) for training.
- `agents/muzero/configs/muzero_config.yaml::model.device_benchmark_steps` - Steps for auto device micro-benchmark when `device=auto`.
- `agents/muzero/configs/muzero_config.yaml::selfplay.num_workers` - Parallel self-play workers (CPU mode).
- `assault_bench/configs/benchmark_config.yaml` - Default benchmark config.
- `assault_bench/configs/benchmark_config.test.yaml` - Fast benchmark smoke config.
- `assault_bench/configs/benchmark_config.smoke.yaml` - Short benchmark config paired with MuZero smoke profile (extended seed count for better signal).
- `assault_bench/configs/benchmark_config.dev.yaml` - Development benchmark config (more seeds/steps).
- `assault_bench/configs/benchmark_config.dev_plus.yaml` - Extended benchmark config (higher horizon + more seeds).
- `assault_bench/configs/benchmark_config.yaml::benchmark.num_workers` - Parallel benchmark workers by seed.
- `voec_sim/configs/voec_config.yaml` - Shared VOEC asset-path and default scenario config.
- `voec_sim/ui_contract/export_timeline.py` - CLI to export replay-ready `EpisodeTimeline` JSON.
- `agents/muzero/xai/timeline_exporter.py` - Converts MuZero run events into VOEC-compatible timeline JSON (`EpisodeTimeline` shape).

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

