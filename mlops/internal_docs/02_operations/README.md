# 02 Operations

Validation state: **Pending Validation**.

## Local Run

```powershell
python -m mlops.orchestrator.run --config mlops/configs/experiment_config.yaml
```

## EfficientZero v2 (Primary)

Quick command (PowerShell):

```powershell
.\scripts\run_efficientzero_v2_quick.ps1
```

Quick train + bench (single command):

```powershell
.\scripts\run_efficientzero_v2_train_bench_quick.ps1
```

VP-capture tuning note (2026-07-15, **Pending Validation**):

- Updated EZv2 reward/objective defaults and presets to increase VP capture prioritization with moderate deltas.
- Tuned keys: `capture_bonus`, `vp_capture_bonus_per_hex`, `objective_progress_bonus_per_hex`, `objective_no_progress_penalty`, `objective_no_progress_attack_penalty`, `objective_pos_weight`, `objective_opportunity_max_dist`, and `objective_signal.opportunity_near_vp_max_dist`.
- Applied consistently in `efficientzero_v2_config.yaml`, `efficientzero_v2_config.min_valid.yaml`, and `efficientzero_v2_config.capture_v1.yaml`.

Standard daily flow (train + bench + viewer):

```powershell
.\scripts\run_efficientzero_v2_train_bench_quick.ps1
.\scripts\build_curriculum_reporting_catalog.ps1
.\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow
```

## MuZero (Legacy)

MuZero remains available for historical comparisons only.

Quick command (PowerShell):

```powershell
.\scripts\run_muzero_train.ps1
```

Objective Decision Flow now comes from **eval** metrics (`phase_2_9_eval_kpis`), not from train diagnostics.

- `run_muzero_train.ps1` stays lean by default (diagnostics disabled unless `-EnableDiagnostics` is provided).
- `run_new_muzero_model_and_eval_pack.ps1` remains available for legacy batches.
- `run_many_evals_latest_muzero.ps1` remains available for legacy eval-pack runs.
- Eval runner computes flow diagnostics only for MuZero-controlled turns/sides (skips random-only diagnostics for speed).

Generate many evals for latest MuZero train (recommended to stress Objective Decision Flow):

```powershell
.\scripts\run_many_evals_latest_muzero.ps1 -EvalCount 10 -SeedsPerEval 3 -OpenViewer
```

Train a new model and launch a full eval pack (all-in-one):

```powershell
.\scripts\run_new_muzero_model_and_eval_pack.ps1 -TrainProfile quality -EvalCount 8 -SeedsPerEval 3
```

Train performance mode:

- Base profile files may define `train.enable_post_train_analytics: false` for lean mode.
- Train scripts keep this lean behavior unless diagnostics are explicitly requested.
- Lean mode skips heavy post-train analytics/XAI exports and keeps core train outputs (`checkpoints`, `metrics/summary.json`, `run_manifest.json`).

This script runs three matchup profiles (no `random_selfplay`):

- `muzero_selfplay` (MuZero mirror baseline)
- `muzero_vs_random_side_a` (MuZero vs Random, role A)
- `muzero_vs_random_side_b` (MuZero vs Random, role B)

In model eval detail view, rows now include:

- `matchup_profile`
- `matchup_group`
- `measurement_goal`

## Prefect Run

```powershell
python -m mlops.orchestrator.run --config mlops/configs/experiment_config.yaml --prefect
```

If Prefect is unavailable, execution falls back to local orchestrator mode.

## Curriculum Reporting Catalog (v2)

Build catalog separated by `engine -> model -> train_history/eval_history`:

```powershell
.\scripts\build_curriculum_reporting_catalog.ps1
```

Default output:

- `runs_curriculum/experiments/reporting/model_catalog_latest.json`

## Curriculum Reporting Viewer (Base UI)

Launch local viewer:

```powershell
.\scripts\run_curriculum_reporting_viewer.ps1
```

Open directly in a new browser window/tab:

```powershell
.\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow
```

Dev mode with auto-restart on viewer code changes:

```powershell
.\scripts\run_curriculum_reporting_viewer.ps1 -Dev
```

Then open:

- `http://127.0.0.1:8777/`

Isolation note:

- Curriculum train/eval/reporting scripts write to `runs_curriculum/` by default.
- This isolates the new curriculum viewer pipeline from legacy artifacts under `runs/`.

The base UI shows:

- engine list (EZv2-first ordering when available, then remaining engines)
- model list per engine
- separated tabs:
  - `Train History`
  - `Eval History`
- live refresh without manual page reload:
  - `auto-refresh` toggle
  - interval selector (seconds)
- train navigation and detail panel:
  - `Prev train` / `Next train`
  - selected train detail (engine-specific only, no cross-engine mixing)
- model browser `Open` button:
  - opens `/model?engine=...&model=...` in new window
  - dedicated model page with:
    - common model info
    - multi-scenario summary (`scenarios_seen`, train/eval counts by scenario)
    - scenario filter (`all` or single scenario)
    - train history navigation
    - evals filtered by selected train
    - tabs:
      - `Overview`
      - `VP Summary` (single main table by side with filters + totals row; removed extra secondary tables)

Schema highlights:

- first level: `engines` (includes `efficientzero_v2`, `sb3`, `muzero`, `alpha`)
- second level: `models` grouped by config fingerprint
- separated histories:
  - `train_history` (run, retrain lineage, checkpoint, metrics path, commit)
  - `eval_history` (bench eval snapshots tied to train run and commit)
  - `eval_history.flow_traceability`:
    - `flow_source: "eval"`
    - `flow_contract_version: "phase_2_9_eval_kpis.v1"`
    - availability/fields for Objective Decision Flow diagnostics

## MLflow

Configured in `mlops/configs/experiment_config.yaml` using `execution.mlflow_experiment`.

Logged metrics:

- `promotion_gate_pass`
- `muzero_win_rate`
- `baseline_win_rate`
- `win_rate_delta_vs_baseline`

Logged artifacts:

- stage manifests
- experiment manifest
- comparison summary
- decision report

## Smoke Tests

```powershell
python -m pytest -q mlops/tests/test_contracts.py mlops/tests/test_registry.py mlops/tests/test_orchestrator_smoke.py mlops/tests/test_prefect_flow.py
```
