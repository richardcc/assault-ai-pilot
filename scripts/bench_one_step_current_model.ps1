param(
    [string]$BaseConfig = "assault_bench/configs/benchmark_config.yaml",
    [string]$TempConfig = "assault_bench/configs/benchmark_config.one_episode.yaml",
    [string]$Profile = "muzero_selfplay",
    [int]$Seed = 1,
    [int]$MaxSteps = 60,
    [switch]$DisableMlflow
)

$ErrorActionPreference = "Stop"

if ($DisableMlflow) {
    $env:ASSAULT_BENCH_DISABLE_MLFLOW = "1"
}

$tmpPy = Join-Path $env:TEMP "bench_one_step_config_gen.py"
@'
import sys
from pathlib import Path
import yaml

base = Path(sys.argv[1])
tmp = Path(sys.argv[2])
profile = str(sys.argv[3])
seed = int(sys.argv[4])
max_steps = int(sys.argv[5])

cfg = yaml.safe_load(base.read_text(encoding="utf-8"))
b = cfg.setdefault("benchmark", {})

b["num_workers"] = 1
b["allow_cuda_parallel"] = False
b["seed_batch_size"] = 1
b["persist_replay_episode_files"] = True
b["matchup_profiles"] = [profile]
b["seeds"] = [seed]
b["max_steps"] = max_steps
b["max_steps_override"] = 0

tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=False), encoding="utf-8")
print(tmp.as_posix())
'@ | Set-Content -Path $tmpPy -Encoding UTF8

python "$tmpPy" "$BaseConfig" "$TempConfig" "$Profile" "$Seed" "$MaxSteps"

python -m assault_bench.runner `
  --config "$TempConfig" `
  --checkpoint latest `
  --mlflow-run-name "one_step_current_model"

