# Curriculum Repeatability Runbook

## Objective

Run train/eval/publish cycles in a fully repeatable way:
- same declared commands,
- same tracked config files (hash-locked),
- same artifact/log structure per cycle.

Note:
- `publish_command` in manifest is optional.
- Leave it empty/omitted when your train/eval flow already publishes catalog automatically.

## Tooling

- Manifest template: `scripts/curriculum_cycle.template.json`
- Runner: `scripts/run_curriculum_cycle.ps1`

Each execution creates:
- `runs_curriculum/experiments/curriculum_cycles/<timestamp_name>/meta/manifest.lock.json`
- `runs_curriculum/experiments/curriculum_cycles/<timestamp_name>/meta/status.json`
- `runs_curriculum/experiments/curriculum_cycles/<timestamp_name>/logs/01_train.log`
- `runs_curriculum/experiments/curriculum_cycles/<timestamp_name>/logs/02_eval.log`
- `runs_curriculum/experiments/curriculum_cycles/<timestamp_name>/logs/03_publish.log`

## Standard Flow

1) Edit manifest commands and tracked files:
- `scripts/curriculum_cycle.template.json`
- If publish is already automatic in your flow, omit `publish_command`.

2) Dry run (validation only):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_curriculum_cycle.ps1 -ManifestPath .\scripts\curriculum_cycle.template.json -DryRun
```

3) Execute full cycle:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_curriculum_cycle.ps1 -ManifestPath .\scripts\curriculum_cycle.template.json
```

## Repeatability Rules

- Never run ad-hoc train/eval for gated comparisons; use manifest runner.
- Commit manifest changes before execution when possible.
- Keep `tracked_files` aligned to effective train/eval configs.
- Compare cycle-to-cycle only when seed packs and scenario matrix are unchanged.

## Recommended Next Hardening

- Add a fixed `seeds` field in manifest and enforce it via config generation.
- Add automatic gate command (pass/fail JSON) as fourth step.
- Add a `latest` pointer file to the last successful cycle for dashboard tools.
