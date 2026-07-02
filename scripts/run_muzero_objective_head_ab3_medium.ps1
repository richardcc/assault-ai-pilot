[CmdletBinding()]
param(
  [string]$Repo = "C:\repos\python\assault",
  [int[]]$Seeds = @(7, 13, 29),
  [double]$ObjectiveLossWeightOff = 0.0,
  [double]$ObjectiveLossWeightOn = 0.25
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  & ".\scripts\run_muzero_objective_head_ab3.ps1" `
    -Repo $Repo `
    -Seeds $Seeds `
    -ObjectiveLossWeightOff $ObjectiveLossWeightOff `
    -ObjectiveLossWeightOn $ObjectiveLossWeightOn `
    -TrainIterations 10 `
    -EpisodesPerIter 8
}
finally {
  Pop-Location
}
