param(
  [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  Write-Host "== VERIFY CLEAN STATE =="

  $checks = @(
    ".\runs",
    ".\runs_curriculum",
    ".\mlruns",
    ".\.pytest_cache"
  )

  foreach ($p in $checks) {
    $exists = Test-Path $p
    Write-Host ("{0} => {1}" -f $p, $exists)
  }

  $pyCaches = Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
  Write-Host ("__pycache__ directories remaining: {0}" -f @($pyCaches).Count)
}
finally {
  Pop-Location
}
