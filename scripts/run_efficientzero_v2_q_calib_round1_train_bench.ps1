param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BenchConfig = "assault_bench/configs/benchmark_config.yaml",
  [string]$MlflowTrainExperiment = "assault_efficientzero_v2",
  [string]$MlflowBenchExperiment = "assault_bench",
  [int]$BenchWorkers = 1,
  [int]$BenchMaxSteps = 80,
  [int[]]$BenchSeeds = @(41, 42, 43),
  [string[]]$Configs = @(
    "agents/efficientzero_v2/configs/efficientzero_v2_config.q_calib_c.yaml",
    "agents/efficientzero_v2/configs/efficientzero_v2_config.q_calib_d.yaml",
    "agents/efficientzero_v2/configs/efficientzero_v2_config.q_calib_e.yaml"
  )
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $runsRoot = Join-Path $Repo "runs"
  $cmpDir = Join-Path $runsRoot ("bench_compare\q_calib_round1_{0}" -f $stamp)
  $tmpDir = Join-Path $runsRoot "experiments\reporting\tmp_configs"
  New-Item -ItemType Directory -Path $cmpDir -Force | Out-Null
  New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

  $seedCsv = ($BenchSeeds -join ", ")
  $benchCfgTmp = Join-Path $tmpDir ("benchmark.q_calib_round1.{0}.yaml" -f $stamp)
  $benchText = Get-Content -Path (Join-Path $Repo $BenchConfig) -Raw
  $benchText = [regex]::Replace($benchText, "(?m)^\s*num_workers\s*:\s*\d+\s*$", ("  num_workers: " + $BenchWorkers))
  $benchText = [regex]::Replace($benchText, "(?m)^\s*max_steps\s*:\s*\d+\s*$", ("  max_steps: " + $BenchMaxSteps))
  $benchText = [regex]::Replace($benchText, "(?m)^\s*seeds\s*:\s*\[.*\]\s*$", ("  seeds: [" + $seedCsv + "]"))
  Set-Content -Path $benchCfgTmp -Value $benchText -Encoding UTF8

  $summary = @()
  foreach ($cfg in $Configs) {
    $cfgName = [System.IO.Path]::GetFileNameWithoutExtension($cfg)
    $runName = "{0}_{1}" -f $cfgName, $stamp
    Write-Host "== TRAIN ($cfgName) =="
    python -m agents.efficientzero_v2.train.train_efficientzero_v2 `
      --config $cfg `
      --mlflow-experiment $MlflowTrainExperiment `
      --mlflow-run-name $runName
    if ($LASTEXITCODE -ne 0) {
      throw "Train failed for $cfgName with exit code $LASTEXITCODE"
    }

    $latestRun = Get-ChildItem -Path $runsRoot -Directory -Filter "efficientzero_v2_*" |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if ($null -eq $latestRun) {
      throw "No efficientzero_v2_* run directory found under $runsRoot"
    }
    $finalCkpt = Join-Path $latestRun.FullName "checkpoints\final.pt"
    if (-not (Test-Path $finalCkpt)) {
      throw "Final checkpoint not found: $finalCkpt"
    }

    Write-Host "== BENCH ($cfgName) =="
    python -m assault_bench.runner `
      --config $benchCfgTmp `
      --checkpoint $finalCkpt `
      --muzero-config $cfg `
      --mlflow-experiment $MlflowBenchExperiment `
      --mlflow-run-name ("bench_" + $runName)
    if ($LASTEXITCODE -ne 0) {
      throw "Bench failed for $cfgName with exit code $LASTEXITCODE"
    }

    $benchOut = Join-Path $cmpDir ("bench_{0}.json" -f $cfgName)
    Copy-Item -Path "runs\bench_latest.json" -Destination $benchOut -Force
    $row = (Get-Content -Path $benchOut -Raw | ConvertFrom-Json).results[0]
    $summary += [ordered]@{
      profile = $cfgName
      config = $cfg
      run_id = $latestRun.Name
      checkpoint = $finalCkpt
      bench_json = $benchOut
      timeout_rate = [double]$row.timeout_rate
      tracked_captured_avg = [double]$row.tracked_captured_avg
      xai_vp_capture_take_rate = [double]$row.xai_vp_capture_take_rate
    }
  }

  $summaryPath = Join-Path $cmpDir "summary.json"
  ($summary | ConvertTo-Json -Depth 8) | Set-Content -Path $summaryPath -Encoding UTF8
  Write-Host ""
  Write-Host "Round summary: $summaryPath"
  Write-Host ($summary | ConvertTo-Json -Depth 8)
}
finally {
  Pop-Location
}
