[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [int[]]$Seeds = @(7, 13, 29),
  [string]$SeedsCsv = "",
  [int]$TrainIterations = 24,
  [int]$EpisodesPerIter = 16
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  Write-Host ("[MuZero] VP progress AB3 long preset | iterations={0} episodes_per_iter={1}" -f $TrainIterations, $EpisodesPerIter)
  & ".\scripts\run_muzero_vp_progress_ab3.ps1" `
    -Repo $Repo `
    -Seeds $Seeds `
    -SeedsCsv $SeedsCsv `
    -TrainIterations $TrainIterations `
    -EpisodesPerIter $EpisodesPerIter

  if ($LASTEXITCODE -ne 0) {
    throw ("run_muzero_vp_progress_ab3.ps1 failed (exit={0})" -f $LASTEXITCODE)
  }
}
finally {
  Pop-Location
}

