# Internal Docs Changelog

Validation state: **Pending Validation**.

## 2026-07-03

- Added structured internal docs layout:
  - `mlops/internal_docs/01_architecture/`
  - `mlops/internal_docs/02_operations/`
  - `mlops/internal_docs/03_roadmap/`
- Added section-level README files for each area.
- Added this changelog to track documentation evolution.
- Removed prior top-level legacy files:
  - `mlops/internal_docs/ARCHITECTURE.md`
  - `mlops/internal_docs/OPERATIONS.md`
  - `mlops/internal_docs/ROADMAP.md`
- Added `scripts/run_muzero_train.ps1` for direct MuZero training with optional MLflow run naming.
- Updated operations guide with direct MuZero training commands.
- Added reporting v2 catalog builder:
  - `mlops/reporting/build_catalog.py`
  - `scripts/build_curriculum_reporting_catalog.ps1`
- Reporting v2 now separates `engine/model` identity from `train_history` and `eval_history`, with MLflow commit linkage when available.
- Added base graphical viewer for curriculum reporting:
  - `mlops/reporting/viewer.py`
  - `scripts/run_curriculum_reporting_viewer.ps1`
- Upgraded viewer first UX pass:
  - open in new window option (`-OpenWindow`)
  - selected-train navigation (`Prev`/`Next`)
  - strict engine isolation (no cross-engine train/eval mixing)
