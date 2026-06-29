[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int[]]$Seeds = @(42),
  [int]$Episodes = 10,
  [int]$MinReactionFireCount = 0,
  [switch]$ForceDeterministicFallback,
  [switch]$SkipEval
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Write-Host "[$ts] $Message"
}

function Run-Cmd {
  param(
    [string]$Title,
    [string[]]$Command
  )
  Write-Step "==== $Title ===="
  Write-Host ("CMD: " + ($Command -join " "))
  & $Command[0] $Command[1..($Command.Length - 1)]
  if ($LASTEXITCODE -ne 0) {
    throw "Failed: $Title (exit=$LASTEXITCODE)"
  }
}

if (-not (Test-Path -LiteralPath $RepoPath)) {
  throw "Repo path not found: $RepoPath"
}

Push-Location $RepoPath
try {
  # 1) Runtime contract tests (deterministic)
  Run-Cmd -Title "Pytest runtime reaction-fire contracts" -Command @(
    "pytest",
    "assault_model/tests/test_runtime_reaction_fire_flag.py",
    "-k",
    "human_reaction_creates_pending_window or resolve_pending_reaction_use_and_skip"
  )

  if ($SkipEval) {
    Write-Step "SkipEval enabled. Stopping after runtime tests."
    exit 0
  }

  # 2) Eval smoke with reaction fire ON
  $env:ASSAULT_ENABLE_REACTION_FIRE = "1"
  Write-Step ("Eval seeds: " + (($Seeds | ForEach-Object { [string]$_ }) -join ","))
  $evalArgs = @{
    RepoPath = $RepoPath
    SkipTrain = $true
    Seeds = $Seeds
    Episodes = $Episodes
  }
  Write-Step "==== Eval smoke with reaction fire enabled ===="
  & ".\run_train_eval.ps1" @evalArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Failed: Eval smoke with reaction fire enabled (exit=$LASTEXITCODE)"
  }

  # 3) Validate metrics presence in latest report
  $reportsDir = Join-Path $RepoPath "assault_sim\session\reports\sb3_eval"
  if (-not (Test-Path -LiteralPath $reportsDir)) {
    throw "Reports dir not found: $reportsDir"
  }

  $latestReport = Get-ChildItem -Path $reportsDir -Filter "metrics_sb3_report_*.json" -Recurse |
    Sort-Object LastWriteTimeUtc |
    Select-Object -Last 1

  if (-not $latestReport) {
    throw "No metrics_sb3_report_*.json found under: $reportsDir"
  }

  Write-Step ("Latest report: " + $latestReport.FullName)
  $json = Get-Content -LiteralPath $latestReport.FullName -Raw | ConvertFrom-Json
  $foundMission = $false
  $rows = @()

  foreach ($sideProp in ($json.by_side_and_scenario.PSObject.Properties | ForEach-Object { $_ })) {
    $sideName = [string]$sideProp.Name
    $scenarios = $sideProp.Value
    foreach ($scenarioProp in ($scenarios.PSObject.Properties | ForEach-Object { $_ })) {
      $scenarioName = [string]$scenarioProp.Name
      $payload = $scenarioProp.Value
      $mission = $payload.mission
      if ($null -ne $mission) {
        $foundMission = $true
        $rfCount = [int]($mission.reaction_fire_count | ForEach-Object { $_ })
        $rfRate = [double]($mission.reaction_fire_rate | ForEach-Object { $_ })
        $rfBySide = $mission.reaction_fire_by_side
        $rows += [pscustomobject]@{
          side = $sideName
          scenario = $scenarioName
          reaction_fire_count = $rfCount
          reaction_fire_rate = $rfRate
          reaction_fire_by_side = ($rfBySide | ConvertTo-Json -Compress)
        }
      }
    }
  }

  if (-not $foundMission) {
    throw "Mission block not found in report: $($latestReport.FullName)"
  }

  Write-Step "Reaction fire metrics found in report:"
  $rows | Format-Table -AutoSize | Out-String | Write-Host

  $totalReactionFire = ($rows | Measure-Object -Property reaction_fire_count -Sum).Sum
  if ($null -eq $totalReactionFire) {
    $totalReactionFire = 0
  }
  $totalReactionFire = [int]$totalReactionFire
  Write-Step ("Total reaction_fire_count across rows: " + $totalReactionFire)
  $thresholdMetByFallback = $false

  if ($totalReactionFire -lt $MinReactionFireCount) {
    if ($ForceDeterministicFallback) {
      Write-Step "Threshold not met in eval. Running deterministic forced smoke fallback..."
      Run-Cmd -Title "Forced deterministic reaction-fire smoke" -Command @(
        "python",
        ".\scripts\force_reaction_fire_smoke.py"
      )
      Write-Step "Forced deterministic fallback passed. (Eval remained below threshold.)"
      $thresholdMetByFallback = $true
    } else {
      throw "Reaction fire threshold NOT met: got=$totalReactionFire expected>=$MinReactionFireCount"
    }
  }

  if ($MinReactionFireCount -gt 0) {
    if ($thresholdMetByFallback) {
      Write-Step ("Reaction fire threshold satisfied via fallback: eval_got=$totalReactionFire expected>=$MinReactionFireCount forced_smoke=pass")
    } else {
      Write-Step ("Reaction fire threshold met in eval: got=$totalReactionFire expected>=$MinReactionFireCount")
    }
  }

  Write-Step "Done."
}
finally {
  Pop-Location
}

