param(
  [string]$Repo = "C:\repos\python\assault",
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

function Remove-PathSafe {
  param([string]$PathToRemove)
  if (Test-Path $PathToRemove) {
    Remove-Item -Recurse -Force $PathToRemove
    Write-Host "REMOVED: $PathToRemove"
  } else {
    Write-Host "SKIP (missing): $PathToRemove"
  }
}

Push-Location $Repo
try {
  $targets = @(
    ".\runs",
    ".\runs_curriculum",
    ".\mlruns",
    ".\.pytest_cache"
  )

  # Include all local Python cache directories.
  $pyCaches = Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { $_.FullName }
  $targets += $pyCaches

  $uniqueTargets = $targets | Sort-Object -Unique

  Write-Host "== CLEANUP PLAN =="
  $uniqueTargets | ForEach-Object { Write-Host $_ }

  if (-not $Execute) {
    Write-Host ""
    Write-Host "Dry-run only. Nothing deleted."
    Write-Host "Run with -Execute to delete everything listed."
    exit 0
  }

  Write-Host ""
  Write-Host "== EXECUTING DELETION =="
  $uniqueTargets | ForEach-Object { Remove-PathSafe $_ }

  Write-Host ""
  Write-Host "Cleanup complete."
}
finally {
  Pop-Location
}
