param(
  [switch]$Serve
)

$ErrorActionPreference = "Stop"

if ($Serve) {
  python -m mkdocs serve
} else {
  python -m mkdocs build
  if ($LASTEXITCODE -ne 0) {
    throw "mkdocs build failed (exit=$LASTEXITCODE)"
  }
  Write-Host "HTML generated at: site"
}
