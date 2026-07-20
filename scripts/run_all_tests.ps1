param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$PythonExe = "",
  [string]$Keyword = "",
  [int]$MaxFail = 1,
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  $py = $PythonExe
  if (-not $py) {
    if (Test-Path ".\.venv\Scripts\python.exe") {
      $py = ".\.venv\Scripts\python.exe"
    } else {
      $py = "python"
    }
  }

  Write-Host "== Running full pytest suite =="
  Write-Host "Repo: $Repo"
  Write-Host "Python: $py"

  $args = @("-m", "pytest", "-o", "addopts=", "-ra", "--maxfail=$MaxFail")
  if ($Quiet) {
    $args += "-q"
  }
  if ($Keyword -and $Keyword.Trim()) {
    $args += @("-k", $Keyword.Trim())
  }

  & $py @args
}
finally {
  Pop-Location
}
