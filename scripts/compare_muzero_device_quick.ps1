param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BaseConfig = "runs_curriculum/experiments/reporting/tmp_configs/muzero_config.anti_empty.quick_20260706_153850.yaml",
  [string]$RunsRoot = "runs",
  [switch]$CpuOnly,
  [switch]$CudaOnly
)

$ErrorActionPreference = "Stop"

function New-DeviceConfig {
  param(
    [string]$SourcePath,
    [string]$TargetPath,
    [string]$Device,
    [string]$RunsRoot
  )
  $txt = Get-Content -Path $SourcePath -Raw
  $txt = [regex]::Replace($txt, "(?m)^\s*device\s*:\s*.*$", ("  device: " + $Device))
  $txt = [regex]::Replace($txt, "(?m)^\s*run_root\s*:\s*.*$", ("  run_root: " + $RunsRoot))
  Set-Content -Path $TargetPath -Value $txt -Encoding UTF8
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }
  $env:OMP_NUM_THREADS = "1"
  $env:MKL_NUM_THREADS = "1"
  $env:NUMEXPR_NUM_THREADS = "1"
  $env:OPENBLAS_NUM_THREADS = "1"
  $env:PYTORCH_CUDA_ALLOC_CONF = "expandable_segments:True"

  $basePath = Join-Path $Repo $BaseConfig
  if (-not (Test-Path $basePath)) {
    throw "Base config not found: $basePath"
  }

  $tmpDir = Join-Path $Repo "runs_curriculum\experiments\reporting\tmp_configs"
  if (-not (Test-Path $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  }

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $cpuCfg = Join-Path $tmpDir ("muzero_config.compare_cpu_{0}.yaml" -f $stamp)
  $cudaCfg = Join-Path $tmpDir ("muzero_config.compare_cuda_{0}.yaml" -f $stamp)
  New-DeviceConfig -SourcePath $basePath -TargetPath $cpuCfg -Device "cpu" -RunsRoot $RunsRoot
  New-DeviceConfig -SourcePath $basePath -TargetPath $cudaCfg -Device "cuda" -RunsRoot $RunsRoot

  $results = @()
  $targets = @()
  if (-not $CudaOnly) { $targets += @{ name = "cpu"; cfg = $cpuCfg } }
  if (-not $CpuOnly) { $targets += @{ name = "cuda"; cfg = $cudaCfg } }

  foreach ($t in $targets) {
    $dev = [string]$t.name
    $cfg = [string]$t.cfg
    Write-Host ""
    Write-Host ("== Running {0} ==" -f $dev)
    Write-Host ("Config: {0}" -f $cfg)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    python -m agents.muzero.train.train_muzero --config $cfg --mlflow-experiment assault_muzero --mlflow-run-name ("compare_" + $dev + "_" + $stamp)
    $exitCode = $LASTEXITCODE
    $sw.Stop()
    $results += [PSCustomObject]@{
      device = $dev
      elapsed_s = [Math]::Round($sw.Elapsed.TotalSeconds, 2)
      exit_code = $exitCode
      config = $cfg
    }
  }

  Write-Host ""
  Write-Host "== Compare Summary =="
  $results | Format-Table -AutoSize
}
finally {
  Pop-Location
}

