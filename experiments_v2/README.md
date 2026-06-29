# Experiments V2 (Reset from scratch)

This is a clean replacement for the previous experiment queue.

## Stack

- Orchestration/runtime: Python worker (`scripts/exp_v2_worker.py`)
- Tracking: MLflow (local file backend)
- Manifest format: YAML (`experiments_v2/queue/*.yaml`)

## Folder layout

- `experiments_v2/queue/` - pending manifests
- `experiments_v2/archive/passed/` - successful manifests
- `experiments_v2/archive/failed/` - failed manifests
- `experiments_v2/runs/` - per-run logs and metadata

## Manifest example

See: `experiments_v2/queue/example_reward_stepin.yaml`

## Run

```powershell
python .\scripts\exp_v2_worker.py --once
python .\scripts\exp_v2_worker.py
```

## Status

```powershell
python .\scripts\exp_v2_status.py
```

## Notes

- This V2 flow does not attempt backward compatibility with old manifests/scripts.
- Allowed auto-apply targets are intentionally strict:
  - `assault_sim/config/reward_config.json`
  - `assault_sim/config/train_config.json`
