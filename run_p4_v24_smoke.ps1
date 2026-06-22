# run_p4_v24_smoke.ps1
param(
    [string]$OutDir = "C:\repos\python\assault\assault_sim\session\reports\sb3_eval\run_p4_v24_smoke",
    [string]$Seeds = "42,43,44",
    [int]$Episodes = 20,
    [int]$EvalParallelJobs = 3
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$testLog = Join-Path $OutDir "tests.log"
$evalLog = Join-Path $OutDir "eval.log"
$summaryMd = Join-Path $OutDir "p4_v24_smoke_summary.md"

function Run-LoggedCommand {
    param(
        [string]$Exe,
        [string[]]$CmdArgs,
        [string]$LogPath,
        [string]$Label
    )

    Write-Host "[$Label] $Exe $($CmdArgs -join ' ')" -ForegroundColor Cyan
    $null = & $Exe @CmdArgs 2>&1 | Tee-Object -FilePath $LogPath
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host "[$Label] ERROR exit_code=$code. Revisa $LogPath" -ForegroundColor Red
        throw "$Label failed with exit code $code"
    }
}

function Parse-EvalField {
    param(
        [string]$Line,
        [string]$FieldName
    )
    if ([string]::IsNullOrWhiteSpace($Line)) { return $null }
    if ($Line -match "$([regex]::Escape($FieldName))=([0-9]*\.?[0-9]+)") {
        return [double]$matches[1]
    }
    return $null
}

function Last-MetricLine {
    param(
        [string]$LogPath,
        [string]$Prefix
    )
    if (!(Test-Path $LogPath)) { return $null }

    # PowerShell regex-safe literal prefix
    $escaped = [regex]::Escape($Prefix)
    $pattern = "^$escaped"
    $m = Select-String -Path $LogPath -Pattern $pattern | Select-Object -Last 1
    if ($m) { return $m.Line.Trim() }
    return $null
}

Write-Host ""
Write-Host "=== P4 v24 SMOKE START ===" -ForegroundColor Yellow
Write-Host "OutDir: $OutDir"

# 1) Tests críticos P4 tagging
Run-LoggedCommand `
    -Exe "python" `
    -CmdArgs @("-m","pytest","assault_sim/tests/test_option_executor_plan_tags.py","-q") `
    -LogPath $testLog `
    -Label "TEST"

# 2) Eval smoke multi-seed (sin train)
# run_train_eval.ps1 espera Seeds como string CSV
$evalArgs = @(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",".\run_train_eval.ps1",
    "-SkipTrain",
    "-Seeds",$Seeds,
    "-Episodes","$Episodes",
    "-ParallelEvalSeeds",
    "-EvalParallelJobs","$EvalParallelJobs",
    "-OutDir","$OutDir"
)

Run-LoggedCommand `
    -Exe "powershell" `
    -CmdArgs $evalArgs `
    -LogPath $evalLog `
    -Label "EVAL"

# 3) Resumen KPIs
$lineSummary = Last-MetricLine -LogPath $evalLog -Prefix "side=US scenario="
$lineIntent  = Last-MetricLine -LogPath $evalLog -Prefix "intent_commitment_rate_stub:"
$lineRoles   = Last-MetricLine -LogPath $evalLog -Prefix "plan_role_counts_stub:"
$lineInvalid = Last-MetricLine -LogPath $evalLog -Prefix "invalid_action_rate:"
$lineFallback= Last-MetricLine -LogPath $evalLog -Prefix "fallback_rate:"
$lineWaitBk  = Last-MetricLine -LogPath $evalLog -Prefix "wait_recovery_sb3_backstep_rate:"
$lineVpConv  = Last-MetricLine -LogPath $evalLog -Prefix "vp_entry_conversion_rate:"
$lineLoss    = Last-MetricLine -LogPath $evalLog -Prefix "loss_rate:"
$lineTrueWin = Last-MetricLine -LogPath $evalLog -Prefix "interpreted_rates:"

$trueWin = Parse-EvalField -Line $lineSummary -FieldName "true_win_rate(only_wins)"
$lossRate = Parse-EvalField -Line $lineSummary -FieldName "loss_rate"

$vpConv = $null
if ($lineVpConv -match "vp_entry_conversion_rate:\s*([0-9]*\.?[0-9]+)") { $vpConv = [double]$matches[1] }

$invalidRate = $null
if ($lineInvalid -match "invalid_action_rate:\s*([0-9]*\.?[0-9]+)") { $invalidRate = [double]$matches[1] }

$fallbackRate = $null
if ($lineFallback -match "fallback_rate:\s*([0-9]*\.?[0-9]+)") { $fallbackRate = [double]$matches[1] }

$waitBackstepRate = $null
if ($lineWaitBk -match "wait_recovery_sb3_backstep_rate:\s*([0-9]*\.?[0-9]+)") { $waitBackstepRate = [double]$matches[1] }

$md = @()
$md += "# P4 v24 Smoke Summary"
$md += ""
$md += "## Quick Read"
$md += "- true_win_rate: $trueWin"
$md += "- loss_rate: $lossRate"
$md += "- vp_entry_conversion_rate: $vpConv"
$md += "- invalid_action_rate: $invalidRate"
$md += "- fallback_rate: $fallbackRate"
$md += "- wait_recovery_sb3_backstep_rate: $waitBackstepRate"
$md += ""
$md += "## Planner Diagnostics"
$md += "- $lineIntent"
$md += "- $lineRoles"
$md += ""
$md += "## Raw Key Lines"
$md += "- $lineSummary"
$md += "- $lineTrueWin"
$md += "- $lineInvalid"
$md += "- $lineFallback"
$md += "- $lineWaitBk"
$md += "- $lineVpConv"
$md += "- $lineLoss"
$md += ""
$md += "## Gate Notes (manual)"
$md += "- P4 v24 expected direction: intent_commitment up, UNKNOWN role share down."
$md += "- R2.1 expected direction: invalid/fallback/wait_backstep rates down."
$md += "- Keep NO-GO if loss worsens materially or fallback_rate remains high without mission gains."

Set-Content -Path $summaryMd -Value ($md -join "`r`n") -Encoding UTF8

Write-Host ""
Write-Host "✅ P4 v24 smoke completado"
Write-Host "Test log : $testLog"
Write-Host "Eval log : $evalLog"
Write-Host "Summary  : $summaryMd"