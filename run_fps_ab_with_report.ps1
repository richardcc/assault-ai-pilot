# run_fps_ab_with_report.ps1
# Ejecuta A/B de rendimiento + smoke eval y genera tabla Markdown GO/NO-GO
#
# Uso:
#   .\run_fps_ab_with_report.ps1 -BaseOutDir "C:\repos\python\assault\assault_sim\session\reports\sb3_eval\fps_ab_$(Get-Date -Format yyyyMMdd_HHmmss)"
#
# Notas:
# - train_sb3 NO soporta --total-timesteps/--vec-env/--num-envs por CLI.
# - Este script crea un config temporal por variante y llama:
#     python -m assault_sim.train.train_sb3 --config <tmp_config.json>

param(
    [string]$BaseOutDir = "C:\repos\python\assault\assault_sim\session\reports\sb3_eval\fps_ab",
    [int]$TrainSteps = 240000,
    [int]$SmokeEpisodes = 20,
    [string]$Seeds = "42,43,44",
    [int]$EvalParallelJobs = 3,
    [string]$BaseTrainConfig = "C:\repos\python\assault\assault_sim\config\train_config.json",
    [switch]$KeepTempConfigs
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $BaseOutDir | Out-Null

$results = @()

function Get-LastMetricFromLog {
    param(
        [string]$LogPath,
        [string]$MetricName
    )
    if (!(Test-Path $LogPath)) { return $null }

    $line = Select-String -Path $LogPath -Pattern "\|\s*$MetricName\s*\|" | Select-Object -Last 1
    if (!$line) { return $null }

    # Ejemplo: |    fps                  | 46           |
    if ($line.Line -match "\|\s*$([regex]::Escape($MetricName))\s*\|\s*([^\|]+)\|") {
        return $matches[1].Trim()
    }
    return $null
}

function Get-LastEvalSideLine {
    param([string]$EvalLog)
    if (!(Test-Path $EvalLog)) { return $null }

    $match = Select-String -Path $EvalLog -Pattern "^side=.*true_win_rate\(only_wins\)=" | Select-Object -Last 1
    if ($match) { return $match.Line.Trim() }

    return $null
}

function Parse-EvalMetric {
    param(
        [string]$Line,
        [string]$Name
    )
    if ([string]::IsNullOrWhiteSpace($Line)) { return $null }

    if ($Line -match "$([regex]::Escape($Name))=([0-9]*\.?[0-9]+)") {
        return [double]$matches[1]
    }
    return $null
}

function Decide-GoNoGo {
    param(
        [double]$BaseFps,
        [double]$Fps,
        [double]$BaseTwr,
        [double]$Twr,
        [double]$BaseLr,
        [double]$Lr
    )

    # GO si FPS >= +20% y no empeora TWR/LR en más de 0.05
    if ($BaseFps -le 0) { return "PENDING" }
    $fpsGain = ($Fps - $BaseFps) / $BaseFps

    $twrOk = $true
    $lrOk = $true
    if ($null -ne $BaseTwr -and $null -ne $Twr) { $twrOk = (($Twr + 0.00001) - $BaseTwr) -ge -0.05 }
    if ($null -ne $BaseLr -and $null -ne $Lr) { $lrOk = ($Lr - $BaseLr) -le 0.05 }

    if ($fpsGain -ge 0.20 -and $twrOk -and $lrOk) { return "GO" }
    return "NO-GO"
}

function New-VariantTrainConfig {
    param(
        [string]$SourceConfig,
        [string]$TargetConfig,
        [int]$TotalTimesteps,
        [string]$VecEnv,
        [int]$NumEnvs
    )

    if (!(Test-Path $SourceConfig)) {
        throw "No existe BaseTrainConfig: $SourceConfig"
    }

    $cfg = Get-Content $SourceConfig -Raw | ConvertFrom-Json
    $cfg.sb3_total_timesteps = $TotalTimesteps
    $cfg.sb3_vec_env_type = $VecEnv
    $cfg.sb3_num_envs = $NumEnvs

    # UTF-8 sin BOM
    $json = $cfg | ConvertTo-Json -Depth 50
    [System.IO.File]::WriteAllText($TargetConfig, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Run-LoggedCommand {
    param(
        [string]$Exe,
        [string[]]$CmdArgs,   # <- importante: NO usar "Args"
        [string]$LogPath,
        [string]$Label
    )

    Write-Host "[$Label] $Exe $($CmdArgs -join ' ')"
    & $Exe @CmdArgs 2>&1 | Tee-Object -FilePath $LogPath
    $code = $LASTEXITCODE

    if ($code -ne 0) {
        Write-Host "[$Label] ERROR exit_code=$code. Revisa log: $LogPath" -ForegroundColor Red
        throw "$Label failed with exit code $code"
    }
}

function Run-Variant {
    param(
        [string]$Name,
        [string]$VecEnv,
        [int]$NumEnvs
    )

    $OutDir = Join-Path $BaseOutDir $Name
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

    Write-Host ""
    Write-Host "=== RUN $Name (vec_env=$VecEnv num_envs=$NumEnvs) ===" -ForegroundColor Cyan

    $trainLog = Join-Path $OutDir "train.log"
    $evalLog  = Join-Path $OutDir "eval.log"
    $tmpCfg   = Join-Path $OutDir "train_config.tmp.json"

    # 0) Config temporal por variante
    New-VariantTrainConfig `
        -SourceConfig $BaseTrainConfig `
        -TargetConfig $tmpCfg `
        -TotalTimesteps $TrainSteps `
        -VecEnv $VecEnv `
        -NumEnvs $NumEnvs

    # 1) Train corto para medir FPS
    Run-LoggedCommand `
        -Exe "python" `
        -CmdArgs @("-m","assault_sim.train.train_sb3","--config",$tmpCfg) `
        -LogPath $trainLog `
        -Label "TRAIN"

    # 2) Eval smoke multi-seed
    Run-LoggedCommand `
        -Exe "powershell" `
        -CmdArgs @(
            "-NoProfile","-ExecutionPolicy","Bypass","-File",".\run_train_eval.ps1",
            "-SkipTrain",
            "-Seeds",$Seeds,
            "-Episodes","$SmokeEpisodes",
            "-ParallelEvalSeeds",
            "-EvalParallelJobs","$EvalParallelJobs",
            "-OutDir","$OutDir\eval_smoke"
        ) `
        -LogPath $evalLog `
        -Label "EVAL"

    # 3) Parse métricas
    $fps = Get-LastMetricFromLog -LogPath $trainLog -MetricName "fps"
    $timeElapsed = Get-LastMetricFromLog -LogPath $trainLog -MetricName "time_elapsed"
    $steps = Get-LastMetricFromLog -LogPath $trainLog -MetricName "total_timesteps"
    $epRew = Get-LastMetricFromLog -LogPath $trainLog -MetricName "ep_rew_mean"

    $evalLine = Get-LastEvalSideLine -EvalLog $evalLog
    $trueWin = Parse-EvalMetric -Line $evalLine -Name "true_win_rate\(only_wins\)"
    $lossRate = Parse-EvalMetric -Line $evalLine -Name "loss_rate"

    if (-not $KeepTempConfigs) {
        Remove-Item -Path $tmpCfg -Force -ErrorAction SilentlyContinue
    }

    return [pscustomobject]@{
        Run = $Name
        CambioUnico = "vec_env=$VecEnv num_envs=$NumEnvs"
        Steps = $steps
        TimeSec = $timeElapsed
        FPS = $fps
        EpRewMean = $epRew
        TrueWinRate = $trueWin
        LossRate = $lossRate
        EvalSummary = $evalLine
        GoNoGo = "PENDING"
    }
}

# Variantes (matriz corta R1.b)
$variants = @(
    @{ Name = "baseline_dummy_env4"; VecEnv = "dummy";   NumEnvs = 4 },
    @{ Name = "A_subproc_env4";      VecEnv = "subproc"; NumEnvs = 4 },
    @{ Name = "B_dummy_env8";        VecEnv = "dummy";   NumEnvs = 8 },
    @{ Name = "C_subproc_env8";      VecEnv = "subproc"; NumEnvs = 8 }
)

foreach ($v in $variants) {
    $results += Run-Variant -Name $v.Name -VecEnv $v.VecEnv -NumEnvs $v.NumEnvs
}

# Decide GO/NO-GO contra baseline
$base = $results | Where-Object { $_.Run -eq "baseline_dummy_env4" } | Select-Object -First 1
$baseFps = [double]($base.FPS -as [double])
$baseTwr = $base.TrueWinRate
$baseLr  = $base.LossRate

foreach ($r in $results) {
    $fpsVal = [double]($r.FPS -as [double])
    $r.GoNoGo = Decide-GoNoGo -BaseFps $baseFps -Fps $fpsVal -BaseTwr $baseTwr -Twr $r.TrueWinRate -BaseLr $baseLr -Lr $r.LossRate
}

# Export CSV
$csvPath = Join-Path $BaseOutDir "fps_ab_summary.csv"
$results | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $csvPath

# Export Markdown
$mdPath = Join-Path $BaseOutDir "fps_ab_summary.md"
$md = @()
$md += "# FPS A/B Summary"
$md += ""
$md += "| Run | Cambio único | Steps | Time (s) | FPS | ep_rew_mean | true_win_rate (smoke) | loss_rate (smoke) | GO/NO-GO |"
$md += "|---|---|---:|---:|---:|---:|---:|---:|---|"
foreach ($r in $results) {
    $md += "| $($r.Run) | $($r.CambioUnico) | $($r.Steps) | $($r.TimeSec) | $($r.FPS) | $($r.EpRewMean) | $($r.TrueWinRate) | $($r.LossRate) | $($r.GoNoGo) |"
}
$md += ""
$md += "## Raw eval lines"
foreach ($r in $results) {
    $md += "- **$($r.Run)**: $($r.EvalSummary)"
}
Set-Content -Path $mdPath -Value ($md -join "`r`n") -Encoding UTF8

Write-Host ""
Write-Host "✅ Listo"
Write-Host "CSV: $csvPath"
Write-Host "MD : $mdPath"