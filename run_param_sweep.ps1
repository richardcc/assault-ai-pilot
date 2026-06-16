[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int]$MaxRuns = 12,
  [int]$Episodes = 30,
  [int[]]$Seeds = @(42, 43, 44),
  [int]$EvalParallelJobs = 2,
  [int]$SleepBetweenRunsSec = 3,
  [string]$OutRoot = "",
  [switch]$RandomSearch,
  [int]$RandomSeed = 42
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
  param([string]$Message)
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Write-Host "[$ts] $Message"
}

function Get-ParamGrid {
  # Conservative sweep ranges (single-machine safe).
  return @{
    sb3_batch_size = @(256, 384, 512)
    sb3_n_steps    = @(768, 1024, 1536)
    sb3_n_epochs   = @(8, 10)
    sb3_ent_coef   = @(0.006, 0.008, 0.010)
  }
}

function Get-Combos {
  param(
    [hashtable]$Grid,
    [switch]$RandomMode,
    [int]$Limit,
    [int]$Seed
  )
  $all = @()
  foreach ($batch in $Grid.sb3_batch_size) {
    foreach ($steps in $Grid.sb3_n_steps) {
      foreach ($epochs in $Grid.sb3_n_epochs) {
        foreach ($ent in $Grid.sb3_ent_coef) {
          $all += [pscustomobject]@{
            sb3_batch_size = $batch
            sb3_n_steps    = $steps
            sb3_n_epochs   = $epochs
            sb3_ent_coef   = $ent
          }
        }
      }
    }
  }
  if ($RandomMode) {
    $rng = [System.Random]::new($Seed)
    $all = $all | Sort-Object { $rng.Next() }
  }
  return @($all | Select-Object -First $Limit)
}

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath no existe: $RepoPath"
}

$cfgPath = Join-Path $RepoPath "assault_sim\config\train_config.json"
if (-not (Test-Path $cfgPath)) {
  throw "No se encontró train_config.json en: $cfgPath"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ([string]::IsNullOrWhiteSpace($OutRoot)) {
  $OutRoot = Join-Path $RepoPath ("assault_sim\session\reports\sb3_eval\sweep_{0}" -f $stamp)
}
New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null
$summaryCsv = Join-Path $OutRoot "sweep_summary.csv"

$originalConfigText = Get-Content -Path $cfgPath -Raw
$grid = Get-ParamGrid
$combos = Get-Combos -Grid $grid -RandomMode:$RandomSearch -Limit $MaxRuns -Seed $RandomSeed

Write-Log ("Sweep start -> runs={0} out={1}" -f $combos.Count, $OutRoot)
Write-Log ("Seeds={0} Episodes={1} ParallelEvalJobs={2}" -f ($Seeds -join ","), $Episodes, $EvalParallelJobs)

$rows = [System.Collections.Generic.List[object]]::new()

try {
  $runIndex = 0
  foreach ($combo in $combos) {
    $runIndex += 1
    $entStr = ([double]$combo.sb3_ent_coef).ToString([System.Globalization.CultureInfo]::InvariantCulture)
    $runId = "r{0:D2}_bs{1}_ns{2}_ep{3}_ent{4}" -f $runIndex, $combo.sb3_batch_size, $combo.sb3_n_steps, $combo.sb3_n_epochs, ($entStr.Replace(".", "p"))
    $runOut = Join-Path $OutRoot $runId

    # Rebuild from original config each time (single-palanca bundle for PPO only).
    $cfgObj = ($originalConfigText | ConvertFrom-Json)
    $cfgObj.sb3_vec_env_type = "dummy"
    $cfgObj.sb3_num_envs = 12
    $cfgObj.sb3_train_lean = $false
    $cfgObj.sb3_batch_size = [int]$combo.sb3_batch_size
    $cfgObj.sb3_n_steps = [int]$combo.sb3_n_steps
    $cfgObj.sb3_n_epochs = [int]$combo.sb3_n_epochs
    $cfgObj.sb3_ent_coef = [double]$combo.sb3_ent_coef
    ($cfgObj | ConvertTo-Json -Depth 12) | Set-Content -Path $cfgPath

    Write-Log ("[{0}/{1}] RUN {2}" -f $runIndex, $combos.Count, $runId)
    Write-Log ("Config: batch={0} n_steps={1} n_epochs={2} ent_coef={3}" -f $combo.sb3_batch_size, $combo.sb3_n_steps, $combo.sb3_n_epochs, $combo.sb3_ent_coef)

    & (Join-Path $RepoPath "run_train_eval.ps1") `
      -RepoPath $RepoPath `
      -Seeds $Seeds `
      -Episodes $Episodes `
      -OutDir $runOut `
      -ParallelEvalSeeds `
      -EvalParallelJobs $EvalParallelJobs `
      -AutoGateAndPromoteBaseline
    if ($LASTEXITCODE -ne 0) {
      Write-Log ("Run failed exit={0}: {1}" -f $LASTEXITCODE, $runId)
    }

    $decisionPath = Join-Path $runOut "gate_decision.json"
    $decision = $null
    $trueWin = $null
    $loss = $null
    $capt45 = $null
    if (Test-Path $decisionPath) {
      $g = Get-Content -Path $decisionPath -Raw | ConvertFrom-Json
      $decision = [string]$g.decision
      $trueWin = [double]$g.metrics.true_win_rate
      $loss = [double]$g.metrics.loss_rate
      $capt45 = [int]$g.metrics.captured_4_5_episodes
      Write-Log ("Decision={0} true_win={1:N3} loss={2:N3} captured45={3}" -f $decision, $trueWin, $loss, $capt45)
    } else {
      Write-Log "Decision file missing (run likely failed before gate)."
    }

    $rows.Add([pscustomobject]@{
      run_id = $runId
      out_dir = $runOut
      decision = $decision
      true_win_rate = $trueWin
      loss_rate = $loss
      captured_4_5_episodes = $capt45
      sb3_batch_size = $combo.sb3_batch_size
      sb3_n_steps = $combo.sb3_n_steps
      sb3_n_epochs = $combo.sb3_n_epochs
      sb3_ent_coef = $combo.sb3_ent_coef
    }) | Out-Null

    Start-Sleep -Seconds $SleepBetweenRunsSec
  }
}
finally {
  # Restore original config at the end of sweep.
  Set-Content -Path $cfgPath -Value $originalConfigText
  Write-Log "train_config.json restored to original state."
}

if ($rows.Count -gt 0) {
  $rows | Export-Csv -Path $summaryCsv -NoTypeInformation
  Write-Log ("Sweep summary saved: {0}" -f $summaryCsv)
  $best = $rows |
    Where-Object { $_.decision -eq "GO" } |
    Sort-Object -Property @{Expression = "true_win_rate"; Descending = $true}, @{Expression = "loss_rate"; Descending = $false} |
    Select-Object -First 1
  if ($best) {
    Write-Log ("Best GO run: {0} (true_win={1:N3}, loss={2:N3})" -f $best.run_id, $best.true_win_rate, $best.loss_rate)
  } else {
    Write-Log "No GO runs found in this sweep."
  }
}

Write-Log "Sweep complete."
