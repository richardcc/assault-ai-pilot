param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BenchConfig = "assault_bench/configs/benchmark_config.dev.yaml",
  [Parameter(Mandatory = $true)]
  [string]$CandidateCheckpoint,
  [string]$CandidateModelConfig = "agents/efficientzero_v2/configs/efficientzero_v2_config.min_valid.yaml",
  [string]$BaselineCheckpoint = "",
  [string]$BaselineModelConfig = "agents/muzero/configs/muzero_config.dev.yaml",
  [int[]]$Seeds = @(41, 42, 43, 44, 45),
  [int]$MinSeeds = 5,
  [double]$MinCaptureImprovementRatio = 0.15,
  [double]$RuntimeRatioLimit = 1.40,
  [string]$RunsRoot = "runs"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  if (-not (Test-Path $BenchConfig)) {
    throw "Bench config not found: $BenchConfig"
  }
  if (-not (Test-Path $CandidateCheckpoint)) {
    throw "Candidate checkpoint not found: $CandidateCheckpoint"
  }
  if ([int]$Seeds.Count -lt [int]$MinSeeds) {
    throw "Need at least $MinSeeds seeds, got $($Seeds.Count)"
  }

  if (-not $BaselineCheckpoint) {
    $latestBase = Get-ChildItem -Path (Join-Path $Repo $RunsRoot) -Recurse -File -Filter "iter_*.pt" |
      Where-Object { $_.FullName -match "\\muzero_.*\\checkpoints\\" } |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if ($null -eq $latestBase) {
      throw "Could not auto-resolve baseline checkpoint under $RunsRoot\muzero_*"
    }
    $BaselineCheckpoint = $latestBase.FullName
  }
  if (-not (Test-Path $BaselineCheckpoint)) {
    throw "Baseline checkpoint not found: $BaselineCheckpoint"
  }

  $tmpDir = Join-Path $Repo "runs\experiments\reporting\tmp_configs"
  New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $seedCsv = ($Seeds -join ", ")
  $benchCfgTmp = Join-Path $tmpDir ("benchmark.ez_gate_{0}.yaml" -f $stamp)
  $candidateJson = Join-Path $tmpDir ("benchmark.ez_candidate_{0}.json" -f $stamp)
  $baselineJson = Join-Path $tmpDir ("benchmark.ez_baseline_{0}.json" -f $stamp)
  $gateOut = Join-Path $tmpDir ("efficientzero_v2_promotion_gate_{0}.json" -f $stamp)

  $cfgText = Get-Content -Path $BenchConfig -Raw
  if ($cfgText -match "(?m)^\s*seeds\s*:\s*\[.*\]\s*$") {
    $cfgText = [regex]::Replace($cfgText, "(?m)^\s*seeds\s*:\s*\[.*\]\s*$", ("  seeds: [" + $seedCsv + "]"))
  } else {
    $cfgText += [Environment]::NewLine + "benchmark:" + [Environment]::NewLine + ("  seeds: [" + $seedCsv + "]")
  }
  Set-Content -Path $benchCfgTmp -Value $cfgText -Encoding UTF8

  Write-Host "== EZ Candidate benchmark =="
  python -m assault_bench.runner --config $benchCfgTmp --checkpoint $CandidateCheckpoint --muzero-config $CandidateModelConfig --mlflow-experiment assault_bench --mlflow-run-name ("ez_gate_candidate_" + $stamp)
  if ($LASTEXITCODE -ne 0) {
    throw "Candidate benchmark failed with exit code $LASTEXITCODE"
  }
  Copy-Item -Path (Join-Path $Repo "$RunsRoot\bench_latest.json") -Destination $candidateJson -Force

  Write-Host "== Baseline benchmark =="
  python -m assault_bench.runner --config $benchCfgTmp --checkpoint $BaselineCheckpoint --muzero-config $BaselineModelConfig --mlflow-experiment assault_bench --mlflow-run-name ("ez_gate_baseline_" + $stamp)
  if ($LASTEXITCODE -ne 0) {
    throw "Baseline benchmark failed with exit code $LASTEXITCODE"
  }
  Copy-Item -Path (Join-Path $Repo "$RunsRoot\bench_latest.json") -Destination $baselineJson -Force

  Write-Host "== Promotion gate report =="
  python -m mlops.efficientzero_promotion_gate --candidate-json $candidateJson --baseline-json $baselineJson --seed-count $($Seeds.Count) --min-seeds $MinSeeds --min-capture-improvement-ratio $MinCaptureImprovementRatio --runtime-ratio-limit $RuntimeRatioLimit --out $gateOut
  if ($LASTEXITCODE -ne 0) {
    throw "Promotion gate evaluation failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Candidate benchmark: $candidateJson"
  Write-Host "Baseline benchmark: $baselineJson"
  Write-Host "Gate report: $gateOut"
}
finally {
  Pop-Location
}
