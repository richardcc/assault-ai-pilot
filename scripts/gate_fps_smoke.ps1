param(
  [string]$Repo = "C:\repos\python\assault"
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
  $backupPath = Join-Path $Repo "assault_sim\config\train_config.gate_fps_backup.json"

  Copy-Item $configPath $backupPath -Force

  $cfgObj = (Get-Content $configPath -Raw) | ConvertFrom-Json
  $cfgObj.sb3_total_timesteps = 30000
  $cfgObj.sb3_eval_freq = 1000000
  $cfgObj.sb3_eval_episodes = 1
  $cfgObj.sb3_clean_models_before_train = $false

  Write-JsonNoBom -Path $configPath -JsonText ($cfgObj | ConvertTo-Json -Depth 30)

  Write-Host "== Running FPS smoke train =="
  $start = Get-Date
  python -m assault_sim.train.train_sb3
  $elapsed = (Get-Date) - $start
  Write-Host ("Elapsed seconds: {0:N2}" -f $elapsed.TotalSeconds)
}
finally {
  $backupPath = Join-Path $Repo "assault_sim\config\train_config.gate_fps_backup.json"
  $configPath = Join-Path $Repo "assault_sim\config\train_config.json"
  if (Test-Path $backupPath) {
    Move-Item $backupPath $configPath -Force
    Write-Host "Restored original train_config.json"
  }
  Pop-Location
}