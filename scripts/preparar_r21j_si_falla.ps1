param(
  [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

$reportsDir = Join-Path $Repo "assault_sim\session\reports\sb3_eval"
if (-not (Test-Path -Path $reportsDir -PathType Container)) {
  throw "No existe carpeta de reportes: $reportsDir"
}

$latest = Get-ChildItem -Path $reportsDir -File -Filter "r21i_closeout_*.json" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if ($null -eq $latest) {
  throw "No se encontro closeout de R2.1-i. Ejecuta primero scripts\cerrar_r21i.ps1"
}

$payload = Get-Content $latest.FullName -Raw | ConvertFrom-Json
$decision = [string]$payload.decision

if ($decision -ne "NO-GO") {
  Write-Host "R2.1-i no esta en NO-GO. No se abre R2.1-j." -ForegroundColor Yellow
  Write-Host "Decision actual: $decision"
  exit 0
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$outPath = Join-Path $reportsDir ("r21j_bootstrap_" + $stamp + ".md")

$content = @(
  "# R2.1-j bootstrap",
  "",
  "- source_closeout: " + $latest.FullName,
  "- decision_in: NO-GO",
  "- created_utc: $stamp",
  "",
  "Checklist inicial R2.1-j:",
  "- [ ] definir una sola palanca",
  "- [ ] mantener seeds/episodes del protocolo fijo",
  "- [ ] ejecutar multi-seed y gatear con mismos umbrales",
  "- [ ] registrar decision final GO/NO-GO"
) -join "`n"

[System.IO.File]::WriteAllText($outPath, $content, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "R2.1-j preparado." -ForegroundColor Green
Write-Host "Archivo: $outPath"
exit 0
