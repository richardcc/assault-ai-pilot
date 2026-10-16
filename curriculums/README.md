# Curriculums Workspace

This folder stores versioned training curriculums and their configs.

## Recommended Structure

- One folder per curriculum version:
  - `curriculums/<curriculum_name>/curriculum.yaml`
  - `curriculums/<curriculum_name>/configs/*.yaml`
  - `curriculums/<curriculum_name>/cycle.template.json`
  - `curriculums/<curriculum_name>/notes.md` (optional)

## Usage

1. Pick a curriculum folder.
2. Select phase config from `configs/`.
3. Use `cycle.template.json` with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_curriculum_cycle.ps1 -ManifestPath .\curriculums\<name>\cycle.template.json
```

## Convention

- `curriculum.yaml` defines phase order and gates.
- Each phase config must be immutable after execution.
- Create a new curriculum version folder when changing strategy.
