# run_train_eval.ps1
# Uso:
#   .\run_train_eval.ps1
#   .\run_train_eval.ps1 -RepoPath "C:\repos\python\assault"
#   .\run_train_eval.ps1 -SkipTrain -Seeds 42,43,44 -Episodes 100
#   .\run_train_eval.ps1 -OutDir "C:\tmp\sb3_eval\run_custom"

[CmdletBinding()]
param(
  [string]$RepoPath = "C:\repos\python\assault",
  [int[]]$Seeds = @(42, 43, 44),
  [int]$Episodes = 100,
  [switch]$SkipTrain,
  [string]$OutDir,
  [switch]$ContinueOnEvalError
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
  param(
    [string]$Message,
    [string]$FilePath
  )
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$ts] $Message" | Tee-Object -FilePath $FilePath -Append
}

function Run-Step {
  param(
    [string]$Title,
    [string[]]$Command,
    [string]$FilePath,
    [string]$HeartbeatPath
  )

  Write-Log "==== $Title ====" $FilePath
  Write-Log ("CMD: " + ($Command -join " ")) $FilePath
  $startedAt = Get-Date
  Set-Content -Path $HeartbeatPath -Value ("status=running`nstep={0}`nstarted_at={1}`nlast_update={1}`nelapsed_seconds=0" -f $Title, ($startedAt.ToString("s")))

  $hbJob = Start-Job -ScriptBlock {
    param($Path, $Step, $StartText)
    $start = [datetime]::Parse($StartText)
    while ($true) {
      $now = Get-Date
      $elapsed = [int]([timespan]($now - $start)).TotalSeconds
      $content = @(
        "status=running"
        "step=$Step"
        "started_at=$StartText"
        ("last_update=" + $now.ToString("s"))
        "elapsed_seconds=$elapsed"
      ) -join [Environment]::NewLine
      Set-Content -Path $Path -Value $content
      Start-Sleep -Seconds 15
    }
  } -ArgumentList $HeartbeatPath, $Title, $startedAt.ToString("s")

  try {
    # Native Python stderr lines should be logged fully (no early Stop on first stderr line).
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Command[0] $Command[1..($Command.Length - 1)] 2>&1 | Tee-Object -FilePath $FilePath -Append
    $ErrorActionPreference = $prevEap
    if ($LASTEXITCODE -ne 0) {
      throw "Fallo en paso: $Title (exit=$LASTEXITCODE)"
    }
    $doneAt = Get-Date
    $elapsedDone = [int]([timespan]($doneAt - $startedAt)).TotalSeconds
    Set-Content -Path $HeartbeatPath -Value ("status=done`nstep={0}`nstarted_at={1}`nlast_update={2}`nelapsed_seconds={3}" -f $Title, $startedAt.ToString("s"), $doneAt.ToString("s"), $elapsedDone)
  }
  catch {
    # Restore preference in case of early throw.
    $ErrorActionPreference = "Stop"
    $errAt = Get-Date
    $elapsedErr = [int]([timespan]($errAt - $startedAt)).TotalSeconds
    $msg = $_.Exception.Message -replace "`r|`n", " "
    $detail = ($_ | Out-String).Trim()
    Set-Content -Path $HeartbeatPath -Value ("status=error`nstep={0}`nstarted_at={1}`nlast_update={2}`nelapsed_seconds={3}`nerror={4}" -f $Title, $startedAt.ToString("s"), $errAt.ToString("s"), $elapsedErr, $msg)
    if (-not [string]::IsNullOrWhiteSpace($detail)) {
      Write-Log ("ERROR detail: {0}" -f $detail) $FilePath
    }
    throw
  }
  finally {
    if ($hbJob) {
      Stop-Job -Job $hbJob -ErrorAction SilentlyContinue | Out-Null
      Remove-Job -Job $hbJob -ErrorAction SilentlyContinue | Out-Null
    }
  }
}

if (-not (Test-Path -Path $RepoPath -PathType Container)) {
  throw "RepoPath no existe: $RepoPath"
}

$reportRoot = Join-Path $RepoPath "assault_sim\session\reports\sb3_eval"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = if ([string]::IsNullOrWhiteSpace($OutDir)) {
  Join-Path $reportRoot "run_$stamp"
} else {
  $OutDir
}
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$logFile = Join-Path $runDir "pipeline.log"
$heartbeatFile = Join-Path $runDir "heartbeat.txt"

$summary = [System.Collections.Generic.List[string]]::new()
$summary.Add("run_dir=$runDir")
$summary.Add("repo=$RepoPath")
$summary.Add("episodes=$Episodes")
$summary.Add("seeds=$($Seeds -join ',')")
$summary.Add("skip_train=$([bool]$SkipTrain)")

Push-Location $RepoPath
try {
  # Activar venv si existe.
  $activatePath = Join-Path $RepoPath ".venv\Scripts\Activate.ps1"
  if (Test-Path $activatePath) {
    . $activatePath
    Write-Log "Venv activado: $activatePath" $logFile
  } else {
    Write-Log "Venv no encontrado; se usará python del PATH." $logFile
  }

  if (-not $SkipTrain) {
    Run-Step -Title "TRAIN" -Command @("python", "-m", "assault_sim.train.train_sb3") -FilePath $logFile -HeartbeatPath $heartbeatFile
  } else {
    Write-Log "TRAIN omitido por -SkipTrain." $logFile
    Set-Content -Path $heartbeatFile -Value ("status=running`nstep=EVAL`nstarted_at={0}`nlast_update={0}`nelapsed_seconds=0" -f (Get-Date).ToString("s"))
  }

  foreach ($seed in $Seeds) {
    $title = "EVAL seed $seed"
    $cmd = @(
      "python", "-m", "assault_sim.evaluation.eval_sb3",
      "--seed", "$seed",
      "--episodes", "$Episodes",
      "--out-dir", "$runDir"
    )

    try {
      Run-Step -Title $title -Command $cmd -FilePath $logFile -HeartbeatPath $heartbeatFile
      $summary.Add("seed_$seed=ok")
    } catch {
      $summary.Add("seed_$seed=failed")
      Write-Log ("ERROR en {0}: {1}" -f $title, $_.Exception.Message) $logFile
      if (-not $ContinueOnEvalError) {
        throw
      }
    }
  }

  $reportFiles = Get-ChildItem -Path $runDir -Filter "metrics_sb3_report_*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
  if ($reportFiles) {
    Write-Log "Reportes JSON generados:" $logFile
    foreach ($f in $reportFiles) {
      Write-Log " - $($f.FullName)" $logFile
    }
  } else {
    Write-Log "No se detectaron reportes JSON en $runDir." $logFile
  }

  Write-Log "OK. Resultados en: $runDir" $logFile
  $finishedAt = Get-Date
  Set-Content -Path $heartbeatFile -Value ("status=finished`nstep=ALL`nstarted_at={0}`nlast_update={1}`nelapsed_seconds=0" -f $stamp, $finishedAt.ToString("s"))
  Write-Host "OK. Resultados en: $runDir"
}
finally {
  Pop-Location
  Write-Host "Resumen: $($summary -join ' | ')"
}