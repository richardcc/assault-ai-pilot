param(
  [string]$Repo = "C:\repos\python\assault",
  [int]$Episodes = 10,
  [switch]$DedupScenarioSchedule
)

$ErrorActionPreference = "Stop"

function Write-JsonNoBom([string]$Path, [string]$JsonText) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $JsonText, $utf8NoBom)
}

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  $configPath = Join-Path $Repo "assault_sim\config\train_config.json"
  $backupPath = Join-Path $Repo "assault_sim\config\train_config.gate_eval_backup.json"

  if ($DedupScenarioSchedule) {
    Copy-Item $configPath $backupPath -Force
    $cfgObj = (Get-Content $configPath -Raw) | ConvertFrom-Json
    if ($cfgObj.scenario_schedule -and $cfgObj.scenario_schedule.Count -gt 1) {
      $cfgObj.scenario_schedule = @($cfgObj.scenario_schedule[0])
      Write-JsonNoBom -Path $configPath -JsonText ($cfgObj | ConvertTo-Json -Depth 30)
      Write-Host "Applied temporary scenario_schedule dedupe for smoke eval."
    }
  }

  Write-Host "== Running smoke eval =="
  python -m assault_sim.evaluation.eval_sb3 --episodes $Episodes --seed 42
}
finally {
  $backupPath = Join-Path $Repo "assault_sim\config\train_config.gate_eval_backup.json"
  $configPath = Join-Path $Repo "assault_sim\config\train_config.json"
  if (Test-Path $backupPath) {
    Move-Item $backupPath $configPath -Force
    Write-Host "Restored original train_config.json"
  }
  Pop-Location
}