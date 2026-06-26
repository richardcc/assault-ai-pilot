# Unused Files Inventory (Batch v44)

Validation state: **Pending Validation**.

This inventory tracks low-risk cleanup candidates identified during roadmap batch execution.

## Candidate groups

- `config_backups`
  - `assault_sim/config/train_config.backup.json`
  - `assault_sim/config/train_config.ab_backup.json`
  - `assault_sim/config/train_config.c2_backup.json`
  - `assault_sim/config/train_config.curriculum_backup.json`
- `tmp_parallel_configs`
  - `assault_sim/session/tmp_parallel/train_config_*.parallel.json`
- `old_eval_reports`
  - `assault_sim/session/reports/sb3_eval/metrics_sb3_report_*.json` (high volume historical outputs)

## Cleanup policy

- Never delete the latest successful run artifacts used by current tuning.
- For `config_backups`, move to archival bucket or delete only after confirming no script references.
- For `tmp_parallel_configs`, keep only currently active scenario-side configs.
- For `old_eval_reports`, retain recent windows and archive older batches.

## Next safe step

Run a reference check against scripts/docs and then clean by small batches:

1. archive/remove `config_backups`,
2. prune obsolete `tmp_parallel_configs`,
3. archive old `metrics_sb3_report_*.json` beyond active tuning window.

## Automation added

- `scripts/archive_cleanup_batch1.ps1`
  - default mode: dry-run (no changes)
  - apply mode: moves candidates to `assault_sim/deprecated/cleanup_batch1_<timestamp>/...`
- `scripts/check_trainer_sweep_gate.ps1`
  - reads `comparative_summary.csv` from sweep output
  - enriches with mission metrics from per-row `report` JSON
  - emits per-config decision (`GO`, `CONDITIONAL GO`, `NO-GO`) and `rollback_required`
- `scripts/build_trainer_sweep_summary.ps1`
  - consumes `trainer_sweep_gate_decision.csv`
  - writes `decision_summary.md`
  - appends run-level row into `trainer_sweep_history.csv` with promotion/rollback flags
- Pipeline reference:
  - `docs/TRAINER_SWEEP_PIPELINE.md`
