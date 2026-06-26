# Trainer Sweep Pipeline

Validation state: **Pending Validation**.

This document describes the automated sweep/eval/gate flow for IT battaglia trainer experiments.

## Scripts

- `scripts/run_trainer_sweep_it_battaglia.ps1`
  - orchestrates A/B/C training in parallel
  - runs comparative eval for successful variants
  - runs gate decision and summary generation
- `scripts/check_trainer_sweep_gate.ps1`
  - evaluates roadmap thresholds from `comparative_summary.csv`
  - outputs `trainer_sweep_gate_decision.csv`
- `scripts/build_trainer_sweep_summary.ps1`
  - writes `decision_summary.md`
  - appends run-level row to `trainer_sweep_history.csv`
- `scripts/archive_cleanup_batch1.ps1`
  - dry-run/apply archive cleanup for low-risk stale files

## Standard run

```powershell
.\scripts\run_trainer_sweep_it_battaglia.ps1
```

Strict CI-like run (fail when no GO):

```powershell
.\scripts\run_trainer_sweep_it_battaglia.ps1 -FailIfNoGo
```

Strict and abort on any training failure:

```powershell
.\scripts\run_trainer_sweep_it_battaglia.ps1 -AbortOnTrainFailure -FailIfNoGo
```

## Output layout

Each run creates:

- `assault_sim/session/reports/sb3_eval/trainer_sweep_it_battaglia_<timestamp>/`
  - `train_logs/train_A.log`
  - `train_logs/train_B.log`
  - `train_logs/train_C.log`
  - `run_configs/train_config_it_sweep_*.run.json`
  - `comparative_summary.csv`
  - `trainer_sweep_gate_decision.csv`
  - `decision_summary.md`

Global history:

- `assault_sim/session/reports/sb3_eval/trainer_sweep_history.csv`

## Gate thresholds (default)

Applied by `check_trainer_sweep_gate.ps1`:

- `true_win_rate_objective >= 0.10`
- `loss_rate <= 0.60`
- `vp_entry_missed_rate < 1.00`
- `captured_4_5 >= 1`

Decisions:

- `GO`: all checks pass.
- `CONDITIONAL GO`: win/loss pass but another check fails.
- `NO-GO`: primary checks fail.

## Cleanup workflow

Review candidates:

```powershell
.\scripts\archive_cleanup_batch1.ps1
```

Apply archive move:

```powershell
.\scripts\archive_cleanup_batch1.ps1 -Apply
```
