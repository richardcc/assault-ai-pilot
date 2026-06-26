<#
.SYNOPSIS
Runs IT battaglia trainer sweep (A/B/C), then eval, gate and summary.

.DESCRIPTION
Creates isolated runtime train configs per variant (A/B/C), launches training in parallel,
collects logs, evaluates successful variants, runs gate decisions, and writes decision summary/history.

.PARAMETER RepoPath
Repository root path.

.PARAMETER Episodes
Episodes per eval run in comparative stage.

.PARAMETER Seed
Seed used in eval stage.

.PARAMETER EvalParallel
Max parallel eval jobs in comparative stage.

.PARAMETER AbortOnTrainFailure
If set, aborts before eval when any training job fails.

.PARAMETER FailIfNoGo
If set, exits with code 1 when final summary reports promotion_allowed=no.

.EXAMPLE
.\scripts\run_trainer_sweep_it_battaglia.ps1

.EXAMPLE
.\scripts\run_trainer_sweep_it_battaglia.ps1 -FailIfNoGo -AbortOnTrainFailure
#>
[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int]$Episodes = 20,
  [int]$Seed = 42,
  [int]$EvalParallel = 3,
  [switch]$AbortOnTrainFailure,
  [switch]$FailIfNoGo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$baseCfgA = Join-Path $RepoPath "assault_sim\session\tmp_parallel\train_config_battaglia_cittadina_2_1_it.trainer_sweep_A.json"
$baseCfgB = Join-Path $RepoPath "assault_sim\session\tmp_parallel\train_config_battaglia_cittadina_2_1_it.trainer_sweep_B.json"
$baseCfgC = Join-Path $RepoPath "assault_sim\session\tmp_parallel\train_config_battaglia_cittadina_2_1_it.trainer_sweep_C.json"

