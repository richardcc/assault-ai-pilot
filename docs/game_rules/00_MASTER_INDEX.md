# ASSAULT - EXHAUSTIVE RULES DOCUMENTATION

This folder organizes product rules in a hierarchical structure, using
the PDFs in `docs/pdfs/` as canonical source.

## Hierarchy

- `01_CORE_RULEBOOK_V2.md`
- `02_TURN_SEQUENCE_AND_ACTIONS.md`
- `03_MOVEMENT_AND_TERRAIN.md`
- `04_LOS_SPOTTING_AND_RANGED_FIRE.md`
- `05_CLOSE_COMBAT_AND_CRITICALS.md`
- `06_TAS_OAS_AND_TERRAIN_DAMAGE.md`
- `07_GELA_CAMPAIGN.md`
- `08_OPTIONAL_FOW_RULES.md`
- `annexes/A_GLOSSARY.md`
- `annexes/B_PDF_TRACEABILITY.md`
- `annexes/C_DICE_MODIFIER_VALIDATION_TABLES.md`

## Precedence Rule

1. PDFs in `docs/pdfs/` are the source of truth.
2. These markdown files are operational consolidations.
3. If there is any conflict, the PDF prevails.

## Simulation Training Operational Note

Validation state: **Pending Validation**.

- `assault_sim/train/train_sb3.py` now cleans transient artifacts under `models/` at run start to avoid cross-run contamination (`sb3_latest_*`, `sb3_vecnormalize_*`, `sb3_best_*`, `sb3_eval_*`, `models/runs/`).
- This does not define game rules; it is a reproducibility guardrail for RL train/eval workflow.
- `run_train_eval.ps1` supports configurable parallel eval by seed (`-ParallelEvalSeeds`, `-EvalParallelJobs`) with isolated output folders per seed.
