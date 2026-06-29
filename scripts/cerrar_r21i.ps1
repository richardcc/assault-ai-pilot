param(
  [string]$Repo = "C:\repos\python\assault",
  [int[]]$Seeds = @(42, 43, 44),
  [int]$Episodes = 10,
  [string]$Side = "US",
  [string]$Scenario = "battaglia_cittadina_2_1",
  [string]$CaptureMetric = "capture_conversion_after_contact",
  [ValidateSet("strict", "majority", "mean")]
  [string]$PassPolicy = "majority",
  [double]$MinCaptureAttemptSuccessRate = 0.0000001,
  [double]$MaxLossRate = 0.8,
  [double]$MinVpEntryConversionRate = 0.30
)

$ErrorActionPreference = "Stop"

$runner = Join-Path $Repo "scripts\run_r21e_us_gate.ps1"
if (-not (Test-Path -Path $runner -PathType Leaf)) {
  throw "No existe runner base: $runner"
}

$reportDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$decisionJson = Join-Path $reportDir ("r21i_closeout_" + $stamp + ".json")
$decisionMd = Join-Path $reportDir ("r21i_closeout_" + $stamp + ".md")

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  & $runner `
    -Repo $Repo `
    -Seeds $Seeds `
    -Episodes $Episodes `
    -Side $Side `
    -Scenario $Scenario `
    -CaptureMetric $CaptureMetric `
    -PassPolicy $PassPolicy `
    -MinCaptureAttemptSuccessRate $MinCaptureAttemptSuccessRate `
    -MaxLossRate $MaxLossRate `
    -MinVpEntryConversionRate $MinVpEntryConversionRate

  $exitCode = $LASTEXITCODE
  $decision = if ($exitCode -eq 0) { "GO" } else { "NO-GO" }

  $payload = [pscustomobject]@{
    cycle = "R2.1-i"
    timestamp_utc = $stamp
    decision = $decision
    pass_policy = $PassPolicy
    seeds = $Seeds
    episodes = $Episodes
    side = $Side
    scenario = $Scenario
    capture_metric = $CaptureMetric
    thresholds = [pscustomobject]@{
      min_capture_attempt_success_rate = $MinCaptureAttemptSuccessRate
      max_loss_rate = $MaxLossRate
      min_vp_entry_conversion_rate = $MinVpEntryConversionRate
    }
  }

  $json = $payload | ConvertTo-Json -Depth 10
  [System.IO.File]::WriteAllText($decisionJson, $json, (New-Object System.Text.UTF8Encoding($false)))

  $md = @(
    "# R2.1-i closeout",
    "",
    "- timestamp_utc: $stamp",
    "- decision: $decision",
    "- pass_policy: $PassPolicy",
    "- seeds: $($Seeds -join ', ')",
    "- episodes: $Episodes",
    "- side: $Side",
    "- scenario: $Scenario",
    "- capture_metric: $CaptureMetric",
    "- thresholds: capture>$MinCaptureAttemptSuccessRate, loss<$MaxLossRate, vp_conv>=$MinVpEntryConversionRate",
    "",
    "Artifacts:",
    "- $decisionJson"
  ) -join "`n"
  [System.IO.File]::WriteAllText($decisionMd, $md, (New-Object System.Text.UTF8Encoding($false)))

  Write-Host ""
  Write-Host "R2.1-i closeout: $decision" -ForegroundColor Cyan
  Write-Host "Decision JSON: $decisionJson"
  Write-Host "Decision MD:   $decisionMd"

  if ($exitCode -ne 0) {
    exit 1
  }
  exit 0
}
finally {
  Pop-Location
}