$configs = @($baseCfgA, $baseCfgB, $baseCfgC)
foreach ($cfg in $configs) {
  if (-not (Test-Path -Path $cfg -PathType Leaf)) {
    throw "Config no encontrada: $cfg"
  }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outRoot = Join-Path $RepoPath ("assault_sim\session\reports\sb3_eval\trainer_sweep_it_battaglia_{0}" -f $timestamp)
New-Item -ItemType Directory -Path $outRoot -Force | Out-Null
$logsDir = Join-Path $outRoot "train_logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
$runCfgDir = Join-Path $outRoot "run_configs"
New-Item -ItemType Directory -Path $runCfgDir -Force | Out-Null

function New-IsolatedConfig {
  param(
    [string]$SourceConfig,
    [string]$TargetConfig,
    [string]$ModelsSubdir
  )
  $cfg = Get-Content -Path $SourceConfig -Raw | ConvertFrom-Json
  # Force unique workspace per sweep variant to avoid cleanup/write collisions.
  $cfg.sb3_models_subdir = $ModelsSubdir
  $cfg.sb3_models_subdir_template = ""
  [System.IO.File]::WriteAllText(
    $TargetConfig,
    ($cfg | ConvertTo-Json -Depth 50),
    (New-Object System.Text.UTF8Encoding($false))
  )
}

$cfgA = Join-Path $runCfgDir "train_config_it_sweep_A.run.json"
$cfgB = Join-Path $runCfgDir "train_config_it_sweep_B.run.json"
$cfgC = Join-Path $runCfgDir "train_config_it_sweep_C.run.json"
New-IsolatedConfig -SourceConfig $baseCfgA -TargetConfig $cfgA -ModelsSubdir ("trainer_sweep\{0}\A" -f $timestamp)
New-IsolatedConfig -SourceConfig $baseCfgB -TargetConfig $cfgB -ModelsSubdir ("trainer_sweep\{0}\B" -f $timestamp)
New-IsolatedConfig -SourceConfig $baseCfgC -TargetConfig $cfgC -ModelsSubdir ("trainer_sweep\{0}\C" -f $timestamp)

Write-Host ("Out root: {0}" -f $outRoot)
Write-Host "Starting parallel training jobs..."

$jobs = @(
  Start-Job -Name "train_it_sweep_A" -ScriptBlock {
    param($repo, $cfg, $logPath)
    Set-Location $repo
    & ".\.venv\Scripts\python.exe" -m assault_sim.train.train_sb3 --config $cfg 2>&1 | Tee-Object -FilePath $logPath
    [pscustomobject]@{ config = $cfg; exit_code = $LASTEXITCODE; log_path = $logPath }
  } -ArgumentList $RepoPath, $cfgA, (Join-Path $logsDir "train_A.log")

  Start-Job -Name "train_it_sweep_B" -ScriptBlock {
    param($repo, $cfg, $logPath)
    Set-Location $repo
    & ".\.venv\Scripts\python.exe" -m assault_sim.train.train_sb3 --config $cfg 2>&1 | Tee-Object -FilePath $logPath
    [pscustomobject]@{ config = $cfg; exit_code = $LASTEXITCODE; log_path = $logPath }
  } -ArgumentList $RepoPath, $cfgB, (Join-Path $logsDir "train_B.log")

  Start-Job -Name "train_it_sweep_C" -ScriptBlock {
    param($repo, $cfg, $logPath)
    Set-Location $repo
    & ".\.venv\Scripts\python.exe" -m assault_sim.train.train_sb3 --config $cfg 2>&1 | Tee-Object -FilePath $logPath
    [pscustomobject]@{ config = $cfg; exit_code = $LASTEXITCODE; log_path = $logPath }
  } -ArgumentList $RepoPath, $cfgC, (Join-Path $logsDir "train_C.log")
)

Write-Host "Waiting training jobs..."
$null = $jobs | Wait-Job

$trainFailed = $false
$successfulConfigs = New-Object System.Collections.Generic.List[string]
foreach ($job in $jobs) {
  $output = Receive-Job -Job $job
  $meta = @($output | Where-Object { $_ -is [pscustomobject] -and $_.PSObject.Properties.Name -contains "exit_code" } | Select-Object -Last 1)
  if ($meta.Count -lt 1) {
    Write-Warning ("{0}: no exit metadata found." -f $job.Name)
    $trainFailed = $true
    continue
  }
  $exitCode = [int]$meta[0].exit_code
  $logPath = [string]$meta[0].log_path
  if ($exitCode -ne 0) {
    Write-Warning ("{0}: FAILED (exit={1}) config={2}" -f $job.Name, $exitCode, [string]$meta[0].config)
    if (Test-Path -Path $logPath -PathType Leaf) {
      Write-Host ("--- tail {0} ---" -f $logPath)
      Get-Content -Path $logPath -Tail 30
      Write-Host ("--- end tail {0} ---" -f $logPath)
    }
    $trainFailed = $true
  } else {
    Write-Host ("{0}: OK" -f $job.Name)
    $successfulConfigs.Add([string]$meta[0].config) | Out-Null
  }
}

$jobs | Remove-Job -Force -ErrorAction SilentlyContinue | Out-Null

if ($trainFailed -and $AbortOnTrainFailure) {
  throw "At least one training job failed. Aborting eval stage."
}
if ($successfulConfigs.Count -lt 1) {
  throw "No successful training jobs. Cannot run eval stage."
}

Write-Host ("Running comparative eval for successful configs ({0})..." -f $successfulConfigs.Count)
$evalScript = Join-Path $RepoPath "scripts\run_eval_parallel_configs.ps1"
if (-not (Test-Path -Path $evalScript -PathType Leaf)) {
  throw "Eval script not found: $evalScript"
}

$evalParams = @{
  RepoPath = $RepoPath
  Configs = @($successfulConfigs.ToArray())
  Episodes = $Episodes
  Seed = $Seed
  MaxParallel = $EvalParallel
  OutRoot = $outRoot
}
& $evalScript @evalParams

Write-Host ""
Write-Host ("Sweep finished. Reports in: {0}" -f $outRoot)

$gateScript = Join-Path $RepoPath "scripts\check_trainer_sweep_gate.ps1"
$comparativeCsv = Join-Path $outRoot "comparative_summary.csv"
if ((Test-Path -Path $gateScript -PathType Leaf) -and (Test-Path -Path $comparativeCsv -PathType Leaf)) {
  Write-Host ""
  Write-Host "Running gate decision script..."
  & powershell -NoProfile -ExecutionPolicy Bypass -File $gateScript -ComparativeCsv $comparativeCsv
  $gateExitCode = $LASTEXITCODE
  $gateCsv = Join-Path $outRoot "trainer_sweep_gate_decision.csv"
  $summaryScript = Join-Path $RepoPath "scripts\build_trainer_sweep_summary.ps1"
  if ((Test-Path -Path $summaryScript -PathType Leaf) -and (Test-Path -Path $gateCsv -PathType Leaf)) {
    Write-Host "Building markdown summary + history..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $summaryScript -GateCsv $gateCsv
    $summaryPath = Join-Path $outRoot "decision_summary.md"
    if ($FailIfNoGo -and (Test-Path -Path $summaryPath -PathType Leaf)) {
      $summaryRaw = Get-Content -Path $summaryPath -Raw
      if ($summaryRaw -match "Promotion allowed:\s*\*\*no\*\*") {
        Write-Error "FailIfNoGo active: promotion_allowed=no (NO-GO global)."
        exit 1
      }
    } elseif ($FailIfNoGo -and $gateExitCode -ne 0) {
      Write-Error "FailIfNoGo active: gate script returned non-zero."
      exit 1
    }
  }
}
